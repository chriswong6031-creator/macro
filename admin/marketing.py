"""admin/marketing.py — Marketing NW lobe admin page.

Panel payloads for GET /api/marketing/{overview,departments,channels,campaigns,
experiments,lobes}.  All sources are fail-soft (try/except → None/[]).  Panels
read only committed artifacts; they never write.

The single source of truth is data/neuralweb/marketing_state.json (marketing.state/v1).
config/marketing.yml is read for the settings echo.

All public functions return {"ok": True, ...} or {"ok": False, "error": ...}.
If the state file is absent they return ok:True with empty/null sections and
an honest accruing note — so the page renders gracefully on day 0.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

_STATE_REL   = Path("data/neuralweb/marketing_state.json")
_CONTENT_REL = Path("data/marketing/content_plan.json")
_CONFIG_REL  = Path("config/marketing.yml")

_ACCRUING_NOTE = (
    "marketing_state.json not yet written — "
    "accruing after first nightly governor run."
)
_CONTENT_ACCRUING_NOTE = (
    "content_plan.json not yet written — "
    "accruing after first nightly governor run."
)


# ---------------------------------------------------------------------------
# IO helpers (all fail-soft)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _read_yaml(path: Path) -> dict:
    try:
        import yaml  # noqa: PLC0415
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:  # noqa: BLE001
        return {}


def _state(root: Path) -> dict | None:
    return _read_json(root / _STATE_REL)


# ---------------------------------------------------------------------------
# Panel builders
# ---------------------------------------------------------------------------

def overview(root=None) -> dict:
    """CMO office view: lobe lifecycle, mandate, north-star, CMO portfolio,
    opportunity queue depth, self-improvement loop, guardrail checklist."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "lobe": None,
                "north_star": None,
                "cmo": None,
                "authority_level": None,
                "mandate": None,
            }
        return {
            "ok": True,
            "lobe": s.get("lobe"),
            "north_star": s.get("north_star"),
            "cmo": s.get("cmo"),
            "authority_level": (s.get("lobe") or {}).get("authority_level"),
            "mandate": (s.get("lobe") or {}).get("mandate"),
            "as_of": s.get("as_of"),
            "waves": s.get("waves"),
            "notes": s.get("notes"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.overview failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def departments(root=None) -> dict:
    """Department portfolio: one record per department + authority ladder."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "departments": [],
                "authority_ladder": [],
            }
        return {
            "ok": True,
            "departments": s.get("departments") or [],
            "authority_ladder": s.get("authority_ladder") or [],
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.departments failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def channels(root=None) -> dict:
    """Desk network: accounts, distinctness, actuation path; publication ledger;
    corrections count."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "desk_network": None,
                "publications": None,
                "corrections": None,
            }
        pipeline = s.get("pipeline") or {}
        return {
            "ok": True,
            "desk_network": s.get("desk_network"),
            "publications": pipeline.get("publications"),
            "corrections": (pipeline.get("publications") or {}).get("corrections"),
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.channels failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def campaigns(root=None) -> dict:
    """Opportunity bus + campaigns table + pipeline summary."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "opportunities": None,
                "campaigns": None,
                "pipeline": None,
            }
        pipeline = s.get("pipeline") or {}
        return {
            "ok": True,
            "opportunities": pipeline.get("opportunities"),
            "campaigns": pipeline.get("campaigns"),
            "pipeline": pipeline,
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.campaigns failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def experiments(root=None) -> dict:
    """Experiment registry + trial-variant selector + north-star window."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "experiments": None,
                "trial_variants": ["7_trading_days", "14_calendar_days", "value_moment_limited"],
                "north_star": None,
            }
        pipeline = s.get("pipeline") or {}
        cfg = _read_yaml(repo / _CONFIG_REL)
        active_variant = (cfg.get("settings") or {}).get("trial_variant", "7_trading_days")
        return {
            "ok": True,
            "experiments": pipeline.get("experiments"),
            "trial_variants": ["7_trading_days", "14_calendar_days", "value_moment_limited"],
            "active_trial_variant": active_variant,
            "north_star": s.get("north_star"),
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.experiments failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def lobes(root=None) -> dict:
    """Engines-by-department; provenance modes + claims summary; growth-event spine."""
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "engines_by_department": [],
                "provenance": None,
                "growth_events": None,
            }
        # Build engines-by-department index from department records
        depts = s.get("departments") or []
        engines_by_dept = [
            {
                "department_id":   d.get("id"),
                "department_name": d.get("name"),
                "engines":         d.get("engines") or [],
                "lifecycle_state": d.get("lifecycle_state"),
                "authority_level": d.get("authority_level"),
            }
            for d in depts
        ]
        pipeline = s.get("pipeline") or {}
        return {
            "ok": True,
            "engines_by_department": engines_by_dept,
            "provenance": s.get("provenance"),
            "growth_events": pipeline.get("growth_events"),
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.lobes failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def content(root=None) -> dict:
    """Content Studio panel: reads data/marketing/content_plan.json.

    Returns {ok, content_types, accounts, featured_charts, distinctness, summary}.
    Fail-soft with honest note when the file is absent (accruing state).
    """
    repo = Path(root) if root is not None else _ROOT
    try:
        cp = _read_json(repo / _CONTENT_REL)
        if cp is None:
            return {
                "ok": True,
                "note": _CONTENT_ACCRUING_NOTE,
                "content_types": [],
                "accounts": [],
                "featured_charts": [],
                "distinctness": None,
                "summary": None,
            }
        return {
            "ok": True,
            "content_types": cp.get("content_types") or [],
            "accounts": cp.get("accounts") or [],
            "featured_charts": cp.get("featured_charts") or [],
            "distinctness": cp.get("distinctness"),
            "summary": cp.get("summary"),
            "as_of": cp.get("as_of"),
            "source": cp.get("source"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.content failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def department(root=None, dept_id=None) -> dict:
    """Single-department detail payload.

    Returns mission/tagline/formal_name, engines [{id,name,does}], scorecard,
    authority, model mix, wave, retirement test.
    Fail-soft: returns ok:True with note if state absent or dept not found.
    """
    repo = Path(root) if root is not None else _ROOT
    try:
        s = _state(repo)
        if s is None:
            return {
                "ok": True,
                "note": _ACCRUING_NOTE,
                "department": None,
            }
        depts = s.get("departments") or []
        if dept_id is None:
            return {
                "ok": True,
                "note": "dept_id required",
                "department": None,
            }
        dept = next((d for d in depts if d.get("id") == dept_id), None)
        if dept is None:
            return {
                "ok": True,
                "note": f"Department '{dept_id}' not found (accruing or unknown id).",
                "department": None,
            }
        return {
            "ok": True,
            "department": dept,
            "as_of": s.get("as_of"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.department failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def settings(root=None) -> dict:
    """Echo of config/marketing.yml top-level knobs. Read-only."""
    repo = Path(root) if root is not None else _ROOT
    try:
        cfg = _read_yaml(repo / _CONFIG_REL)
        s_block = cfg.get("settings") or {}
        return {
            "ok": True,
            "settings": {
                "trial_variant":      s_block.get("trial_variant", "7_trading_days"),
                "desk_network_stage": s_block.get("desk_network_stage", "A"),
                "paid_enabled":       bool(s_block.get("paid_enabled", False)),
                "auditor_strict":     bool(s_block.get("auditor_strict", True)),
                "north_star_window_days": int(s_block.get("north_star_window_days", 90)),
            },
            "positioning": cfg.get("positioning") or {},
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing.settings failed: %s", exc)
        return {"ok": False, "error": str(exc)}
