"""scripts/metabolism_immune.py — IMMUNE lane (R-V8-1..R-V8-5).

PURPOSE
-------
Runs every 2h (cron '15 */2 * * *').  Three independent responsibilities:

  A. MAIN-RED SENTINEL
     Reads main's combined check-runs via gh api, finds red REQUIRED checks.
     - Known class + no live claim  → fresh git worktree off origin/main,
       run heal_cmd, verify detector passes, commit claim row, push, open DRAFT PR.
     - Unknown class                → insight_bus row (ci_red_unknown) + Telegram.

  B. LANE-HEALTH SENSORS (R-V8-4)
     - Dead cron (cancelled/timed_out latest run per schedule workflow)
     - Queue saturation (runs queued > queue_stuck_min minutes)
     - Offline self-hosted runners
     - Key-pool partial degradation (>50% cooling)
     Each fires once per day per condition (dedup via journal markers).

  C. AUTO-MERGE — DEFERRED (R-V8-3, amended 2026-07-12).
     Auto-merge is NOT implemented in this wave (v8A).  The lane opens a claimed
     DRAFT heal PR and stops.  Auto-merge returns as R-V8-3b (future wave) with
     the correct re-scan design (a later run merges an already-open PR when it is
     green at a fresh head SHA) and requires config/metabolism_immune.yml to be in
     the self-mod fence IMMUTABLE set (done this wave).

  D. CI-STATUS ARTIFACT (R-V8-5)
     Writes data/metabolism/ci_status.json after every run so
     anomaly_monitor.ci_red_streak comes alive.

INERTNESS GUARANTEES
--------------------
* Sensing (A + B + D) runs even when AUTONOMY_PAUSED.
* NEVER-RAISE: all public functions catch exceptions and return safe fallbacks.

Usage (CLI):
    python -m scripts.metabolism_immune [--root <path>] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

_CI_STATUS_REL = ("data", "metabolism", "ci_status.json")
_REPO_OWNER_REPO: str | None = None  # lazy-resolved; NEVER memoize None (a transient
                                      # failure must be retried on the next call)
_OWNER_REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
_HEARTBEAT_WORKFLOW = "ci-main-heartbeat.yml"


# ── Pause guard ────────────────────────────────────────────────────────────────

def _is_paused() -> bool:
    """Return True unless AUTONOMY_PAUSED is the exact string 'false'.  NEVER raises."""
    try:
        from scripts.metabolism_guard import is_paused
        return is_paused()
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_immune._is_paused: %s — treating as paused", exc)
        return True


# ── Telegram notify ────────────────────────────────────────────────────────────

def _notify(text: str) -> None:
    """Send a Telegram message.  NEVER raises; silently drops on missing creds."""
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
        chat_id = os.environ.get("TELEGRAM_CHAT_ID") or ""
        if not token or not chat_id:
            return
        subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                f"https://api.telegram.org/bot{token}/sendMessage",
                "-d", f"chat_id={chat_id}",
                "-d", f"text={text}",
            ],
            capture_output=True, timeout=15,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._notify: %s", exc)


# ── gh helpers (subprocess boundary) ──────────────────────────────────────────

def _gh_json(args: list[str], timeout: int = 60) -> Any:
    """Run a gh command, return parsed JSON, or None on failure.  NEVER raises.

    Returns the raw parsed value from stdout — a dict, list, or scalar.
    Use _gh_json_list when the caller needs a flat list of dicts.
    """
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            log.warning("immune._gh_json: gh %s failed: %s", " ".join(args[:4]), result.stderr[:200])
            return None
        text = result.stdout or "null"
        return json.loads(text)
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._gh_json: %s", exc)
        return None


def _gh_json_list(args: list[str], timeout: int = 60) -> list[dict]:
    """Run a gh command and ALWAYS return a flat list of dicts.  NEVER raises.

    Handles all three output shapes produced by gh:

    1. Single object per line (NDJSON, e.g. --paginate --jq '.check_runs[]'):
       Each line is a dict → collected into a list.

    2. Array per page (e.g. --paginate --jq '.workflow_runs' where each page
       emits one JSON array):  Each line is a list → extended into result.

    3. Single line (one object or one array, no --paginate):
       Treated as a one-element or multi-element flat result.

    Empty output or errors → [].
    """
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            log.warning("immune._gh_json_list: gh %s failed: %s", " ".join(args[:4]), result.stderr[:200])
            return []
        text = result.stdout or ""
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return []
        flat: list[dict] = []
        for line in lines:
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, list):
                flat.extend(item for item in obj if isinstance(item, dict))
            elif isinstance(obj, dict):
                flat.append(obj)
            # scalars silently dropped
        return flat
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._gh_json_list: %s", exc)
        return []


def _get_main_sha() -> str:
    """Return current HEAD SHA of origin/main.  NEVER raises."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._get_main_sha: %s", exc)
    return ""


def _get_heartbeat_head_sha(repo: str | None) -> str | None:
    """Return the head_sha of the newest CONCLUDED ci-main-heartbeat.yml run.

    Failure to resolve this is NOT a hard sensing failure — the caller falls
    back to sensing live origin/main HEAD alone and logs a warning.  Deliberately
    does NOT use --paginate (a single most-recent completed run is all we need).
    NEVER raises.
    """
    try:
        if not repo:
            return None
        result = subprocess.run(
            [
                "gh", "api",
                f"/repos/{repo}/actions/workflows/{_HEARTBEAT_WORKFLOW}/runs"
                f"?status=completed&per_page=1",
                "--jq", ".workflow_runs[0].head_sha",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log.warning(
                "immune._get_heartbeat_head_sha: gh api failed: %s", result.stderr[:200],
            )
            return None
        sha = (result.stdout or "").strip()
        if not sha or sha == "null":
            return None
        return sha
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._get_heartbeat_head_sha: %s", exc)
        return None


def _sense_required_red_checks(
    main_sha: str,
    immune_cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    """Union red required checks across TWO SHAs, de-duplicated by check name.

    _get_main_sha() reads live origin/main HEAD, but ci-main-heartbeat.yml runs
    on a 6-hourly cron while main advances ~17 commits/hour — so sensing HEAD
    alone structurally reads a commit that never carried the heartbeat's own
    check-runs, and reports a false-clean read.  This unions:
      1. red required checks on live origin/main HEAD, and
      2. red required checks on the head_sha of the newest CONCLUDED
         ci-main-heartbeat.yml run (via _get_heartbeat_head_sha).
    keeping the FIRST occurrence of each check name.

    Returns None (BLIND) only when the origin/main HEAD read itself failed —
    that is the read this whole sentinel exists to make.  Failure to resolve
    the heartbeat SHA, or to read check-runs at a heartbeat SHA that WAS
    resolved, is logged and does not blind the run: it continues on the main
    HEAD read alone.  NEVER raises.
    """
    try:
        main_reds = _get_required_red_checks(main_sha, immune_cfg=immune_cfg)
        if main_reds is None:
            return None

        union: list[dict[str, Any]] = list(main_reds)
        seen = {c.get("name") for c in union}

        repo = _resolve_repo()
        heartbeat_sha = _get_heartbeat_head_sha(repo)
        if not heartbeat_sha:
            log.info(
                "immune._sense_required_red_checks: could not resolve %s head_sha — "
                "continuing on main HEAD alone", _HEARTBEAT_WORKFLOW,
            )
            return union

        if heartbeat_sha == main_sha:
            return union

        hb_reds = _get_required_red_checks(heartbeat_sha, immune_cfg=immune_cfg)
        if hb_reds is None:
            log.warning(
                "immune._sense_required_red_checks: heartbeat sha=%s read failed — "
                "continuing on main HEAD alone", heartbeat_sha[:8],
            )
            return union

        for c in hb_reds:
            name = c.get("name")
            if name in seen:
                continue
            seen.add(name)
            union.append(c)
        return union
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._sense_required_red_checks: %s", exc)
        return None


def _get_spurious_check_names(immune_cfg: dict[str, Any]) -> set[str]:
    """Return the set of known-spurious check names from config.  NEVER raises."""
    try:
        raw = immune_cfg.get("spurious_checks") or []
        return {str(s).lower() for s in raw if s}
    except Exception:  # noqa: BLE001
        return set()


def _get_required_red_checks(
    main_sha: str,
    immune_cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    """Return red REQUIRED check-runs on main at main_sha.

    Return contract (2026-08-18 repair — the whole point of this function):
      * ``None``  → SENSING FAILED.  Could not determine whether main is red
        or clean: repo unresolved, or both the paginated NDJSON read and the
        plain-fetch fallback failed to produce a usable payload (non-2xx,
        unparseable, or not a dict).  Callers MUST treat this as BLIND, never
        as "no reds" — a 404 (repo unresolved) and a genuinely clean main used
        to collapse to the same value here, which is exactly how nine days of
        two red required checks on main went unnoticed while every scheduled
        run logged "success".
      * ``[]``    → the read SUCCEEDED and there are simply no red checks.

    Known-spurious check names (from config spurious_checks) are excluded so
    the immune lane never opens a heal PR or emits a page for a known false red.

    Uses gh api to get the combined check-runs for the commit.  NEVER raises.
    """
    try:
        if not main_sha:
            return None
        spurious = _get_spurious_check_names(immune_cfg or {})
        repo = _resolve_repo()
        if repo is None:
            log.warning(
                "immune._get_required_red_checks: repo unresolved — sensing BLIND for sha=%s",
                main_sha[:8],
            )
            return None

        # .check_runs[] emits one dict per line (NDJSON); _gh_json_list flattens correctly.
        checks = _gh_json_list([
            "api",
            f"/repos/{repo}/commits/{main_sha}/check-runs",
            "--paginate",
            "--jq", ".check_runs[]",
        ], timeout=60)
        if checks:
            read_ok = True
        else:
            # Fallback: plain fetch without --jq; extract check_runs array from dict.
            # A dict response IS a successful read even when check_runs is empty
            # (a real gh api success for this endpoint always returns a JSON
            # object — never truly empty stdout); anything else is a failed read.
            raw = _gh_json([
                "api",
                f"/repos/{repo}/commits/{main_sha}/check-runs",
            ], timeout=60)
            if isinstance(raw, dict):
                checks = raw.get("check_runs") or []
                read_ok = True
            else:
                checks = []
                read_ok = False

        if not read_ok:
            log.warning(
                "immune._get_required_red_checks: both reads failed for sha=%s — sensing BLIND",
                main_sha[:8],
            )
            return None

        red = []
        for c in checks:
            name = c.get("name") or ""
            # Filter known-spurious checks (e.g. 'Workers Builds: macro').
            # Use SUBSTRING match: a live check name may carry qualifiers like
            # 'Workers Builds: macro (deploy)' which would NOT hit exact-set membership.
            name_lower = name.lower()
            if any(s in name_lower for s in spurious):
                log.info("IMMUNE: skipping known-spurious check %r", name)
                continue
            conclusion = str(c.get("conclusion") or "").lower()
            status = str(c.get("status") or "").lower()
            if conclusion in {"failure", "timed_out", "cancelled", "action_required"}:
                red.append({
                    "name": name,
                    "conclusion": conclusion,
                    "status": status,
                    "url": c.get("html_url") or "",
                })
        return red
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._get_required_red_checks: %s", exc)
        return None


def _parse_owner_repo_from_remote(url: str) -> str | None:
    """Parse an 'owner/repo' string out of a git remote URL.  NEVER raises.

    Handles both forms, with or without a trailing '.git':
      https://github.com/owner/repo(.git)
      git@github.com:owner/repo(.git)
    """
    try:
        u = (url or "").strip()
        if not u:
            return None
        if u.endswith(".git"):
            u = u[: -len(".git")]
        if "://" in u:
            # https://host/owner/repo
            tail = u.split("://", 1)[1]
            parts = tail.split("/", 1)
            tail = parts[1] if len(parts) > 1 else ""
        elif "@" in u and ":" in u:
            # git@host:owner/repo
            tail = u.split(":", 1)[1]
        else:
            tail = u
        tail = tail.strip("/")
        if _OWNER_REPO_RE.match(tail):
            return tail
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._parse_owner_repo_from_remote: %s", exc)
    return None


def _resolve_repo() -> str | None:
    """Return 'owner/repo', or None if it cannot be determined.  NEVER raises.

    Resolution order:
      1. ``GITHUB_REPOSITORY`` env var (Actions-native; no subprocess needed).
      2. ``gh repo view --json nameWithOwner``.
      3. Parse 'owner/repo' out of ``git remote get-url origin``.
      4. Emit a GitHub error annotation and return None.

    MUST NEVER return the literal placeholder string ``"owner/repo"`` — that
    fallback (present until 2026-08-18) silently turned every downstream read
    into a 404 against the literal repo path ``/repos/owner/repo/...``, and
    because _get_required_red_checks could not distinguish "read failed" from
    "main is clean", the sentinel logged red_required=0 and exited 0 on every
    run for nine days while two required checks were actually red on main.
    A resolution failure (None) is deliberately NOT memoized, so a transient
    hiccup (e.g. a momentary gh/network failure) can resolve on a later call
    within the same process; a successful resolution IS memoized, since the
    repo identity cannot change mid-run.
    """
    global _REPO_OWNER_REPO
    if _REPO_OWNER_REPO:
        return _REPO_OWNER_REPO

    try:
        env_repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
        if _OWNER_REPO_RE.match(env_repo):
            _REPO_OWNER_REPO = env_repo
            return _REPO_OWNER_REPO
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._resolve_repo: GITHUB_REPOSITORY check failed: %s", exc)

    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            candidate = result.stdout.strip()
            if _OWNER_REPO_RE.match(candidate):
                _REPO_OWNER_REPO = candidate
                return _REPO_OWNER_REPO
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._resolve_repo: gh repo view failed: %s", exc)

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            candidate = _parse_owner_repo_from_remote(result.stdout)
            if candidate:
                _REPO_OWNER_REPO = candidate
                return _REPO_OWNER_REPO
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._resolve_repo: git remote get-url failed: %s", exc)

    print(
        "::error title=immune-repo-unresolved::metabolism_immune could not determine "
        "owner/repo via GITHUB_REPOSITORY, gh repo view, or git remote get-url origin — "
        "the main-red sentinel is BLIND until this resolves",
        flush=True,
    )
    return None


def _gh_pr_state(pr_number: int) -> str:
    """Return PR state string ('OPEN'|'CLOSED'|'MERGED'|'unknown').  NEVER raises."""
    try:
        data = _gh_json([
            "pr", "view", str(pr_number), "--json", "state",
        ], timeout=30)
        if isinstance(data, dict):
            return str(data.get("state") or "unknown").upper()
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._gh_pr_state: %s", exc)
    return "unknown"


def _pr_ci_green_at_sha(pr_number: int) -> tuple[bool, str]:
    """Return (green, head_sha) for a PR.  Fail-closed on any error.  NEVER raises.

    Uses the shared merge-on-green binding-check semantics: for PRs targeting
    main, the inactive ``ci-authority/codex/merge-queue-pilot`` context is not
    a red this PR owns. ``ci-authority/main`` stays binding.
    """
    try:
        try:
            from scripts.merge_on_green import binding_status_checks
        except ImportError:  # ``python scripts/metabolism_immune.py``
            from merge_on_green import binding_status_checks  # type: ignore[no-redef]
        data = _gh_json([
            "pr", "view", str(pr_number),
            "--json", "headRefOid,statusCheckRollup,baseRefName",
        ], timeout=30)
        if not isinstance(data, dict):
            return False, ""
        head_sha = data.get("headRefOid") or ""
        checks = binding_status_checks(
            list(data.get("statusCheckRollup") or []),
            base_ref=str(data.get("baseRefName") or "main"),
        )
        if not checks:
            return False, head_sha  # No checks = fail-closed
        passing = {"SUCCESS", "NEUTRAL", "SKIPPED"}
        green = all(
            (str(c.get("state") or c.get("conclusion") or "")).upper() in passing
            for c in checks
        )
        return green, head_sha
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._pr_ci_green_at_sha: %s", exc)
        return False, ""


# ── Heal worktree ──────────────────────────────────────────────────────────────

def _heal_pr_create_env() -> dict[str, str]:
    """Environment for the single 'gh pr create' call that opens the DRAFT heal PR.

    A PR opened under the workflow's own GITHUB_TOKEN identity does not
    trigger pull_request CI (GitHub's anti-recursion rule for Actions-authored
    events are exempt from required-check triggers), so a draft heal PR
    opened with the ambient token would sit with zero required checks ever
    run.  METABOLISM_MERGE_PAT is a separate, no-workflows-scope PAT whose
    PRs DO trigger pull_request CI — that is its entire documented purpose
    (see metabolism-immune.yml's checkout step comment).

    This override is scoped to ONLY this one gh invocation.  Sensing
    (_resolve_repo, _get_required_red_checks, _sense_required_red_checks) and
    every other subprocess call in this module run on the workflow's ambient
    GITHUB_TOKEN via GH_TOKEN — sensing must never depend on the PAT being
    alive.  Falls back to the ambient environment untouched when
    METABOLISM_MERGE_PAT is absent/empty (e.g. local dev, or the PAT being
    dead/unprovisioned) — the PR still opens, it just won't self-trigger CI.
    NEVER raises.
    """
    try:
        env = dict(os.environ)
        pat = os.environ.get("METABOLISM_MERGE_PAT") or ""
        if pat:
            env["GH_TOKEN"] = pat
        return env
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._heal_pr_create_env: %s", exc)
        return dict(os.environ)


def _run_heal_in_worktree(
    recipe: dict[str, Any],
    main_sha: str,
    *,
    root: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a temp worktree, run heal + verify, commit claim, push, open DRAFT PR.

    Returns a result dict: {success, pr_number, branch, error}.
    NEVER raises.
    """
    result: dict[str, Any] = {"success": False, "pr_number": None, "branch": None, "error": None}
    wt_dir: str | None = None

    try:
        red_class = recipe.get("red_class") or recipe.get("check_name_pattern") or "unknown"
        heal_cmd = recipe.get("heal_cmd") or ""
        detector = recipe.get("detector") or ""
        if not heal_cmd:
            result["error"] = "no heal_cmd in recipe"
            return result

        # Use RUNNER_TEMP if available (house rule: never /tmp)
        runner_temp = os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()
        wt_dir = str(Path(runner_temp) / f"immune-heal-{red_class}-{main_sha[:8]}")

        branch = f"metabolism/immune-heal-{red_class}-{main_sha[:8]}"
        result["branch"] = branch

        if dry_run:
            log.info("IMMUNE [DRY-RUN]: would heal %s branch=%s", red_class, branch)
            result["success"] = True
            return result

        # Gate on pause status BEFORE any git-push or PR-open side-effect.
        # Sensing (ci_status write, insight emission) may still run while paused.
        # Only git-push / PR-open paths are gated — mirrors metabolism_build.py.
        if _is_paused():
            log.info("IMMUNE: AUTONOMY_PAUSED=true — skipping heal push/PR for %s", red_class)
            result["error"] = "paused"
            return result

        # Create worktree off fresh origin/main
        # Clean up any stale worktree at that path
        subprocess.run(
            ["git", "worktree", "remove", "--force", wt_dir],
            cwd=str(root), capture_output=True, timeout=30,
        )
        if Path(wt_dir).exists():
            shutil.rmtree(wt_dir, ignore_errors=True)

        fetch_r = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
        if fetch_r.returncode != 0:
            result["error"] = f"fetch failed: {fetch_r.stderr[:200]}"
            return result

        wt_r = subprocess.run(
            ["git", "worktree", "add", "-b", branch, wt_dir, "origin/main"],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
        if wt_r.returncode != 0:
            result["error"] = f"worktree add failed: {wt_r.stderr[:200]}"
            return result

        wt_path = Path(wt_dir)

        # Run heal command in the worktree
        heal_r = subprocess.run(
            heal_cmd, shell=True, cwd=wt_dir,
            capture_output=True, text=True, timeout=300,
        )
        log.info("IMMUNE: heal_cmd=%r rc=%d stdout=%s", heal_cmd, heal_r.returncode, heal_r.stdout[:200])
        if heal_r.returncode != 0:
            result["error"] = f"heal_cmd failed (rc={heal_r.returncode}): {heal_r.stderr[:300]}"
            _cleanup_worktree(root, wt_dir)
            return result

        # Verify detector now passes
        if detector:
            verify_r = subprocess.run(
                detector, shell=True, cwd=wt_dir,
                capture_output=True, text=True, timeout=120,
            )
            log.info("IMMUNE: detector=%r rc=%d", detector, verify_r.returncode)
            if verify_r.returncode != 0:
                result["error"] = f"detector still fails after heal (rc={verify_r.returncode}): {verify_r.stderr[:300]}"
                _cleanup_worktree(root, wt_dir)
                return result

        # Check if there are any changes to commit
        status_r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=wt_dir, capture_output=True, text=True, timeout=30,
        )
        if not status_r.stdout.strip():
            # No changes — heal was a no-op (maybe already fixed)
            log.info("IMMUNE: heal produced no changes for %s — skipping PR", red_class)
            result["success"] = True
            result["error"] = "no_changes_after_heal"
            _cleanup_worktree(root, wt_dir)
            return result

        # Commit the heal
        subprocess.run(
            ["git", "add", "-A"],
            cwd=wt_dir, capture_output=True, timeout=30,
        )
        commit_msg = (
            f"fix(immune): heal {red_class} on main-sha {main_sha[:8]}\n\n"
            f"Auto-heal by metabolism immune lane (R-V8-1).\n"
            f"red_class: {red_class}\n"
            f"heal_cmd: {heal_cmd}\n"
            f"Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
        )
        commit_r = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=wt_dir, capture_output=True, text=True, timeout=30,
        )
        if commit_r.returncode != 0:
            result["error"] = f"commit failed: {commit_r.stderr[:200]}"
            _cleanup_worktree(root, wt_dir)
            return result

        # Push branch
        push_r = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=wt_dir, capture_output=True, text=True, timeout=60,
        )
        if push_r.returncode != 0:
            result["error"] = f"push failed: {push_r.stderr[:200]}"
            _cleanup_worktree(root, wt_dir)
            return result

        # Open DRAFT PR
        pr_body = (
            f"## Immune system heal: {red_class}\n\n"
            f"Auto-generated by metabolism immune lane (R-V8-1).\n\n"
            f"- `red_class`: {red_class}\n"
            f"- `main_sha`: {main_sha}\n"
            f"- `heal_cmd`: `{heal_cmd}`\n"
            f"- `detector`: `{detector}`\n\n"
            f"This PR was opened automatically after the detector confirmed the heal.\n"
            f"**Auto-merge is DEFERRED this wave (R-V8-3 amended 2026-07-12).**\n"
            f"Operator review and manual merge required.\n"
            f"Auto-merge returns as R-V8-3b (future wave) with the correct re-scan design.\n"
        )
        pr_r = subprocess.run(
            [
                "gh", "pr", "create",
                "--draft",
                "--title", f"fix(immune): heal {red_class} [{main_sha[:8]}]",
                "--body", pr_body,
                "--head", branch,
                "--base", "main",
            ],
            capture_output=True, text=True, timeout=60,
            env=_heal_pr_create_env(),
        )
        if pr_r.returncode != 0:
            result["error"] = f"gh pr create failed: {pr_r.stderr[:300]}"
            _cleanup_worktree(root, wt_dir)
            return result

        # Parse PR number from output URL
        pr_url = pr_r.stdout.strip()
        pr_number = None
        try:
            pr_number = int(pr_url.rstrip("/").split("/")[-1])
        except Exception:  # noqa: BLE001
            pass

        result["success"] = True
        result["pr_number"] = pr_number
        log.info("IMMUNE: heal PR opened: %s (pr_number=%s)", pr_url, pr_number)

    except Exception as exc:  # noqa: BLE001
        log.warning("immune._run_heal_in_worktree: %s", exc)
        result["error"] = str(exc)
    finally:
        if wt_dir and not dry_run:
            _cleanup_worktree(root, wt_dir)

    return result


def _cleanup_worktree(root: Path, wt_dir: str) -> None:
    """Remove the heal worktree.  NEVER raises."""
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", wt_dir],
            cwd=str(root), capture_output=True, timeout=30,
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        if Path(wt_dir).exists():
            shutil.rmtree(wt_dir, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass



# ── CI-status artifact (R-V8-5) ───────────────────────────────────────────────

def write_ci_status(
    main_sha: str,
    red_required: list[dict],
    *,
    root: Path,
    prev_consecutive: int = 0,
) -> bool:
    """Write data/metabolism/ci_status.json.

    Schema matches what anomaly_monitor.py:384 reads:
      { ts, main_sha, red_required, green, consecutive_failures }

    consecutive_failures increments when green=False; resets to 0 when green=True.
    NEVER raises.
    """
    try:
        green = len(red_required) == 0
        consecutive = 0 if green else (prev_consecutive + 1)
        artifact = {
            "ts": _now_utc_str(),
            "main_sha": main_sha,
            "red_required": red_required,
            "green": green,
            "consecutive_failures": consecutive,
        }
        p = root.joinpath(*_CI_STATUS_REL)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.write_ci_status: %s", exc)
        return False


def _read_prev_consecutive(root: Path) -> int:
    """Read the previous consecutive_failures count from ci_status.json.  NEVER raises."""
    try:
        p = root.joinpath(*_CI_STATUS_REL)
        if not p.exists():
            return 0
        data = json.loads(p.read_text(encoding="utf-8"))
        return int(data.get("consecutive_failures") or 0)
    except Exception:  # noqa: BLE001
        return 0


def _now_utc_str() -> str:
    from datetime import datetime, timezone  # noqa: PLC0415
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Lane-health sensors (R-V8-4) ──────────────────────────────────────────────

def _fetch_runs_list() -> list[dict]:
    """Fetch recent workflow runs from gh api.  NEVER raises.

    Uses '.workflow_runs[]' selector so gh emits one dict per line (NDJSON),
    which _gh_json_list always flattens correctly regardless of page count.
    """
    try:
        runs = _gh_json_list([
            "api",
            "/repos/{owner}/{repo}/actions/runs",
            "--jq", ".workflow_runs[]",
            "--paginate",
        ], timeout=90)
        if runs:
            return runs
        # Fallback: plain fetch, extract array from dict response.
        raw = _gh_json([
            "api", "/repos/{owner}/{repo}/actions/runs",
        ], timeout=60)
        if isinstance(raw, dict):
            return raw.get("workflow_runs") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._fetch_runs_list: %s", exc)
    return []


def _fetch_runners_list() -> list[dict]:
    """Fetch self-hosted runners from gh api.  NEVER raises."""
    try:
        raw = _gh_json([
            "api", "/repos/{owner}/{repo}/actions/runners",
        ], timeout=30)
        if isinstance(raw, dict):
            return raw.get("runners") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._fetch_runners_list: %s", exc)
    return []


def _fetch_key_ledger(root: Path) -> dict[str, Any]:
    """Read data/metabolism/key_ledger.jsonl and return a summary dict for check_key_pool_degraded.

    Delegates cooling logic to engine.neuralweb.key_pool.is_cooling (single source
    of truth).  Falls back to local inline logic when the import is unavailable
    (e.g. test environments that stub the path).

    The inline fallback replicates key_pool.is_cooling exactly:
      - A key is cooling iff at least one active horizon remains (reset_hint in
        the future AND not cleared by a later "ok" row for window/auth kinds).
      - "weekly" cool_kind is NEVER cleared by an "ok" row; only reset_hint passage.

    Only capability_id (name) is returned — secret VALUES are never read or returned.
    NEVER raises.
    """
    try:
        ledger_path = root / "data" / "metabolism" / "key_ledger.jsonl"
        if not ledger_path.exists():
            return {"keys": []}

        rows: list[dict] = []
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue

        from datetime import datetime, timezone  # noqa: PLC0415

        # Collect all capability_ids present in the ledger
        all_ids: set[str] = set()
        for row in rows:
            cap_id = row.get("key_id") or row.get("capability_id")
            if cap_id:
                all_ids.add(str(cap_id))

        if not all_ids:
            return {"keys": []}

        def _parse_dt(ts: str) -> datetime | None:
            try:
                if ts.endswith("Z"):
                    ts = ts[:-1] + "+00:00"
                return datetime.fromisoformat(ts).astimezone(timezone.utc)
            except Exception:  # noqa: BLE001
                return None

        def _ts_key(r: dict) -> datetime:
            t = _parse_dt(r.get("ts") or "")
            return t if t else datetime.min.replace(tzinfo=timezone.utc)

        # Try to delegate to key_pool.is_cooling (single source of truth).
        # Guard the import so test environments that don't have the ledger path
        # wired can still run.
        _kp_is_cooling = None
        try:
            from engine.neuralweb.key_pool import is_cooling as _kp_fn  # noqa: PLC0415
            _kp_is_cooling = _kp_fn
        except Exception:  # noqa: BLE001
            pass

        keys_summary: list[dict] = []
        now = datetime.now(timezone.utc)

        for cap_id in sorted(all_ids):
            if _kp_is_cooling is not None:
                cooling_flag = _kp_is_cooling(cap_id, root)
            else:
                # Inline fallback — replicates key_pool.is_cooling clear-by-ok logic.
                # Cooling rows use outcome in ('rate_limited', 'auth_failed').
                cooling_rows = [
                    r for r in rows
                    if (r.get("key_id") or r.get("capability_id")) == cap_id
                    and r.get("outcome") in ("rate_limited", "auth_failed")
                    and r.get("reset_hint")
                ]
                # Also accept stage=="cooling" rows that lack an outcome field
                # (older ledger format written by scripts, not key_pool itself).
                cooling_rows += [
                    r for r in rows
                    if (r.get("key_id") or r.get("capability_id")) == cap_id
                    and r.get("stage") == "cooling"
                    and r.get("outcome") not in ("rate_limited", "auth_failed", "ok")
                    and r.get("reset_hint")
                ]

                cooling_flag = False
                if cooling_rows:
                    ok_ts = [
                        _ts_key(r) for r in rows
                        if (r.get("key_id") or r.get("capability_id")) == cap_id
                        and r.get("outcome") == "ok"
                    ]
                    # Group by cool_kind; evaluate each horizon independently
                    latest_by_kind: dict[str, dict] = {}
                    for r in sorted(cooling_rows, key=_ts_key):
                        latest_by_kind[r.get("cool_kind") or "window"] = r
                    for kind, cool_row in latest_by_kind.items():
                        reset = _parse_dt(cool_row.get("reset_hint") or "")
                        if reset is None:
                            continue  # unparseable hint → resolved
                        if now >= reset:
                            continue  # horizon expired by time
                        if kind != "weekly":
                            cool_ts = _ts_key(cool_row)
                            if any(t >= cool_ts for t in ok_ts):
                                continue  # window/auth cleared by later ok row
                        cooling_flag = True
                        break

            # Name only — never a value
            keys_summary.append({"name": cap_id, "cooling": cooling_flag})

        return {"keys": keys_summary}
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._fetch_key_ledger: %s", exc)
        return {"keys": []}


def run_lane_health_checks(
    immune_cfg: dict[str, Any],
    *,
    root: Path,
    dry_run: bool = False,
) -> list[dict]:
    """Run all lane-health sensors; emit insights + Telegram for new findings.

    Returns list of fired-insight dicts.  NEVER raises.
    """
    from engine.metabolism.immune import (  # noqa: PLC0415
        check_dead_cron, check_queue_stuck,
        check_runner_offline, check_key_pool_degraded,
        has_fired_today, mark_fired_today,
    )
    from engine.metabolism.insight_bus import build_row, append_row  # noqa: PLC0415

    lane_cfg = immune_cfg.get("lane_health") or {}
    cooldown = immune_cfg.get("cooldown") or {}
    fired: list[dict] = []

    try:
        runs = _fetch_runs_list()
        runners = _fetch_runners_list()
        key_ledger = _fetch_key_ledger(root)

        checks: list[tuple[str, dict, str]] = [
            (
                cooldown.get("dead_cron_journal_key") or "immune.lane_health.dead_cron",
                check_dead_cron(runs, lane_cfg),
                "dead-cron lane detected",
            ),
            (
                cooldown.get("queue_stuck_journal_key") or "immune.lane_health.queue_stuck",
                check_queue_stuck(runs, lane_cfg),
                "Actions queue saturation detected",
            ),
            (
                cooldown.get("runner_offline_journal_key") or "immune.lane_health.runner_offline",
                check_runner_offline(runners, lane_cfg),
                "self-hosted runner offline",
            ),
            (
                cooldown.get("key_pool_degraded_journal_key") or "immune.lane_health.key_pool_degraded",
                check_key_pool_degraded(key_ledger, lane_cfg),
                "key-pool partial degradation detected",
            ),
        ]

        for journal_key, result, label in checks:
            if not result.get("found"):
                continue
            if has_fired_today(journal_key, root=root):
                log.info("IMMUNE lane-health: %s already fired today — dedup", journal_key)
                continue
            summary = result.get("summary") or label
            row = build_row(
                emitter="metabolism_immune.lane_health",
                kind="lane_health_alert",
                severity="high",
                entities=["ci", "actions"],
                summary=summary,
                evidence_ref=str(root / "data" / "metabolism" / "ci_status.json"),
            )
            if not dry_run:
                append_row(row, root=root)
                mark_fired_today(journal_key, root=root)
                _notify(f"[Metabolism/Immune] {summary}")
            fired.append(row)

    except Exception as exc:  # noqa: BLE001
        log.warning("immune.run_lane_health_checks: %s", exc)

    return fired


# ── Main sentinel loop ─────────────────────────────────────────────────────────

def run_immune_lane(
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute the immune lane for one run.

    Returns a summary dict.  NEVER raises.
    """
    from engine.metabolism.immune import (  # noqa: PLC0415
        load_immune_config, classify_red,
        has_live_claim_for_class, append_claim,
        has_fired_today, mark_fired_today,
    )
    from engine.metabolism.insight_bus import build_row, append_row  # noqa: PLC0415

    r = root or _ROOT
    summary: dict[str, Any] = {
        "healed": [],
        "unknown_reds": [],
        "lane_health": [],
        "errors": [],
        "sensing_failed": False,
    }

    try:
        immune_cfg = load_immune_config(root=r)

        # Step 1: fetch main SHA and red required checks (union of live main
        # HEAD + the newest concluded ci-main-heartbeat.yml run's head_sha —
        # see _sense_required_red_checks).
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=str(r), capture_output=True, timeout=60,
        )
        main_sha = _get_main_sha()
        if not main_sha:
            log.warning("IMMUNE: could not get main SHA — aborting sentinel")
            print(
                "::error title=immune-sensing-blind::metabolism_immune could not resolve "
                "origin/main HEAD sha — sentinel is BLIND, not green",
                flush=True,
            )
            summary["errors"].append("could not get main SHA")
            summary["sensing_failed"] = True
        else:
            red_checks = _sense_required_red_checks(main_sha, immune_cfg=immune_cfg)
            if red_checks is None:
                # SENSING FAILED — this is BLINDNESS, not "main is clean".  Do NOT
                # write a ci_status.json here: a fabricated green/[] read would
                # repeat the exact 2026-08-17→08-18 incident (a 404 read as
                # red_required=0).  Leave the last real artifact in place and let
                # main() exit non-zero so the run is loud instead of quietly green.
                log.warning(
                    "IMMUNE: sensing FAILED for main_sha=%s — sentinel BLIND, not clean",
                    main_sha[:8],
                )
                print(
                    "::error title=immune-sensing-blind::metabolism_immune could not read "
                    f"check-runs for main_sha={main_sha[:8]} — sentinel is BLIND, not green",
                    flush=True,
                )
                summary["errors"].append("sensing failed: could not read check-runs")
                summary["sensing_failed"] = True
            else:
                log.info("IMMUNE: main_sha=%s red_required=%d", main_sha[:8], len(red_checks))

                # Step 2: write CI-status artifact (R-V8-5) — always, even if no reds
                prev_consecutive = _read_prev_consecutive(r)
                write_ci_status(main_sha, red_checks, root=r, prev_consecutive=prev_consecutive)

                # Step 3: classify and act on each red
                for check in red_checks:
                    check_name = check.get("name") or ""
                    recipe = classify_red(check_name, immune_cfg)

                    if recipe is None:
                        # Unknown red → insight + Telegram, deduped ONCE PER DAY per red-class
                        # (FIX-5: 2h cron must not page the operator on every run for the same red)
                        cooldown = immune_cfg.get("cooldown") or {}
                        unknown_prefix = cooldown.get("unknown_red_journal_prefix") or "immune.unknown_red"
                        # Sanitise check_name for use as a journal-key component
                        safe_name = (check_name or "unknown").replace("/", "_").replace(" ", "_")[:64]
                        journal_key = f"{unknown_prefix}.{safe_name}"
                        if has_fired_today(journal_key, root=r):
                            log.info("IMMUNE: unknown-red page for %r already fired today — dedup", check_name)
                            summary["unknown_reds"].append(check_name)
                            continue
                        row = build_row(
                            emitter="metabolism_immune.sentinel",
                            kind="ci_red_unknown",
                            severity="high",
                            entities=["ci", "main"],
                            summary=f"Unknown CI red on main: {check_name!r} ({check.get('conclusion')})",
                            evidence_ref=check.get("url"),
                        )
                        if not dry_run:
                            append_row(row, root=r)
                            mark_fired_today(journal_key, root=r)
                            _notify(
                                f"[Metabolism/Immune] Unknown CI red on main: {check_name!r} "
                                f"({check.get('conclusion')}) — operator action required"
                            )
                        summary["unknown_reds"].append(check_name)
                        continue

                    red_class = recipe.get("red_class") or recipe.get("check_name_pattern") or "unknown"

                    # Check for live claim (dedup — the three-agents lesson)
                    if has_live_claim_for_class(red_class, root=r, gh_pr_state_fn=_gh_pr_state):
                        log.info("IMMUNE: live claim exists for %s — skipping", red_class)
                        continue

                    # Run heal in fresh worktree
                    heal_result = _run_heal_in_worktree(
                        recipe, main_sha, root=r, dry_run=dry_run,
                    )
                    log.info("IMMUNE: heal result for %s: %s", red_class, heal_result)

                    if not heal_result.get("success"):
                        err = heal_result.get("error") or "unknown error"
                        if err != "no_changes_after_heal":
                            summary["errors"].append(f"{red_class}: {err}")
                            _notify(f"[Metabolism/Immune] Heal failed for {red_class}: {err}")
                        continue

                    pr_number = heal_result.get("pr_number")
                    if pr_number and not dry_run:
                        # Append claim row (R-V8-2)
                        append_claim({
                            "red_class": red_class,
                            "check_name": check_name,
                            "main_sha": main_sha,
                            "pr_number": pr_number,
                        }, root=r)
                        # Auto-merge is DEFERRED (R-V8-3 amended 2026-07-12).
                        # The lane opens the claimed DRAFT heal PR and stops here.
                        # Auto-merge returns as R-V8-3b (future wave).
                        log.info("IMMUNE: heal PR #%s claimed for %s — operator review required", pr_number, red_class)

                    summary["healed"].append({
                        "red_class": red_class,
                        "pr_number": pr_number,
                        "branch": heal_result.get("branch"),
                    })

        # Step 4: lane-health sensors (R-V8-4)
        lh_rows = run_lane_health_checks(immune_cfg, root=r, dry_run=dry_run)
        summary["lane_health"] = [r2.get("summary") for r2 in lh_rows]

    except Exception as exc:  # noqa: BLE001
        log.warning("immune.run_immune_lane: %s", exc)
        summary["errors"].append(str(exc))

    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the IMMUNE lane."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser(
        description="Metabolism V8 IMMUNE lane — CI-red sentinel + lane-health sensors."
    )
    ap.add_argument("--root", default=None, help="Repo root (default: auto-detect).")
    ap.add_argument("--dry-run", action="store_true", help="Describe actions without executing.")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else _ROOT
    result = run_immune_lane(root=root, dry_run=args.dry_run)

    healed = result.get("healed") or []
    unknown = result.get("unknown_reds") or []
    errors = result.get("errors") or []
    lh = result.get("lane_health") or []
    sensing_failed = bool(result.get("sensing_failed"))

    log.info(
        "IMMUNE: complete — healed=%d unknown_reds=%d lane_health=%d errors=%d sensing_failed=%s",
        len(healed), len(unknown), len(lh), len(errors), sensing_failed,
    )
    for e in errors:
        log.warning("IMMUNE error: %s", e)

    # Exit contract (repaired 2026-08-18 — replaces the old unconditional
    # "Exit 0 always / NEVER-RAISE" comment): NEVER-RAISE still holds for every
    # internal function (all catch and return safe fallbacks, nothing here
    # raises), but the PROCESS exit code is no longer unconditionally 0.
    # Finding a red required check is a SUCCESSFUL sensing run — that is the
    # sentinel doing its job — and still exits 0.  Only SENSING ITSELF failing
    # (repo unresolved, or the check-runs read failed at every SHA probed)
    # exits 2.  A blind sentinel that reports "success" is indistinguishable
    # from a healthy one from the outside — that gap is exactly how a dead
    # METABOLISM_MERGE_PAT + a literal "owner/repo" _resolve_repo() fallback
    # let two red required checks (contract-drift, tier-gate) on main run
    # unnoticed for nine days while every 2-hourly scheduled run here logged
    # "success" and metabolism-immune.yml showed green.
    if sensing_failed:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
