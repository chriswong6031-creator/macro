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
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import github_api
from .paths import ROOT

_log = logging.getLogger(__name__)

_VAR_NAME = "AUTONOMY_PAUSED"
_ARMED_VALUE = "false"

# Metabolism data directory
_MET_DIR = ROOT / "data" / "metabolism"

# ---------------------------------------------------------------------------
# V10 Throttle constants (mirrors engine.metabolism.throttle)
# ---------------------------------------------------------------------------
_INTENSITY_ALLOWED = {"low", "normal", "high", "max"}
_PACE_ALLOWED = {"single", "2x", "4x"}
_KEYS_ENABLED_RE = re.compile(r"^[0-9a-z,]{0,64}$")

# Workflow filename map for run mode dispatch
_RUN_MODE_WORKFLOWS = {
    "cycle": "metabolism-cycle.yml",
    "agenda": "metabolism-agenda.yml",
    "propose": "metabolism-propose.yml",
    "adjudicate": "metabolism-adjudicate.yml",
    "build": "metabolism-build.yml",
}

_STAGES_ALLOWED = {"full", "sense", "through-adjudicate"}
_LOBE_RE = re.compile(r"^[a-z0-9-]{0,40}$")


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


# ---------------------------------------------------------------------------
# V10 Throttle & Key Economy
# ---------------------------------------------------------------------------

def throttle(root: Path | None = None) -> dict:  # noqa: ARG001
    """Return the current METAB_* throttle variable state.

    Reads METAB_INTENSITY, METAB_PACE, METAB_KEYS_ENABLED from GitHub repo
    variables (fail-soft: each None-tolerates).  Resolves effective values
    via engine.metabolism.throttle helpers (guarded import; fails to defaults
    + note string).  Never raises.
    """
    # Read raw variable values from GitHub — each None when absent/error.
    intensity_raw = github_api.get_repo_variable("METAB_INTENSITY")
    pace_raw = github_api.get_repo_variable("METAB_PACE")
    keys_raw = github_api.get_repo_variable("METAB_KEYS_ENABLED")

    # Resolve effective values via throttle engine helpers.
    engine_note: str | None = None
    effective_intensity = "normal"
    effective_pace = "single"
    extra_cycles = 0
    try:
        from engine.metabolism.throttle import (  # noqa: PLC0415
            intensity,
            intensity_multiplier,
            pace,
            pace_extra_cycles,
        )
        import os as _os  # noqa: PLC0415
        # Temporarily inject raw values so the helpers read them.
        _saved_i = _os.environ.get("METAB_INTENSITY")
        _saved_p = _os.environ.get("METAB_PACE")
        try:
            if intensity_raw is not None:
                _os.environ["METAB_INTENSITY"] = intensity_raw
            elif "METAB_INTENSITY" in _os.environ:
                del _os.environ["METAB_INTENSITY"]
            if pace_raw is not None:
                _os.environ["METAB_PACE"] = pace_raw
            elif "METAB_PACE" in _os.environ:
                del _os.environ["METAB_PACE"]
            effective_intensity = intensity()
            effective_pace = pace()
            extra_cycles = pace_extra_cycles(effective_pace)
        finally:
            # Restore original env
            if _saved_i is not None:
                _os.environ["METAB_INTENSITY"] = _saved_i
            elif "METAB_INTENSITY" in _os.environ:
                del _os.environ["METAB_INTENSITY"]
            if _saved_p is not None:
                _os.environ["METAB_PACE"] = _saved_p
            elif "METAB_PACE" in _os.environ:
                del _os.environ["METAB_PACE"]
    except ImportError:
        engine_note = "engine.metabolism.throttle not available; showing raw values"
        # Resolve manually with fail-open defaults
        effective_intensity = intensity_raw if intensity_raw in _INTENSITY_ALLOWED else "normal"
        effective_pace = pace_raw if pace_raw in _PACE_ALLOWED else "single"
        extra_cycles = {"single": 0, "2x": 1, "4x": 3}.get(effective_pace, 0)
    except Exception as exc:  # noqa: BLE001
        engine_note = f"throttle engine error: {exc}"
        effective_intensity = intensity_raw if intensity_raw in _INTENSITY_ALLOWED else "normal"
        effective_pace = pace_raw if pace_raw in _PACE_ALLOWED else "single"
        extra_cycles = {"single": 0, "2x": 1, "4x": 3}.get(effective_pace, 0)

    # Resolve effective_ids for METAB_KEYS_ENABLED
    keys_enabled_note: str | None = None
    effective_ids: list[str] | None = None  # None = all keys
    try:
        from engine.neuralweb.key_pool import enabled_key_ids  # noqa: PLC0415
        import os as _os  # noqa: PLC0415
        _saved_k = _os.environ.get("METAB_KEYS_ENABLED")
        try:
            if keys_raw is not None:
                _os.environ["METAB_KEYS_ENABLED"] = keys_raw
            elif "METAB_KEYS_ENABLED" in _os.environ:
                del _os.environ["METAB_KEYS_ENABLED"]
            result = enabled_key_ids()
            effective_ids = list(result) if result is not None else None
        finally:
            if _saved_k is not None:
                _os.environ["METAB_KEYS_ENABLED"] = _saved_k
            elif "METAB_KEYS_ENABLED" in _os.environ:
                del _os.environ["METAB_KEYS_ENABLED"]
    except ImportError:
        keys_enabled_note = "engine.neuralweb.key_pool not available"
    except Exception as exc:  # noqa: BLE001
        keys_enabled_note = f"key_pool error: {exc}"

    result_dict: dict = {
        "intensity": {
            "value": intensity_raw,
            "effective": effective_intensity,
            "allowed": ["low", "normal", "high", "max"],
        },
        "pace": {
            "value": pace_raw,
            "effective": effective_pace,
            "allowed": ["single", "2x", "4x"],
            "extra_cycles": extra_cycles,
        },
        "keys_enabled": {
            "value": keys_raw,
            "effective_ids": effective_ids,
        },
    }
    if engine_note:
        result_dict["note"] = engine_note
    if keys_enabled_note:
        result_dict["keys_enabled"]["note"] = keys_enabled_note
    return result_dict


def keys(root: Path | None = None) -> list[dict] | dict:
    """Return per-key usage snapshot from key_pool.usage_snapshot().

    Fail-soft: on any import or runtime error returns {"error": <note>}.
    Never raises.
    """
    try:
        from engine.neuralweb.key_pool import usage_snapshot  # noqa: PLC0415
        return usage_snapshot(root=root)
    except ImportError:
        return {"error": "engine.neuralweb.key_pool not available in this environment"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"key_pool.usage_snapshot error: {exc}"}


# ---------------------------------------------------------------------------
# V10 Validators (pure functions — called by server routes + tests)
# ---------------------------------------------------------------------------

def validate_throttle_body(body: dict) -> tuple[bool, dict, dict]:
    """Validate a POST /api/metabolism/throttle request body.

    Returns (ok, errors, to_set) where:
      ok     — True when no validation errors
      errors — dict of field -> error message (empty when ok)
      to_set — dict of {var_name: value} pairs that passed validation
                 (only fields present in the body and valid)
    """
    errors: dict[str, str] = {}
    to_set: dict[str, str] = {}

    if "intensity" in body:
        v = body["intensity"]
        if v not in _INTENSITY_ALLOWED:
            errors["intensity"] = f"intensity must be one of {sorted(_INTENSITY_ALLOWED)}, got {v!r}"
        else:
            to_set["METAB_INTENSITY"] = v

    if "pace" in body:
        v = body["pace"]
        if v not in _PACE_ALLOWED:
            errors["pace"] = f"pace must be one of {sorted(_PACE_ALLOWED)}, got {v!r}"
        else:
            to_set["METAB_PACE"] = v

    if "keys_enabled" in body:
        v = body["keys_enabled"]
        if not isinstance(v, str):
            errors["keys_enabled"] = "keys_enabled must be a string"
        elif not _KEYS_ENABLED_RE.match(v):
            errors["keys_enabled"] = (
                "keys_enabled must match ^[0-9a-z,]{0,64}$ (csv of 1/2/3/legacy, or empty)"
            )
        else:
            to_set["METAB_KEYS_ENABLED"] = v

    return (len(errors) == 0, errors, to_set)


def validate_run_body(body: dict) -> tuple[bool, str | None, str | None, dict]:
    """Validate a POST /api/metabolism/run request body.

    Returns (ok, error, workflow_filename, inputs_dict).
      ok               — True when valid
      error            — error message string or None
      workflow_filename — e.g. "metabolism-cycle.yml" or None on error
      inputs_dict      — dict to pass as workflow inputs (may be empty)
    """
    mode = body.get("mode")
    if mode not in _RUN_MODE_WORKFLOWS:
        allowed = sorted(_RUN_MODE_WORKFLOWS)
        return (False, f"mode must be one of {allowed}, got {mode!r}", None, {})

    workflow = _RUN_MODE_WORKFLOWS[mode]
    inputs: dict[str, str] = {}

    lobe = body.get("lobe")
    if lobe is not None:
        lobe_str = str(lobe)
        if not _LOBE_RE.match(lobe_str):
            return (False, f"lobe must match ^[a-z0-9-]{{0,40}}$, got {lobe_str!r}", None, {})
        # lobe is valid for cycle and propose
        if mode in ("cycle", "propose"):
            inputs["lobe"] = lobe_str

    stages = body.get("stages")
    if stages is not None:
        stages_str = str(stages)
        if stages_str not in _STAGES_ALLOWED:
            return (
                False,
                f"stages must be one of {sorted(_STAGES_ALLOWED)}, got {stages_str!r}",
                None,
                {},
            )
        if mode == "cycle":
            inputs["stages"] = stages_str

    return (True, None, workflow, inputs)


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
      throttle        — V10 throttle state dict (see throttle())

    Never raises.
    """
    try:
        has_token = bool(github_api.token())
        variable_value = github_api.get_repo_variable(_VAR_NAME)
        armed, state = _armed_state(variable_value)
        runs = _recent_metabolism_runs()
        organism = _organism_summary()
        key_health = _key_health(root)
        freezes = _freezes_7d()
        throttle_data = throttle(root)

        return {
            "variable_value": variable_value,
            "armed": armed,
            "state": state,
            "has_token": has_token,
            "runs": runs,
            "organism": organism,
            "keys": key_health,
            "freezes_7d": freezes,
            "throttle": throttle_data,
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
            "throttle": {},
        }
