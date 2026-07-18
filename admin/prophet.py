"""admin/prophet.py — Prophet NW lobe governor admin page.

Panel payload for GET /api/prophet.  Every source is fail-soft (try/except
→ None/[]).  The panel reads only committed artifacts; it never writes.

Structure mirrors the orchestrator_panel() pattern in neural_web.py:
  prophet_status   — cross-market blocks from data/neuralweb/prophet_status.json
  suggestions      — data/neuralweb/prophet_suggestions.json
  fitness          — metabolism fitness cards (us + cn)
  audit_state      — trigger state from standout_audit state files
  postmortems      — newest 3 cohort postmortem digests
  pick_autopsies   — newest 5 pick autopsy digests (ticker + mitigation + lesson)
  track_record     — summary from site/factordata/us_track_history.json
  fable_spend      — today's deliberation-model token spend vs budget cap
  settings         — echo of config.yml `prophet:` block
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

_PROPHET_STATUS_REL   = Path("data/neuralweb/prophet_status.json")
_PROPHET_SUGGEST_REL  = Path("data/neuralweb/prophet_suggestions.json")
_FITNESS_US_REL       = Path("data/metabolism/fitness/standouts_us.json")
_FITNESS_CN_REL       = Path("data/metabolism/fitness/standouts_cn.json")
_AUDIT_STATE_US_REL   = Path("data/standout_audit/us_audit_state.json")
_AUDIT_STATE_CN_REL   = Path("data/standout_audit/cn_audit_state.json")
_POSTMORTEMS_DIR_REL  = Path("data/standout_audit/postmortems")
_AUTOPSIES_DIR_REL    = Path("data/standout_audit/pick_autopsies")
_TRACK_HISTORY_REL    = Path("site/factordata/us_track_history.json")

# Deliberation model prefix — spend for any model containing "fable" or
# matching llm_models.deliberation in config.yml.
_DELIBERATION_LANE_PREFIXES = ("metabolism-standout", "metabolism-propose", "metabolism-adjudicate")
_DELIBERATION_MODEL_DEFAULT = "claude-opus-4-8"


# ---------------------------------------------------------------------------
# IO helpers (all fail-soft)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _list_files_newest_first(directory: Path, glob: str = "*.json") -> list[Path]:
    """Return files in *directory* matching *glob*, newest mtime first.
    Returns [] when the directory is absent or unreadable.
    """
    try:
        return sorted(directory.glob(glob), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Subsection builders
# ---------------------------------------------------------------------------

def _prophet_status(repo: Path) -> dict | None:
    return _read_json(repo / _PROPHET_STATUS_REL)


def _prophet_suggestions(repo: Path) -> list[dict]:
    data = _read_json(repo / _PROPHET_SUGGEST_REL)
    if not isinstance(data, dict):
        return []
    return data.get("suggestions") or []


def _fitness(repo: Path) -> dict:
    return {
        "us": _read_json(repo / _FITNESS_US_REL),
        "cn": _read_json(repo / _FITNESS_CN_REL),
    }


def _audit_state(repo: Path) -> dict:
    return {
        "us": _read_json(repo / _AUDIT_STATE_US_REL),
        "cn": _read_json(repo / _AUDIT_STATE_CN_REL),
    }


def _postmortems(repo: Path) -> list[dict]:
    """Return digests for the newest 3 cohort postmortem files.

    Each digest carries: filename, as_of (from artifact), market,
    matured_n, and the first ~200 chars of the narrative.
    Returns [] with a note when the directory is absent (accruing).
    """
    pm_dir = repo / _POSTMORTEMS_DIR_REL
    if not pm_dir.exists():
        return []
    files = _list_files_newest_first(pm_dir, "*.json")[:3]
    out = []
    for f in files:
        try:
            data = _read_json(f)
            if not isinstance(data, dict):
                continue
            out.append({
                "filename": f.name,
                "market": data.get("market"),
                "as_of": data.get("as_of") or data.get("cycle_id"),
                "matured_n": data.get("matured_n"),
                "narrative_excerpt": str(data.get("narrative") or "")[:200],
            })
        except Exception:  # noqa: BLE001
            continue
    return out


def _pick_autopsies(repo: Path) -> list[dict]:
    """Return digests for the newest 5 pick autopsy files across all markets.

    Each digest carries: ticker, market, mitigation_verdict, lesson.
    Returns [] when the directory is absent (accruing; honest note handled by panel).
    """
    ap_dir = repo / _AUTOPSIES_DIR_REL
    if not ap_dir.exists():
        return []
    # Collect all .json files across market sub-directories
    all_files: list[Path] = []
    try:
        for market_dir in ap_dir.iterdir():
            if market_dir.is_dir():
                all_files.extend(market_dir.glob("*.json"))
    except Exception:  # noqa: BLE001
        return []
    # Sort newest-mtime first, take top 5
    all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for f in all_files[:5]:
        try:
            data = _read_json(f)
            if not isinstance(data, dict):
                continue
            out.append({
                "ticker":              data.get("ticker") or f.stem,
                "market":              data.get("market") or f.parent.name,
                "mitigation_verdict":  data.get("mitigation_verdict"),
                "lesson":              data.get("lesson") or data.get("lesson_line"),
                "as_of":               data.get("asof") or data.get("as_of"),
            })
        except Exception:  # noqa: BLE001
            continue
    return out


def _track_record(repo: Path) -> dict | None:
    """Summary from us_track_history.json — top-level keys only (no deep embed)."""
    data = _read_json(repo / _TRACK_HISTORY_REL)
    if not isinstance(data, dict):
        return None
    rollup = data.get("cohort_rollup") or {}
    return {
        "as_of":      data.get("as_of"),
        "schema":     data.get("schema"),
        "horizons":   list((rollup.get("horizons") or {}).keys()),
        "accruing":   all(
            v.get("accruing", True)
            for v in (rollup.get("horizons") or {}).values()
        ),
        "h21_win_rate": ((rollup.get("horizons") or {}).get("h21") or {}).get("win_rate"),
        "h21_effective_n": ((rollup.get("horizons") or {}).get("h21") or {}).get("effective_n"),
    }


def _fable_spend(repo: Path, cap: int) -> dict:
    """Today's deliberation token spend vs the daily cap.

    Uses engine.llm_auth.deliberation_spend_today() (days=1 window) so the
    panel and the gate always see the same truly today-scoped figure.

    Fail-soft: any error → spend unknown, returns a note.
    """
    # Determine deliberation model ID from config
    try:
        from admin import config_store as _cs  # noqa: PLC0415
        cfg = _cs.read_config()
        delib_model = (cfg.get("llm_models") or {}).get("deliberation") or _DELIBERATION_MODEL_DEFAULT
    except Exception:  # noqa: BLE001
        delib_model = _DELIBERATION_MODEL_DEFAULT

    # Use the shared helper so gate and panel can never diverge
    try:
        import sys as _sys  # noqa: PLC0415
        _repo_str = str(repo)
        if _repo_str not in _sys.path:
            _sys.path.insert(0, _repo_str)
        from engine import llm_auth as _la  # noqa: PLC0415
        spend = _la.deliberation_spend_today(delib_model, root=repo)
    except Exception as exc:  # noqa: BLE001
        log.debug("prophet.panel: deliberation_spend_today unavailable (%s)", exc)
        return {"error": "spend helper unavailable", "cap": cap}

    today_tokens = spend["tokens"]
    today_usd = spend["usd"]

    return {
        "deliberation_model": delib_model,
        "today_tokens_model": today_tokens,
        "today_usd_model": round(today_usd, 6),
        "cap": cap,
        "budget_pct": round(
            min(100, 100 * today_tokens / max(1, cap)),
            1,
        ),
    }


def _settings(repo: Path) -> dict:
    """Echo of config.yml `prophet:` block.  Fail-soft → empty dict."""
    try:
        from admin import config_store as _cs  # noqa: PLC0415
        cfg = _cs.read_config()
        return dict(cfg.get("prophet") or {})
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def panel(root=None) -> dict:
    """Return the Prophet admin page payload (GET /api/prophet).

    All sources fail-soft.  ``root`` defaults to the repo root (tests pass a
    fixture root).
    """
    repo = Path(root) if root is not None else _ROOT

    ps     = _prophet_status(repo)
    sug    = _prophet_suggestions(repo)
    fit    = _fitness(repo)
    ast    = _audit_state(repo)
    pm     = _postmortems(repo)
    ap     = _pick_autopsies(repo)
    tr     = _track_record(repo)
    cfg    = _settings(repo)
    cap    = int((cfg.get("deliberation_daily_token_cap") or 2_000_000))
    spend  = _fable_spend(repo, cap)

    # Honest absence notes
    pm_note  = None if pm else "cohort postmortems not yet written (accruing)"
    ap_note  = None if ap else "pick autopsies not yet written (accruing)"

    return {
        "ok": True,
        "prophet_status": ps,
        "suggestions": sug,
        "fitness": fit,
        "audit_state": ast,
        "postmortems": pm,
        "postmortems_note": pm_note,
        "pick_autopsies": ap,
        "pick_autopsies_note": ap_note,
        "track_record": tr,
        "fable_spend": spend,
        "settings": cfg,
    }
