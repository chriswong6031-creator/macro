"""admin/live_runs.py — Real-time workflow run snapshot for the admin console.

snapshot() returns a dict with three scopes (metabolism, codex, nightly) each
carrying active/queued/last_completed sub-dicts built from the GitHub Actions
runs API, plus a mastermind_bot reachability probe.

Design constraints:
- Never raises: every failure path returns a partial or empty result.
- API budget: at most 2 run_jobs() calls per snapshot() invocation
  (only the 2 most recent in_progress runs across all scopes combined).
- No token values in logs or payloads.
- Module logger (no print).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from . import github_api
from .paths import ROOT

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Workflow name sets per scope (filenames as returned by _slim_run's "workflow"
# field — the path after stripping ".github/workflows/").
# ---------------------------------------------------------------------------
_METABOLISM_WORKFLOWS = frozenset({
    "metabolism-cycle.yml",
    "metabolism-agenda.yml",
    "metabolism-propose.yml",
    "metabolism-adjudicate.yml",
    "metabolism-build.yml",
})
_METABOLISM_PRIMARY = "metabolism-cycle.yml"

_CODEX_WORKFLOWS = frozenset({"codex-research.yml"})
_CODEX_PRIMARY = "codex-research.yml"

_NIGHTLY_WORKFLOWS = frozenset({"daily.yml"})
_NIGHTLY_PRIMARY = "daily.yml"

# Bot probe cache: re-probe at most every 120 seconds.
_BOT_PROBE_CACHE: dict | None = None  # {result: bool, checked_at: str}
_BOT_PROBE_INTERVAL_S = 120

# Path to heartbeat log.
_HEARTBEAT_PATH = ROOT / "data" / "metabolism" / "heartbeat.jsonl"

# How many recent runs to fetch from the API (one page).
_RUNS_CAP = 30

# Maximum in_progress runs that get a jobs() call across ALL scopes combined.
_JOBS_BUDGET = 2

# Default mastermind bot base URL.
_DEFAULT_BOT_BASE = "http://127.0.0.1:8000"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _elapsed_s(run: dict, now: datetime) -> float | None:
    """Seconds since a run started; None if the timestamp is absent or unparseable."""
    raw = run.get("run_started_at") or run.get("created_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (now - dt).total_seconds())
    except Exception:  # noqa: BLE001
        return None


def _duration_s(run: dict) -> float | None:
    """Duration for a completed run (updated_at - created_at); None if absent."""
    created_raw = run.get("created_at")
    updated_raw = run.get("updated_at")
    if not (created_raw and updated_raw):
        return None
    try:
        t0 = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        if t1.tzinfo is None:
            t1 = t1.replace(tzinfo=timezone.utc)
        return max(0.0, (t1 - t0).total_seconds())
    except Exception:  # noqa: BLE001
        return None


def _split_runs(runs: list[dict], workflows: frozenset[str], primary: str,
                now: datetime) -> tuple[list[dict], list[dict], dict | None]:
    """Split a flat run list into (active, queued, last_completed) for a scope.

    active  — in_progress runs (with elapsed_s attached); newest first.
    queued  — queued runs; newest first.
    last_completed — the single most recent completed run for the PRIMARY
                     workflow of the scope (None if absent); filtered to
                     *primary* so stage workflows do not shadow the main
                     loop entry; includes conclusion + duration_s + html_url.
    """
    active: list[dict] = []
    queued: list[dict] = []
    last_completed: dict | None = None

    for r in runs:
        if r.get("workflow") not in workflows:
            continue
        status = r.get("status")
        if status == "in_progress":
            enriched = dict(r)
            enriched["elapsed_s"] = _elapsed_s(r, now)
            active.append(enriched)
        elif status == "queued":
            queued.append(r)
        elif status == "completed" and last_completed is None:
            # Only the primary workflow counts as "last loop" to avoid
            # a short stage workflow shadowing the main cycle completion.
            if r.get("workflow") == primary:
                last_completed = {
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "workflow": r.get("workflow"),
                    "conclusion": r.get("conclusion"),
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                    "html_url": r.get("html_url"),
                    "duration_s": _duration_s(r),
                }

    return active, queued, last_completed


def _read_last_heartbeat() -> dict | None:
    """Return the last valid JSON line from heartbeat.jsonl, or None."""
    try:
        import json  # noqa: PLC0415
        path = Path(_HEARTBEAT_PATH)
        if not path.is_file():
            return None
        last: dict | None = None
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                    if isinstance(obj, dict):
                        last = obj
                except Exception:  # noqa: BLE001
                    pass  # skip malformed lines
        return last
    except Exception:  # noqa: BLE001
        return None


def _probe_bot(base: str) -> bool:
    """GET {base}/api/mastermind_ai with a 2s timeout.

    Returns True only on HTTP 200. Any error, timeout, or non-200 → False.
    Never logs or includes token values.
    """
    try:
        import requests as _req  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return False
    url = f"{base.rstrip('/')}/api/mastermind_ai"
    try:
        resp = _req.get(url, timeout=2)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def snapshot(root: Path | None = None) -> dict:
    """Build a live-run snapshot.

    Args:
        root: override for the data root (used in tests). Ignored currently —
              heartbeat path is module-level, but kept for future callers.

    Returns a dict:
    {
        ts: ISO-8601 UTC timestamp of this snapshot,
        metabolism: {active, queued, last_completed, heartbeat},
        codex:      {active, queued, last_completed},
        nightly:    {active, queued, last_completed},
        mastermind_bot: {base, reachable, checked_at},
    }

    Never raises; all failures degrade to empty lists / None.
    """
    now = _now_utc()
    ts = now.isoformat()

    # --- fetch all recent runs in one page ---
    all_runs: list[dict] = []
    try:
        result = github_api.list_runs(per_page=_RUNS_CAP)
        if result.get("ok"):
            all_runs = result.get("runs") or []
    except Exception:  # noqa: BLE001
        pass

    # --- split by scope ---
    metab_active, metab_queued, metab_last = _split_runs(
        all_runs, _METABOLISM_WORKFLOWS, _METABOLISM_PRIMARY, now)
    codex_active, codex_queued, codex_last = _split_runs(
        all_runs, _CODEX_WORKFLOWS, _CODEX_PRIMARY, now)
    nightly_active, nightly_queued, nightly_last = _split_runs(
        all_runs, _NIGHTLY_WORKFLOWS, _NIGHTLY_PRIMARY, now)

    # --- budget the jobs API calls (at most _JOBS_BUDGET across all scopes) ---
    # Collect the 2 most recent in_progress runs from all scopes, newest first.
    all_active_ordered: list[dict] = []
    for scope_active in (metab_active, codex_active, nightly_active):
        all_active_ordered.extend(scope_active)
    # Sort by run_started_at descending (most recent first).
    def _sort_key(r: dict) -> str:
        return r.get("run_started_at") or r.get("created_at") or ""
    all_active_ordered.sort(key=_sort_key, reverse=True)
    runs_to_fetch_jobs = {r["id"] for r in all_active_ordered[:_JOBS_BUDGET]
                          if r.get("id") is not None}

    def _maybe_add_jobs(run: dict) -> dict:
        if run.get("id") in runs_to_fetch_jobs:
            try:
                run = dict(run)
                run["jobs"] = github_api.run_jobs(run["id"])
            except Exception:  # noqa: BLE001
                pass
        return run

    metab_active = [_maybe_add_jobs(r) for r in metab_active]
    codex_active = [_maybe_add_jobs(r) for r in codex_active]
    nightly_active = [_maybe_add_jobs(r) for r in nightly_active]

    # --- heartbeat ---
    heartbeat: dict | None = None
    try:
        heartbeat = _read_last_heartbeat()
    except Exception:  # noqa: BLE001
        pass

    # --- mastermind bot probe (cached; re-probe at most every 120 s) ---
    global _BOT_PROBE_CACHE
    bot_base = (os.environ.get("MASTERMIND_BOT_BASE", "").strip()
                or _DEFAULT_BOT_BASE).rstrip("/")
    bot_reachable = False
    bot_checked_at = now.isoformat()
    try:
        cache = _BOT_PROBE_CACHE
        needs_probe = True
        if cache is not None:
            try:
                age_s = (now - datetime.fromisoformat(
                    cache["checked_at"].replace("Z", "+00:00")
                )).total_seconds()
                if age_s < _BOT_PROBE_INTERVAL_S:
                    needs_probe = False
                    bot_reachable = cache["result"]
                    bot_checked_at = cache["checked_at"]
            except Exception:  # noqa: BLE001
                needs_probe = True
        if needs_probe:
            bot_checked_at = now.isoformat()
            try:
                bot_reachable = _probe_bot(bot_base)
            except Exception:  # noqa: BLE001
                bot_reachable = False
            _BOT_PROBE_CACHE = {"result": bot_reachable, "checked_at": bot_checked_at}
    except Exception:  # noqa: BLE001
        pass

    return {
        "ts": ts,
        "metabolism": {
            "active": metab_active,
            "queued": metab_queued,
            "last_completed": metab_last,
            "heartbeat": heartbeat,
        },
        "codex": {
            "active": codex_active,
            "queued": codex_queued,
            "last_completed": codex_last,
        },
        "nightly": {
            "active": nightly_active,
            "queued": nightly_queued,
            "last_completed": nightly_last,
        },
        "mastermind_bot": {
            "base": bot_base,
            "reachable": bot_reachable,
            "checked_at": bot_checked_at,
        },
    }
