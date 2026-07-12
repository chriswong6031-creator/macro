"""engine.metabolism.immune — Immune system pure logic (R-V8-1..R-V8-5).

Pure functions only.  NEVER-RAISE contract (mirrors anomaly_monitor.py).
No subprocess calls, no network, no git.  All side-effecting actions live
in scripts/metabolism_immune.py — this module is fully testable without mocks.

PUBLIC API
----------
classify_red(check_name, registry)          → red_class dict | None
append_claim(claim, root)                    → bool
live_claims(root, gh_pr_state_fn)           → list[dict]
check_dead_cron(runs_list, cfg)             → dict
check_queue_stuck(runs_list, cfg)           → dict
check_runner_offline(runners_list, cfg)     → dict
check_key_pool_degraded(key_ledger, cfg)    → dict
load_immune_config(root)                    → dict
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

_IMMUNE_CONFIG_PATH = Path("config") / "metabolism_immune.yml"
_CLAIMS_REL = ("data", "metabolism", "immune_claims.jsonl")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ── Config ────────────────────────────────────────────────────────────────────

def load_immune_config(root: Path | None = None) -> dict[str, Any]:
    """Load config/metabolism_immune.yml.  Returns {} on any failure (fail-open).

    NEVER-RAISE.
    """
    try:
        r = _repo_root(root)
        p = r / _IMMUNE_CONFIG_PATH
        if not p.exists():
            log.warning("immune: config not found at %s", p)
            return {}
        import yaml  # noqa: PLC0415
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.load_immune_config: %s", exc)
        return {}


# ── Classification ─────────────────────────────────────────────────────────────

def classify_red(
    check_name: str,
    registry: dict[str, Any],
) -> dict[str, Any] | None:
    """Match a failing check name against the recipe registry.

    Returns the matching recipe dict (with an added 'red_class' key derived
    from check_name_pattern) if a match is found, or None for unknown reds.

    NEVER-RAISE.
    """
    try:
        recipes = registry.get("recipes") or []
        check_lower = (check_name or "").lower()
        for recipe in recipes:
            pattern = str(recipe.get("check_name_pattern") or "").lower()
            if pattern and pattern in check_lower:
                return {**recipe, "red_class": recipe["check_name_pattern"]}
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.classify_red: %s", exc)
        return None


# ── Claims ────────────────────────────────────────────────────────────────────

def append_claim(
    claim: dict[str, Any],
    root: Path | None = None,
) -> bool:
    """Append one claim row to data/metabolism/immune_claims.jsonl.

    Expected keys: red_class, check_name, main_sha, pr_number, ts.
    Returns True on success.  NEVER-RAISE.
    """
    try:
        r = _repo_root(root)
        claims_path = r.joinpath(*_CLAIMS_REL)
        claims_path.parent.mkdir(parents=True, exist_ok=True)
        row = {**claim, "ts": claim.get("ts") or _now_utc()}
        with claims_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.append_claim: %s", exc)
        return False


def _load_raw_claims(root: Path) -> list[dict]:
    """Load all raw rows from immune_claims.jsonl.  NEVER-RAISE."""
    try:
        path = root.joinpath(*_CLAIMS_REL)
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("immune._load_raw_claims: %s", exc)
        return []


def live_claims(
    root: Path | None = None,
    gh_pr_state_fn: Callable[[int], str] | None = None,
) -> list[dict]:
    """Return claims whose PR is still live.

    A claim is LIVE unless its PR state is definitively CLOSED or MERGED.
    Any other state — including 'OPEN', 'unknown', or transient gh-API blips —
    keeps the claim live (fail-closed: never open a duplicate heal PR because
    of a transient gh response).

    gh_pr_state_fn(pr_number) -> state string ('OPEN'|'CLOSED'|'MERGED'|'unknown').
    If gh_pr_state_fn is None, all claims with a pr_number > 0 are assumed live
    (conservative — avoids false "no live claim" when gh is unavailable).

    NEVER-RAISE.
    """
    # States that definitively expire a claim.  Any other state (OPEN, unknown,
    # transient error) keeps the claim live — fail-closed contract.
    _EXPIRED_STATES = {"CLOSED", "MERGED"}

    try:
        r = _repo_root(root)
        rows = _load_raw_claims(r)
        live: list[dict] = []
        for row in rows:
            pr_num = row.get("pr_number")
            if not pr_num:
                continue
            if gh_pr_state_fn is None:
                # Conservatively treat as live
                live.append(row)
                continue
            try:
                state = str(gh_pr_state_fn(int(pr_num))).upper()
                if state not in _EXPIRED_STATES:
                    # Includes OPEN, unknown, empty, or any transient state
                    live.append(row)
            except Exception as exc:  # noqa: BLE001
                log.warning("immune.live_claims: gh_pr_state_fn(%s) failed: %s — treating as live",
                             pr_num, exc)
                live.append(row)
        return live
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.live_claims: %s", exc)
        return []


def has_live_claim_for_class(
    red_class: str,
    root: Path | None = None,
    gh_pr_state_fn: Callable[[int], str] | None = None,
) -> bool:
    """Return True if there is already a live claim for the given red_class.

    NEVER-RAISE.
    """
    try:
        claims = live_claims(root=root, gh_pr_state_fn=gh_pr_state_fn)
        return any(c.get("red_class") == red_class for c in claims)
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.has_live_claim_for_class: %s", exc)
        return False


# ── Lane-health evaluators (pure — take pre-fetched JSON, return insight dicts) ─

def check_dead_cron(
    runs_list: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Detect cron lanes whose latest run concluded cancelled/timed_out.

    Parameters
    ----------
    runs_list:
        Pre-fetched list of workflow run dicts.  Each dict is expected to have:
          - name        : workflow name
          - event       : trigger event ('schedule' | ...)
          - conclusion  : 'cancelled'|'timed_out'|'success'|'failure'|...
          - status      : 'completed'|'in_progress'|'queued'|...
        (mirrors `gh api /repos/{owner}/{repo}/actions/runs` items)
    cfg:
        Lane-health config dict (from metabolism_immune.yml:lane_health).

    Returns dict with:
        found: bool
        dead_lanes: list[str]   — workflow names that fired the detector
        summary: str
    NEVER-RAISE.
    """
    try:
        bad = cfg.get("dead_cron_conclusions") or ["cancelled", "timed_out"]
        bad_set = {str(c).lower() for c in bad}

        # Only look at schedule-triggered runs; keep the LATEST run per workflow name
        latest: dict[str, dict] = {}
        for run in (runs_list or []):
            if run.get("event") != "schedule":
                continue
            name = run.get("name") or run.get("workflow_id") or "unknown"
            # Assume runs_list is sorted latest-first (gh api default); keep first seen per name
            if name not in latest:
                latest[name] = run

        dead: list[str] = []
        for name, run in latest.items():
            conclusion = str(run.get("conclusion") or "").lower()
            if conclusion in bad_set:
                dead.append(name)

        return {
            "found": bool(dead),
            "dead_lanes": dead,
            "summary": (
                f"dead-cron: {len(dead)} lane(s) with conclusion in {sorted(bad_set)}: {dead}"
                if dead else "dead-cron: all checked cron lanes OK"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.check_dead_cron: %s", exc)
        return {"found": False, "dead_lanes": [], "summary": f"dead-cron check error: {exc}"}


def check_queue_stuck(
    runs_list: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Detect Actions queue saturation (runs queued > queue_stuck_min minutes).

    Parameters
    ----------
    runs_list:
        Pre-fetched list of workflow run dicts with at minimum:
          - status      : 'queued'|'in_progress'|'completed'
          - created_at  : ISO-8601 timestamp
          - name        : workflow name
    cfg:
        Lane-health config dict.

    Returns dict with:
        found: bool
        stuck_count: int
        stuck_runs: list[str]   — run names / ids
        summary: str
    NEVER-RAISE.
    """
    try:
        threshold_min = int(cfg.get("queue_stuck_min") or 40)
        now = datetime.now(timezone.utc)

        stuck: list[str] = []
        for run in (runs_list or []):
            if str(run.get("status") or "").lower() != "queued":
                continue
            created_raw = run.get("created_at") or ""
            if not created_raw:
                continue
            try:
                created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                queued_min = (now - created).total_seconds() / 60.0
                if queued_min > threshold_min:
                    label = run.get("name") or str(run.get("id") or "unknown")
                    stuck.append(f"{label} ({queued_min:.0f}m)")
            except Exception:  # noqa: BLE001
                continue

        return {
            "found": bool(stuck),
            "stuck_count": len(stuck),
            "stuck_runs": stuck,
            "summary": (
                f"queue-stuck: {len(stuck)} run(s) queued >{threshold_min}min: {stuck}"
                if stuck else f"queue-stuck: no runs queued >{threshold_min}min"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.check_queue_stuck: %s", exc)
        return {"found": False, "stuck_count": 0, "stuck_runs": [], "summary": f"queue-stuck check error: {exc}"}


def check_runner_offline(
    runners_list: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Detect self-hosted runners with status != online.

    Parameters
    ----------
    runners_list:
        Pre-fetched list of runner dicts with at minimum:
          - name    : runner name
          - status  : 'online'|'offline'
    cfg:
        Lane-health config dict.

    Returns dict with:
        found: bool
        offline_runners: list[str]
        summary: str
    NEVER-RAISE.
    """
    try:
        offline: list[str] = []
        for runner in (runners_list or []):
            if str(runner.get("status") or "").lower() != "online":
                offline.append(str(runner.get("name") or "unknown"))

        return {
            "found": bool(offline),
            "offline_runners": offline,
            "summary": (
                f"runner-offline: {len(offline)} runner(s) offline: {offline}"
                if offline else "runner-offline: all runners online"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.check_runner_offline: %s", exc)
        return {"found": False, "offline_runners": [], "summary": f"runner-offline check error: {exc}"}


def check_key_pool_degraded(
    key_ledger: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Detect >50% key-pool degradation (keys cooling).

    Parameters
    ----------
    key_ledger:
        Pre-fetched dict with key pool state.  Expected shape:
          { "keys": [{"name": "...", "cooling": bool, ...}, ...] }
        or an iterable of key records.  Only key NAMES are read — never secret values.
    cfg:
        Lane-health config dict.

    Returns dict with:
        found: bool
        cooling_count: int
        total_count: int
        cooling_fraction: float
        summary: str
    NEVER-RAISE.
    """
    try:
        threshold = float(cfg.get("key_pool_degraded_fraction") or 0.5)
        keys = key_ledger.get("keys") or [] if isinstance(key_ledger, dict) else []
        if not keys:
            return {
                "found": False,
                "cooling_count": 0,
                "total_count": 0,
                "cooling_fraction": 0.0,
                "summary": "key-pool: no keys in ledger",
            }

        total = len(keys)
        cooling = sum(1 for k in keys if k.get("cooling"))
        fraction = cooling / total if total > 0 else 0.0
        # Only report key NAMES, never values
        cooling_names = [str(k.get("name") or "unknown") for k in keys if k.get("cooling")]

        found = fraction >= threshold
        return {
            "found": found,
            "cooling_count": cooling,
            "total_count": total,
            "cooling_fraction": round(fraction, 3),
            "summary": (
                f"key-pool: {cooling}/{total} keys cooling ({fraction:.0%}) — "
                f"DEGRADED (>{threshold:.0%} threshold): {cooling_names}"
                if found else
                f"key-pool: {cooling}/{total} keys cooling ({fraction:.0%}) — OK"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.check_key_pool_degraded: %s", exc)
        return {
            "found": False, "cooling_count": 0, "total_count": 0,
            "cooling_fraction": 0.0, "summary": f"key-pool check error: {exc}",
        }


# ── Daily-dedup journal ────────────────────────────────────────────────────────

def has_fired_today(journal_key: str, root: Path | None = None) -> bool:
    """Return True if journal_key was already recorded for today (UTC).

    NEVER-RAISE.
    """
    try:
        r = _repo_root(root)
        journal_dir = r / "data" / "metabolism" / "immune"
        today = _today_utc()
        marker = journal_dir / f"{journal_key}.{today}.fired"
        return marker.exists()
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.has_fired_today: %s", exc)
        return False


def mark_fired_today(journal_key: str, root: Path | None = None) -> bool:
    """Record that journal_key fired today (UTC).  NEVER-RAISE."""
    try:
        r = _repo_root(root)
        journal_dir = r / "data" / "metabolism" / "immune"
        journal_dir.mkdir(parents=True, exist_ok=True)
        today = _today_utc()
        marker = journal_dir / f"{journal_key}.{today}.fired"
        marker.write_text(today, encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.mark_fired_today: %s", exc)
        return False


# ── Automerge daily cap (journal-durable) ─────────────────────────────────────

def _automerge_count_path(root: Path) -> Path:
    today = _today_utc()
    return root / "data" / "metabolism" / "immune" / f"automerge_count.{today}.json"


def get_automerge_count_today(root: Path | None = None) -> int:
    """Return how many heal PRs were auto-merged today.  NEVER-RAISE."""
    try:
        r = _repo_root(root)
        p = _automerge_count_path(r)
        if not p.exists():
            return 0
        data = _read_json(p)
        return int((data or {}).get("count") or 0)
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.get_automerge_count_today: %s", exc)
        return 0


def increment_automerge_count(root: Path | None = None) -> int:
    """Increment the journal-durable daily auto-merge counter.  Returns new count.  NEVER-RAISE."""
    try:
        r = _repo_root(root)
        p = _automerge_count_path(r)
        p.parent.mkdir(parents=True, exist_ok=True)
        current = get_automerge_count_today(root=r)
        new_count = current + 1
        p.write_text(json.dumps({"count": new_count, "date": _today_utc()}), encoding="utf-8")
        return new_count
    except Exception as exc:  # noqa: BLE001
        log.warning("immune.increment_automerge_count: %s", exc)
        return 0
