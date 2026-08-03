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
  learning_loop    — digest of data/prophet_postmortem/summary.json (Learning Loop §2)
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
_LEARNING_LOOP_REL    = Path("data/prophet_postmortem/summary.json")

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
            llm = data.get("llm") if isinstance(data.get("llm"), dict) else {}
            out.append({
                "ticker":              data.get("ticker") or f.stem,
                "market":              data.get("market") or f.parent.name,
                "mitigation_verdict":  llm.get("mitigation_verdict") or data.get("mitigation_verdict"),
                "lesson":              llm.get("lesson") or data.get("lesson") or data.get("lesson_line"),
                "summary":             llm.get("summary") or llm.get("root_cause"),
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


def _learning_loop(repo: Path) -> dict | None:
    """Digest of the Prophet Learning Loop postmortem artifact.

    A POINTER, not a recomputation: the panel reads the committed
    data/prophet_postmortem/summary.json and forwards the aggregations. Re-deriving any
    of these here would give the admin a second implementation of the taxonomy that
    could quietly disagree with the artifact and the report.

    The veto table is forwarded WITH its winners-forfeited column. Shipping
    losses-avoided alone would turn a symmetric counterfactual into an argument for a
    veto — which is the exact reading the artifact exists to prevent.

    It is also forwarded WITH `visible_at_entry` / `variant` / `leg` per row. A veto row
    is a TRIGGER, not a label: `re_admission` arrives as two rows, one buildable (the
    prior position was already under water at the re-admission) and one hindsight (the
    prior episode's resolved loss, a number that did not exist at entry). Dropping those
    fields here would put the hindsight row's headline on the panel with nothing to mark
    it as hindsight — the same badge error the engine was fixed to stop making.

    Fail-soft: returns None when the artifact has not been written yet (the panel then
    shows an honest accruing note). See docs/PROPHET_POSTMORTEM_PROTOCOL.md.
    """
    data = _read_json(repo / _LEARNING_LOOP_REL)
    if not isinstance(data, dict):
        return None
    summary = data.get("summary") or {}
    cohorts = summary.get("cohorts") or {}
    return {
        "as_of":        data.get("as_of"),
        "schema":       data.get("schema"),
        "artifact":     str(_LEARNING_LOOP_REL),
        "report":       f"reports/prophet_postmortem_{data.get('as_of')}.md",
        "protocol":     "docs/PROPHET_POSTMORTEM_PROTOCOL.md",
        "horizon":      (data.get("method") or {}).get("horizon"),
        "llm_used":     (data.get("method") or {}).get("llm_used"),
        "n_episodes":   summary.get("n_episodes"),
        "n_matured":    summary.get("n_matured"),
        "n_in_flight":  summary.get("n_in_flight"),
        "n_board_dates": summary.get("n_board_dates"),
        "n_losers":     cohorts.get("n_losers"),
        "n_winners":    cohorts.get("n_winners"),
        "labels": [
            {
                "label":            f.get("label"),
                "en":               f.get("en"),
                "zh":               f.get("zh"),
                "visible_at_entry": f.get("visible_at_entry"),
                "n_losers":         f.get("n_losers"),
                "loser_share_pct":  f.get("loser_share_pct"),
                "n_winners":        f.get("n_winners"),
                "winner_share_pct": f.get("winner_share_pct"),
                "loser_coverage_pct": f.get("loser_coverage_pct"),
                "loss_contribution_pct": f.get("loss_contribution_pct"),
                "n_null_disclosed": f.get("n_null_disclosed"),
            }
            for f in (summary.get("label_frequency") or [])
        ],
        "veto_cost": [
            {
                "key":                   v.get("key"),
                "label":                 v.get("label"),
                "leg":                   v.get("leg"),
                "variant":               v.get("variant"),
                "visible_at_entry":      v.get("visible_at_entry"),
                "en":                    v.get("en"),
                "zh":                    v.get("zh"),
                "variant_en":            v.get("variant_en"),
                "variant_zh":            v.get("variant_zh"),
                "n_flagged":             v.get("n_flagged"),
                "n_universe":            v.get("n_universe"),
                "n_dates_flagged":       v.get("n_dates_flagged"),
                "n_losers_avoided":      v.get("n_losers_avoided"),
                "loss_avoided_pct":      v.get("loss_avoided_pct"),
                "n_winners_forfeited":   v.get("n_winners_forfeited"),
                "winners_forfeited_pct": v.get("winners_forfeited_pct"),
                "net_pct_if_vetoed":     v.get("net_pct_if_vetoed"),
            }
            for v in (summary.get("veto_cost") or [])
        ],
        "caveats": [c.get("en") for c in (data.get("caveats") or []) if c.get("en")],
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
    ll     = _learning_loop(repo)
    cfg    = _settings(repo)
    cap    = int((cfg.get("deliberation_daily_token_cap") or 2_000_000))
    spend  = _fable_spend(repo, cap)

    # Honest absence notes
    pm_note  = None if pm else "cohort postmortems not yet written (accruing)"
    ap_note  = None if ap else "pick autopsies not yet written (accruing)"
    ll_note  = None if ll else (
        "learning-loop postmortem not yet written — run "
        "`python -m scripts.prophet_postmortem` (docs/PROPHET_POSTMORTEM_PROTOCOL.md)"
    )

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
        "learning_loop": ll,
        "learning_loop_note": ll_note,
        "fable_spend": spend,
        "settings": cfg,
    }
