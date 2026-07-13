"""admin/codex_panel.py — Codex Research Engine admin panel.

Reads CODEX_MODE / CODEX_INTERVAL_HOURS / CODEX_LANES from GitHub repo
variables, surfaces usage_state.json, case_attempts.jsonl tail, and
loop_journal.jsonl tail.  All reads are fail-soft.

Pure validators:
  validate_mode_body(body)  -> (ok, errors, to_set)
  validate_run_body(body)   -> (ok, error, inputs)

CRX-R7: CODEX_MODE absent = off (fail-closed for a token-spending lane).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from . import github_api
from .paths import ROOT

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MODE_ALLOWED = {"off", "interval", "auto"}
_LANES_ALLOWED = {"cases", "signals", "both"}
_CODEX_LANE_DIR = ROOT / "data" / "codex_lane"
_CODEX_CONFIG = ROOT / "config" / "codex_lane.yml"

# Hardcoded defaults (mirror engine.codex_lane.budget.load_cfg)
_CFG_DEFAULTS: dict = {
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

# ---------------------------------------------------------------------------
# Internal helpers (fail-soft)
# ---------------------------------------------------------------------------

def _load_cfg() -> dict:
    """Load config/codex_lane.yml; fall back to hardcoded defaults on any error."""
    try:
        import yaml  # noqa: PLC0415
        if _CODEX_CONFIG.exists():
            raw = yaml.safe_load(_CODEX_CONFIG.read_text(encoding="utf-8")) or {}
            merged = dict(_CFG_DEFAULTS)
            merged.update({k: v for k, v in raw.items() if v is not None})
            return merged
    except Exception:  # noqa: BLE001
        pass
    return dict(_CFG_DEFAULTS)


def _load_usage_state() -> dict | None:
    """Load data/codex_lane/usage_state.json; return None on any error."""
    try:
        p = _CODEX_LANE_DIR / "usage_state.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _tail_jsonl(path: Path, n: int) -> list[dict]:
    """Return last n parsed lines of a .jsonl file; fail-soft (empty list)."""
    try:
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
            if len(rows) >= n:
                break
        rows.reverse()
        return rows
    except Exception:  # noqa: BLE001
        return []


def _recent_codex_runs(cap: int = 10) -> list[dict]:
    """Fetch recent workflow runs filtered to codex-research workflow."""
    try:
        result = github_api.list_runs(per_page=50)
        if not result.get("ok"):
            return []
        runs = result.get("runs") or []
        filtered = []
        for r in runs:
            wf_path = (r.get("workflow") or "").lower()
            wf_name = (r.get("name") or "").lower()
            if "codex-research" in wf_path or "codex-research" in wf_name:
                filtered.append({
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "status": r.get("status"),
                    "conclusion": r.get("conclusion"),
                    "created_at": r.get("created_at"),
                    "html_url": r.get("html_url"),
                })
            if len(filtered) >= cap:
                break
        return filtered
    except Exception:  # noqa: BLE001
        return []


def _derive_usage(raw: dict | None, budget_pct: int) -> dict | None:
    """Derive display fields from usage_state.json contents.

    Returns None when raw is None.  Adds:
      primary_used_pct   — float or None
      secondary_used_pct — float or None
      paused_until       — str or None
      degraded           — bool
      budget_pct         — int (from config)
    """
    if raw is None:
        return None
    out = dict(raw)
    # primary window
    pri = (raw.get("rate_limits") or {}).get("primary") or {}
    out["primary_used_pct"] = pri.get("used_percent")
    # secondary window
    sec = (raw.get("rate_limits") or {}).get("secondary") or {}
    out["secondary_used_pct"] = sec.get("used_percent")
    # paused_until from top-level
    out["paused_until"] = raw.get("paused_until")
    # degraded = no reported usage data
    out["degraded"] = (out["primary_used_pct"] is None and out["secondary_used_pct"] is None)
    out["budget_pct"] = budget_pct
    return out


# ---------------------------------------------------------------------------
# Pure validators
# ---------------------------------------------------------------------------

def validate_mode_body(body: dict) -> tuple[bool, dict, dict]:
    """Validate POST /api/codex/mode body.

    Returns (ok, errors, to_set) where to_set maps variable names to values.
    Accepted fields: mode, interval_hours, lanes (all optional individually).
    """
    errors: dict[str, str] = {}
    to_set: dict[str, str] = {}

    if "mode" in body:
        v = body["mode"]
        if v not in _MODE_ALLOWED:
            errors["mode"] = f"mode must be one of {sorted(_MODE_ALLOWED)}, got {v!r}"
        else:
            to_set["CODEX_MODE"] = v

    if "interval_hours" in body:
        raw = body["interval_hours"]
        try:
            iv = int(raw)
        except (TypeError, ValueError):
            errors["interval_hours"] = f"interval_hours must be an integer, got {raw!r}"
            iv = None
        if iv is not None and not (1 <= iv <= 48):
            errors["interval_hours"] = f"interval_hours must be 1..48, got {iv}"
        elif iv is not None and "interval_hours" not in errors:
            to_set["CODEX_INTERVAL_HOURS"] = str(iv)

    if "lanes" in body:
        v = body["lanes"]
        if v not in _LANES_ALLOWED:
            errors["lanes"] = f"lanes must be one of {sorted(_LANES_ALLOWED)}, got {v!r}"
        else:
            to_set["CODEX_LANES"] = v

    return (len(errors) == 0, errors, to_set)


def validate_run_body(body: dict) -> tuple[bool, str | None, dict]:
    """Validate POST /api/codex/run body.

    Returns (ok, error, inputs) where inputs is the workflow dispatch inputs dict.
    Required: lane ∈ {cases, signals, both}.
    Optional: iterations (int 1..20).
    """
    lane = body.get("lane")
    if lane not in _LANES_ALLOWED:
        return (False, f"lane must be one of {sorted(_LANES_ALLOWED)}, got {lane!r}", {})

    inputs: dict[str, str] = {"lane": lane}

    if "iterations" in body:
        raw = body["iterations"]
        try:
            it = int(raw)
        except (TypeError, ValueError):
            return (False, f"iterations must be an integer, got {raw!r}", {})
        if not (1 <= it <= 20):
            return (False, f"iterations must be 1..20, got {it}", {})
        inputs["iterations"] = str(it)

    return (True, None, inputs)


# ---------------------------------------------------------------------------
# Main panel function
# ---------------------------------------------------------------------------

def panel(root: Path | None = None) -> dict:  # noqa: ARG001  (root unused; kept for test injection)
    """Return the Codex Research panel data dict.

    Keys:
      mode            — {value, effective, allowed}
      interval_hours  — {value, effective}
      lanes           — {value, effective, allowed}
      usage           — contents of usage_state.json with derived fields, or None
      attempts        — last 10 rows of case_attempts.jsonl
      loop            — last 5 rows of loop_journal.jsonl
      runs            — recent codex-research workflow runs (up to 10)

    Never raises.
    """
    try:
        cfg = _load_cfg()
        budget_pct: int = int(cfg.get("budget_pct") or _CFG_DEFAULTS["budget_pct"])

        # Read repo variables (fail-soft — each returns None when absent/error)
        mode_raw = github_api.get_repo_variable("CODEX_MODE")
        interval_raw = github_api.get_repo_variable("CODEX_INTERVAL_HOURS")
        lanes_raw = github_api.get_repo_variable("CODEX_LANES")

        # Effective values (CRX-R7: absent = off for mode)
        effective_mode = mode_raw if mode_raw in _MODE_ALLOWED else "off"
        try:
            effective_interval = int(interval_raw) if interval_raw is not None else 6
        except (TypeError, ValueError):
            effective_interval = 6
        effective_lanes = lanes_raw if lanes_raw in _LANES_ALLOWED else "both"

        # Usage state
        raw_usage = _load_usage_state()
        usage = _derive_usage(raw_usage, budget_pct)

        # Data file tails
        attempts = _tail_jsonl(_CODEX_LANE_DIR / "case_attempts.jsonl", 10)
        loop = _tail_jsonl(_CODEX_LANE_DIR / "loop_journal.jsonl", 5)

        # Workflow runs
        runs = _recent_codex_runs()

        return {
            "mode": {
                "value": mode_raw,
                "effective": effective_mode,
                "allowed": sorted(_MODE_ALLOWED),
            },
            "interval_hours": {
                "value": interval_raw,
                "effective": effective_interval,
            },
            "lanes": {
                "value": lanes_raw,
                "effective": effective_lanes,
                "allowed": sorted(_LANES_ALLOWED),
            },
            "usage": usage,
            "attempts": attempts,
            "loop": loop,
            "runs": runs,
        }
    except Exception as exc:  # noqa: BLE001
        _log.warning("codex_panel.panel error: %s", exc)
        return {
            "mode": {"value": None, "effective": "off", "allowed": sorted(_MODE_ALLOWED)},
            "interval_hours": {"value": None, "effective": 6},
            "lanes": {"value": None, "effective": "both", "allowed": sorted(_LANES_ALLOWED)},
            "usage": None,
            "attempts": [],
            "loop": [],
            "runs": [],
        }
