"""engine/codex_lane/budget.py — Codex lane usage-state + gate logic (CRX-R4).

Frozen cross-lane API:
    load_cfg(root=None)  -> dict
    load_state(root=None) -> dict
    can_run(root=None, cfg=None) -> tuple[bool, str]
    note_result(run: dict, root=None) -> None

usage_state.json schema (codex_lane.usage_state.v1):
    {
        "schema": "codex_lane.usage_state.v1",
        "updated_at": "<ISO UTC>",
        "rate_limits": {        # latest reported snapshot, or null
            "primary":   {"used_percent": float, "resets_at": str | null} | null,
            "secondary": {"used_percent": float, "resets_at": str | null} | null,
        } | null,
        "token_usage_last": {"input_tokens": int, "output_tokens": int,
                              "total_tokens": int} | null,
        "sessions": [{"ts": "<ISO UTC>", "lane": str, "ok": bool,
                      "error_kind": str | null}],  # last 200
        "paused_until": "<ISO UTC>" | null,
        "degraded": bool,   # true when no rate_limits ever reported
    }

can_run gate (CRX-R4):
    1. paused_until in the future  -> (False, "paused_until:<ts>")
    2. reported primary OR secondary used_percent >= budget_pct
                                   -> (False, "budget:<window>:<pct>%")
    3. degraded mode: count sessions in last 5h >= max_sessions_per_window
                                   -> (False, "session_cap")
    4. else                        -> (True, "ok")

NEVER-RAISE: all public functions catch exceptions internally.
Never log token values.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = "config/codex_lane.yml"
_DEFAULT_STATE_PATH = "data/codex_lane/usage_state.json"

_MAX_SESSIONS_STORED = 200
_DEGRADED_WINDOW_HOURS = 5


# ---------------------------------------------------------------------------
# Hardcoded defaults (mirrors the frozen API contract)
# ---------------------------------------------------------------------------

_CFG_DEFAULTS: dict[str, Any] = {
    "budget_pct": 85,
    "max_sessions_per_window": 10,
    "session_timeout_min": 25,
    "signals_per_run": 5,
    "cases_per_run": 1,
    "case_pr_mode": "draft",
    "codex_model": "",
    "sandbox": "workspace-write",
    "network": True,
}

_STATE_DEFAULTS: dict[str, Any] = {
    "schema": "codex_lane.usage_state.v1",
    "updated_at": "",
    "rate_limits": None,
    "token_usage_last": None,
    "sessions": [],
    "paused_until": None,
    "degraded": True,
}


# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------

def _resolve_root(root: str | Path | None) -> Path:
    if root is not None:
        return Path(root)
    # Walk up from this file to repo root (engine/codex_lane/budget.py)
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# UTC helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        # Python 3.11+ supports fromisoformat with Z; be safe for 3.10/3.12
        ts_clean = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def _to_iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_cfg(root: str | Path | None = None) -> dict:
    """Load config/codex_lane.yml, filling missing keys from hardcoded defaults.

    NEVER raises. Returns defaults on any error.
    """
    try:
        cfg_path = _resolve_root(root) / _DEFAULT_CONFIG_PATH
        if cfg_path.is_file():
            try:
                import yaml  # noqa: PLC0415
            except ImportError:
                yaml = None  # type: ignore[assignment]

            if yaml is not None:
                with cfg_path.open() as fh:
                    data = yaml.safe_load(fh) or {}
            else:
                # Minimal YAML-as-JSON fallback for environments without PyYAML:
                # the config is simple key: value so json may not parse it, but
                # we degrade gracefully to defaults.
                data = {}

            result = dict(_CFG_DEFAULTS)
            result.update({k: v for k, v in data.items() if k in _CFG_DEFAULTS})
            return result
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_lane.budget: load_cfg error: %s — using defaults", exc)
    return dict(_CFG_DEFAULTS)


# ---------------------------------------------------------------------------
# State loader / saver
# ---------------------------------------------------------------------------

def load_state(root: str | Path | None = None) -> dict:
    """Load data/codex_lane/usage_state.json.

    Returns a fresh default state dict when the file is absent or malformed.
    NEVER raises.
    """
    try:
        state_path = _resolve_root(root) / _DEFAULT_STATE_PATH
        if state_path.is_file():
            with state_path.open() as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                # Merge with defaults so new keys are present
                merged = dict(_STATE_DEFAULTS)
                merged.update(raw)
                # Ensure sessions is a list
                if not isinstance(merged.get("sessions"), list):
                    merged["sessions"] = []
                return merged
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_lane.budget: load_state error: %s — using defaults", exc)
    return dict(_STATE_DEFAULTS)


def _save_state(state: dict, root: Path) -> None:
    """Write state to data/codex_lane/usage_state.json. NEVER raises."""
    try:
        state_path = root / _DEFAULT_STATE_PATH
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = _to_iso(_now_utc())
        with state_path.open("w") as fh:
            json.dump(state, fh, indent=2)
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_lane.budget: _save_state error: %s", exc)


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def can_run(
    root: str | Path | None = None,
    cfg: dict | None = None,
) -> tuple[bool, str]:
    """Check whether the lane may start a new Codex session.

    Returns (True, "ok") or (False, "<reason>").
    NEVER raises.
    """
    try:
        if cfg is None:
            cfg = load_cfg(root)
        state = load_state(root)

        budget_pct: float = float(cfg.get("budget_pct", 85))
        max_sessions: int = int(cfg.get("max_sessions_per_window", 10))

        # 1. paused_until check
        paused_until_str = state.get("paused_until") or ""
        if paused_until_str:
            dt = _parse_iso(paused_until_str)
            if dt is not None and dt > _now_utc():
                return False, f"paused_until:{paused_until_str}"

        # 2. Budget check from reported rate_limits
        rl = state.get("rate_limits")
        if rl and not state.get("degraded", True):
            primary = rl.get("primary") or {}
            secondary = rl.get("secondary") or {}
            p_pct = primary.get("used_percent")
            s_pct = secondary.get("used_percent")
            if p_pct is not None and float(p_pct) >= budget_pct:
                return False, f"budget:primary:{p_pct:.1f}%"
            if s_pct is not None and float(s_pct) >= budget_pct:
                return False, f"budget:secondary:{s_pct:.1f}%"

        # 3. Session cap logic
        if state.get("degraded", True):
            # Degraded mode: count all sessions in last 5h, excluding not_installed errors
            sessions: list[dict] = state.get("sessions", [])
            window_start = _now_utc() - timedelta(hours=_DEGRADED_WINDOW_HOURS)
            recent = [
                s for s in sessions
                if _parse_iso(s.get("ts", "")) is not None
                and (_parse_iso(s["ts"]) or datetime.min.replace(tzinfo=timezone.utc)) >= window_start
                and s.get("error_kind") != "not_installed"  # FIX 19(a)
            ]
            if len(recent) >= max_sessions:
                return False, "session_cap"
        else:
            # FIX 19(b) — Non-degraded: if rate_limits has a stale fetched_at (>24h old),
            # also apply session cap as a safety net
            rl = state.get("rate_limits")
            if rl and isinstance(rl, dict):
                fetched_at_str = rl.get("fetched_at", "")
                if fetched_at_str:
                    fetched_at = _parse_iso(fetched_at_str)
                    if fetched_at is not None and (_now_utc() - fetched_at).total_seconds() > 24 * 3600:
                        # Rate limits stale >24h — apply session cap as fallback
                        sessions_nd: list[dict] = state.get("sessions", [])
                        window_start_nd = _now_utc() - timedelta(hours=_DEGRADED_WINDOW_HOURS)
                        recent_nd = [
                            s for s in sessions_nd
                            if _parse_iso(s.get("ts", "")) is not None
                            and (_parse_iso(s["ts"]) or datetime.min.replace(tzinfo=timezone.utc)) >= window_start_nd
                            and s.get("error_kind") != "not_installed"
                        ]
                        if len(recent_nd) >= max_sessions:
                            return False, "session_cap"

        return True, "ok"

    except Exception as exc:  # noqa: BLE001
        log.warning("codex_lane.budget: can_run error: %s — denying (fail-closed)", exc)
        return False, f"error:{exc}"


# ---------------------------------------------------------------------------
# Internal state-update helper (shared between note_result and note_rate_limits)
# ---------------------------------------------------------------------------

def _apply_rate_limits_to_state(state: dict, rl: dict) -> None:
    """Apply a normalized rate-limits dict (from runner) to *state* in place.

    Clears the degraded flag whenever primary or secondary is present and
    non-null.  Trusts the latest reported snapshot over any local estimate
    (CRX-R4).

    If the incoming *rl* dict lacks a truthy ``fetched_at`` key, a copy is
    stored with ``fetched_at`` stamped to the current UTC time so the
    staleness session-cap check (can_run gate step 3) always has a reference
    point.  The caller's dict is never mutated.

    FIX 2 — wrong-account tripwire: if plan_type changes between snapshots,
    log a warning so the operator knows a runner box may be logged into the
    wrong ChatGPT account.  Stores the new plan_type in state["plan_type"].
    """
    # Stamp fetched_at if absent so the >24h staleness check has a reference.
    if not rl.get("fetched_at"):
        rl = dict(rl)  # shallow copy — do not mutate caller's dict
        rl["fetched_at"] = _to_iso(_now_utc())
    state["rate_limits"] = rl
    # Clear degraded if at least one window is reported
    primary = rl.get("primary")
    secondary = rl.get("secondary")
    if primary is not None or secondary is not None:
        state["degraded"] = False

    # FIX 2: plan_type change detection (wrong-account tripwire)
    new_plan_type = rl.get("plan_type")
    if new_plan_type:
        old_plan_type = state.get("plan_type")
        if old_plan_type and old_plan_type != new_plan_type:
            log.warning(
                "codex_lane.budget: plan_type changed %s -> %s"
                " — check that every codex-labeled runner box is logged"
                " into the SAME ChatGPT account",
                old_plan_type,
                new_plan_type,
            )
        state["plan_type"] = new_plan_type


# ---------------------------------------------------------------------------
# note_result
# ---------------------------------------------------------------------------

def note_result(run: dict, root: str | Path | None = None) -> None:
    """Update usage_state.json from the result of a run_codex() call.

    - Appends a session row (keeps last 200).
    - Updates rate_limits and token_usage_last when present (clears degraded).
    - Sets paused_until on usage_limit error_kind.
    - Trusts the latest reported snapshot over local estimates (CRX-R4).

    NEVER raises.
    """
    try:
        resolved_root = _resolve_root(root)
        state = load_state(resolved_root)
        now = _now_utc()

        # Append session row
        session_row: dict = {
            "ts": _to_iso(now),
            "lane": run.get("lane", "unknown"),
            "ok": bool(run.get("ok", False)),
            "error_kind": run.get("error_kind"),
        }
        sessions: list = list(state.get("sessions", []))
        sessions.append(session_row)
        # Trim to last _MAX_SESSIONS_STORED
        if len(sessions) > _MAX_SESSIONS_STORED:
            sessions = sessions[-_MAX_SESSIONS_STORED:]
        state["sessions"] = sessions

        # Update rate_limits and token_usage if reported
        run_rl = run.get("rate_limits")
        if run_rl is not None:
            _apply_rate_limits_to_state(state, run_rl)

        run_usage = run.get("token_usage")
        if run_usage is not None:
            state["token_usage_last"] = run_usage

        # Handle usage_limit: set paused_until
        error_kind = run.get("error_kind")
        if error_kind == "usage_limit":
            # FIX 19(c) — if run's rate_limits is None, use state["rate_limits"] as fallback
            _rl_for_pause = run_rl if run_rl is not None else state.get("rate_limits")
            paused_until = _compute_pause_until(_rl_for_pause, now)
            state["paused_until"] = _to_iso(paused_until)
            log.info(
                "codex_lane.budget: usage_limit hit — pausing until %s",
                state["paused_until"],
            )

        _save_state(state, resolved_root)

    except Exception as exc:  # noqa: BLE001
        log.warning("codex_lane.budget: note_result error: %s", exc)


# ---------------------------------------------------------------------------
# note_rate_limits (frozen cross-lane API)
# ---------------------------------------------------------------------------

def note_rate_limits(rl: dict | None, root: str | Path | None = None) -> None:
    """Update usage_state.json with a fresh rate-limits snapshot.

    Called once per loop iteration by codex_research_loop.py, BEFORE
    budget.can_run(), so the gate always sees the latest reported state.

    - rl None is a no-op (not installed / fetch failed).
    - Otherwise updates state["rate_limits"] and state["updated_at"],
      clears the degraded flag when primary or secondary is non-null.

    FIX 1 — CRX-R4 self-heal: after applying the snapshot, if state still
    has a future paused_until AND the fresh snapshot shows that every present
    window (primary/secondary, skipping None) is below budget_pct, the pause
    was written by a stale/wrong-account signal — clear it and log.

    NEVER raises.
    """
    if rl is None:
        return
    try:
        resolved_root = _resolve_root(root)
        state = load_state(resolved_root)
        _apply_rate_limits_to_state(state, rl)

        # FIX 1: self-heal stale paused_until when fresh snapshot is healthy
        paused_until_str = state.get("paused_until") or ""
        if paused_until_str:
            paused_dt = _parse_iso(paused_until_str)
            if paused_dt is not None and paused_dt > _now_utc():
                cfg = load_cfg(resolved_root)
                budget_pct: float = float(cfg.get("budget_pct", 85))
                primary = (rl.get("primary") or {})
                secondary = (rl.get("secondary") or {})
                p_pct = primary.get("used_percent")
                s_pct = secondary.get("used_percent")
                # Require at least one window to be present (skip None windows)
                present_pcts = [v for v in (p_pct, s_pct) if v is not None]
                if present_pcts and all(float(v) < budget_pct for v in present_pcts):
                    state["paused_until"] = None
                    log.info(
                        "codex_lane.budget: fresh snapshot below budget (%.1f%%)"
                        " — clearing stale paused_until %s",
                        budget_pct,
                        paused_until_str,
                    )

        _save_state(state, resolved_root)
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_lane.budget: note_rate_limits error: %s", exc)


def _compute_pause_until(rate_limits: dict | None, now: datetime) -> datetime:
    """Return the datetime to pause until after a usage_limit hit.

    CRX-R4: use reported resets_at hint when available and in future (wins always).
    When no usable resets_at exists, use the window fallback:
      - secondary-attributed limit (secondary used_percent >= primary, or >= 100):
        now + 7 days (weekly window)
      - primary-attributed or unattributable:
        now + 5 hours (hourly window)
    """
    primary = {}
    secondary = {}
    if rate_limits:
        primary = rate_limits.get("primary") or {}
        secondary = rate_limits.get("secondary") or {}

        # Prefer the reported resets_at when usable
        p_resets = primary.get("resets_at")
        if p_resets:
            dt = _parse_iso(p_resets)
            if dt is not None and dt > now:
                return dt

        s_resets = secondary.get("resets_at")
        if s_resets:
            dt = _parse_iso(s_resets)
            if dt is not None and dt > now:
                return dt

    # No usable resets_at — choose fallback window based on attribution.
    # Secondary-attributed: secondary used_percent >= primary (or secondary is explicitly >=100).
    p_pct = float(primary.get("used_percent") or 0)
    s_pct = float(secondary.get("used_percent") or 0)
    if s_pct >= 100 or (s_pct > 0 and s_pct >= p_pct):
        return now + timedelta(days=7)

    # Primary-attributed or unattributable
    return now + timedelta(hours=5)
