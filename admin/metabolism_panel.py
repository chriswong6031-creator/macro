"""admin/metabolism_panel.py — Metabolism loop status panel.

Reads the AUTONOMY_PAUSED repository variable via the GitHub API, summarises
recent metabolism workflow runs, and reports on local organism state and key
pool health.  Every read is fail-soft: a missing file, absent token, or broken
engine import degrades gracefully to None / a note string rather than raising.

Pause semantics mirror scripts/metabolism_guard.py exactly:
    ONLY the exact string "false" means ARMED.
    Unset / empty / "true" / anything else means PAUSED.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import github_api
from .paths import ROOT

_VAR_NAME = "AUTONOMY_PAUSED"
_ARMED_VALUE = "false"

# Metabolism data directory
_MET_DIR = ROOT / "data" / "metabolism"


def _armed_state(variable_value: str | None) -> tuple[bool, str]:
    """Return (armed: bool, state: str) from a raw variable value.

    state is one of: "armed" | "paused" | "unknown"
    """
    if variable_value is None:
        return False, "unknown"
    if variable_value == _ARMED_VALUE:
        return True, "armed"
    return False, "paused"


def _recent_metabolism_runs(cap: int = 15) -> list[dict]:
    """Fetch recent workflow runs and filter to metabolism workflows."""
    try:
        result = github_api.list_runs(per_page=50)
        if not result.get("ok"):
            return []
        runs = result.get("runs") or []
        filtered = []
        for r in runs:
            wf_name = (r.get("name") or "").lower()
            wf_path = (r.get("workflow") or "").lower()
            if "metabolism" in wf_name or "metabolism" in wf_path:
                filtered.append({
                    "name": r.get("name"),
                    "workflow": r.get("workflow"),
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


def _organism_summary() -> dict | None:
    """Fail-soft summary of data/metabolism/organism_state.json."""
    try:
        p = _MET_DIR / "organism_state.json"
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        # Surface top-level scalar fields and gaps count
        scalars = {k: v for k, v in raw.items()
                   if isinstance(v, (str, int, float, bool)) or v is None}
        gaps = raw.get("gaps")
        if isinstance(gaps, list):
            scalars["gaps_count"] = len(gaps)
        elif isinstance(gaps, dict):
            scalars["gaps_count"] = len(gaps)
        return scalars
    except Exception:  # noqa: BLE001
        return None


def _key_health(root: Path | None = None) -> list[dict] | str:
    """Per-pool key health from key_pool.  Returns list of rows or a note string."""
    try:
        from engine.neuralweb.key_pool import (  # type: ignore[import]
            POOL_CAPABILITY_IDS,
            _read_ledger,
            is_cooling,
            window_load,
        )

        effective_root = root or ROOT
        rows = _read_ledger(effective_root)

        results = []
        for cap_id in POOL_CAPABILITY_IDS:
            # Last ledger row for this key
            key_rows = [r for r in rows if r.get("key_id") == cap_id]
            last_outcome = None
            last_ts = None
            if key_rows:
                last_row = key_rows[-1]
                last_outcome = last_row.get("outcome")
                last_ts = last_row.get("ts")

            results.append({
                "id": cap_id,
                "last_outcome": last_outcome,
                "last_ts": last_ts,
                "cooling": is_cooling(cap_id, effective_root),
                "window_load": window_load(cap_id, effective_root),
            })
        return results
    except ImportError:
        return "engine.neuralweb.key_pool not available in this environment"
    except Exception as exc:  # noqa: BLE001
        return f"key_pool error: {exc}"


def _freezes_7d() -> int:
    """Count freeze_*.json files in data/metabolism/journal/ modified in last 7d."""
    try:
        journal = _MET_DIR / "journal"
        if not journal.exists():
            return 0
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - 7 * 86400
        count = 0
        for f in journal.glob("freeze_*.json"):
            try:
                if f.stat().st_mtime >= cutoff:
                    count += 1
            except Exception:  # noqa: BLE001
                pass
        return count
    except Exception:  # noqa: BLE001
        return 0


def panel(root: Path | None = None) -> dict:
    """Return the metabolism panel data dict.

    Keys:
      variable_value  — raw AUTONOMY_PAUSED value from GitHub API, or None
      armed           — True only when variable_value == "false"
      state           — "armed" | "paused" | "unknown"
      has_token       — whether a GitHub token is configured
      runs            — list of recent metabolism workflow runs (up to 15)
      organism        — organism_state.json scalar summary or None
      keys            — list of key health dicts, or a note string
      freezes_7d      — count of freeze_*.json files in last 7 days

    Never raises.
    """
    try:
        has_token = bool(github_api.token())
        variable_value = github_api.get_repo_variable(_VAR_NAME)
        armed, state = _armed_state(variable_value)
        runs = _recent_metabolism_runs()
        organism = _organism_summary()
        keys = _key_health(root)
        freezes = _freezes_7d()

        return {
            "variable_value": variable_value,
            "armed": armed,
            "state": state,
            "has_token": has_token,
            "runs": runs,
            "organism": organism,
            "keys": keys,
            "freezes_7d": freezes,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "variable_value": None,
            "armed": False,
            "state": "unknown",
            "has_token": False,
            "runs": [],
            "organism": None,
            "keys": f"panel error: {exc}",
            "freezes_7d": 0,
        }
