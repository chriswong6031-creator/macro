"""engine.metabolism.standout_auditor — SA-W3: standout-lobe audit organ.

Implements the stateless-cattle auditor that triggers post-mortems on standout
attribution data when enough newly-matured graded rows accumulate (SA-R9).

NEVER-RAISE CONTRACT: every public function catches ALL exceptions and returns
a safe fallback.  An auditor failure must never abort the metabolism cycle.

INERTNESS GUARANTEE: this module writes artifacts only.  It dispatches nothing,
grants nothing, escalates nothing, opens no PR, changes no lobe roster.
It is inert under AUTONOMY_PAUSED (same guard as dream.py).

SHADOW / DRY-RUN MODE: run_audit() accepts a dry_run= flag.  When dry_run=True:
  - model_caller MUST be injected (None → status='refused'); dry_run never
    reaches the real LLM waterfall (no real provider call).
  - ALL write targets are redirected under
    data/metabolism/shadow/<cycle_id>/standout_audit/
    (postmortem, proposal files, insight-bus rows, audit_state cache).
    The REAL data/standout_audit/postmortems/, data/standout_review/proposals/,
    and data/metabolism/insight_bus.jsonl are NEVER touched.
  - The AUTONOMY_PAUSED gate is not needed for dry_run (shadow writes are inert);
    armed (non-dry) mode keeps the fail-closed gate exactly as-is.

Supported markets: "us" | "cn".
  US: data/standout_audit/us_attribution.parquet
      data/standout_audit/us_evidence.jsonl
      data/standout_audit/us_audit_state.json
      site/factordata/us_audit_scoreboard.json
      data/metabolism/fitness/standouts_us.json
  CN: analogous paths with "cn_" prefix (accruing from 2026-10-15)

Context assembler §5 blocks:
  (a) stratified scoreboard
  (b) evidence packs (tail since last audit)
  (c) coverage monitor
  (d) upstream concordance table
  (e) fitness card
  (f) prior post-mortems (anti-repetition)
  (g) NW mission block
  (h) SA-R13 verbatim

audit_due() trigger (SA-R9, stateless-cattle):
  newly_matured_graded_rows_since_last_audit >= 15
  OR (>= 5 AND >= 14 days since last postmortem)

Public API:
  build_context(market, root=None) -> dict
  audit_due(market, root=None) -> dict
  run_audit(market, cycle_id, model_caller, root=None, dry_run=False) -> dict
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_CONTEXT = "standout_auditor.context.v1"
SCHEMA_AUDIT_DUE = "standout_auditor.audit_due.v1"
SCHEMA_POSTMORTEM = "standout_auditor.postmortem.v1"

# SA-R9 trigger thresholds
_TRIGGER_NEW_ROWS_HARD = 15    # hard trigger: >= 15 newly matured graded rows
_TRIGGER_NEW_ROWS_SOFT = 5     # soft trigger: >= 5 AND >= 14 days
_TRIGGER_DAYS_SINCE_PM = 14    # days since last postmortem for soft trigger

# F1 FIX: market-aware date column name for the attribution parquet.
# US organ writes an 'as_of' column; CN organ writes a 'date' column.
# This mapping drives _count_graded_rows_since_audit so a missing column
# is a loud schema error, never a silent zero.
_DATE_COL: dict[str, str] = {"us": "as_of", "cn": "date"}
# F2 FIX: canonical audit-state key names (auditor's own schema).
# The US organ writes 'last_graded_asof'; the auditor reads 'last_audit_graded_as_of'.
# _read_audit_state checks both so the organ stamp advances the cursor without a
# second writer.
_STATE_KEY_GRADED = "last_audit_graded_as_of"     # auditor-owned key (primary)
_STATE_KEY_GRADED_ORGAN = "last_graded_asof"       # organ stamp key (fallback alias)
_STATE_KEY_PM_CYCLE = "last_postmortem_cycle_id"   # auditor-owned key (no alias needed)

# Byte budget for context blocks (total context sent to LLM)
_SCOREBOARD_BUDGET_BYTES = 12_000
_EVIDENCE_BUDGET_BYTES = 20_000
_COVERAGE_BUDGET_BYTES = 4_000
_CONCORDANCE_BUDGET_BYTES = 4_000
_FITNESS_BUDGET_BYTES = 4_000
_PRIOR_PM_BUDGET_BYTES = 8_000
_MISSION_BUDGET_BYTES = 2_000

# Max postmortems to load for anti-repetition context
_MAX_PRIOR_POSTMORTEMS = 3

# Opus model (hard-law: auditor always uses Opus tier)
_OPUS_MODEL = "claude-opus-4-8"

# LLM config mirror from propose.py
_LLM_CFG: dict[str, Any] = {
    "provider_order": ["oauth", "anthropic", "deepseek"],
    "opus_model": _OPUS_MODEL,
    "deepseek_model": "deepseek-chat",
    "deepseek_base_url": "https://api.deepseek.com/anthropic",
    "max_tokens": 6000,
    "oauth_pool_lane": "metabolism-standout",
    "usage_lane": "metabolism-standout",
}

# SA-R13 verbatim — LOOP-IMMUTABLE (do not modify without operator PR)
_SA_R13_VERBATIM = (
    'The two-axis taxonomy assigns an outcome-cause AND a process-fault '
    'independently, so "chased late into a macro drop" records both truths — '
    'the process fault is never masked by the outcome cause. Post-mortems must '
    'respond to each axis with its own remedy class: outcome-cause failures with '
    'clean process demand conditioning evidence (e.g. regime-cell analysis), '
    'NEVER gate tightening; process faults demand the specific fix (timing, gate '
    'margin, data repair). A winner entered late is a process fail despite the P&L.'
)

# Proposal schema required fields (mirrors standout_review.py)
_PROPOSAL_REQUIRED_FIELDS = frozenset({
    "market", "param", "delta_steps", "rationale_ref", "proposer", "cycle_id"
})


# ---------------------------------------------------------------------------
# Path helpers (NEVER raise)
# ---------------------------------------------------------------------------

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _attribution_path(market: str, root: Path) -> Path:
    return root / "data" / "standout_audit" / f"{market}_attribution.parquet"


def _evidence_path(market: str, root: Path) -> Path:
    return root / "data" / "standout_audit" / f"{market}_evidence.jsonl"


def _scoreboard_path(market: str, root: Path) -> Path:
    return root / "site" / "factordata" / f"{market}_audit_scoreboard.json"


def _state_path(market: str, root: Path) -> Path:
    return root / "data" / "standout_audit" / f"{market}_audit_state.json"


def _fitness_path(market: str, root: Path) -> Path:
    fname = "standouts_us.json" if market == "us" else "standouts_cn.json"
    return root / "data" / "metabolism" / "fitness" / fname


def _postmortems_dir(root: Path) -> Path:
    p = root / "data" / "standout_audit" / "postmortems"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    return p


def _proposals_dir(root: Path) -> Path:
    p = root / "data" / "standout_review" / "proposals"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    return p


def _nw_mission_path(root: Path) -> Path:
    return root / "config" / "nw_mission.yml"


# ---------------------------------------------------------------------------
# Shadow-root path helpers (F1 — true dry_run redirection)
# ---------------------------------------------------------------------------

def _shadow_base(root: Path, cycle_id: str) -> Path:
    """Return the shadow base dir for a given cycle_id.

    Convention mirrors metabolism_shadow_cycle.py:
      data/metabolism/shadow/<cycle_id>/standout_audit/
    """
    return root / "data" / "metabolism" / "shadow" / cycle_id / "standout_audit"


def _shadow_postmortems_dir(root: Path, cycle_id: str) -> Path:
    p = _shadow_base(root, cycle_id) / "postmortems"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    return p


def _shadow_proposals_dir(root: Path, cycle_id: str) -> Path:
    p = _shadow_base(root, cycle_id) / "proposals"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    return p


def _shadow_bus_path(root: Path, cycle_id: str) -> Path:
    """Shadow insight_bus file — never touches the real bus."""
    p = _shadow_base(root, cycle_id) / "insight_bus.jsonl"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    return p


def _shadow_audit_state_path(market: str, root: Path, cycle_id: str) -> Path:
    p = _shadow_base(root, cycle_id) / f"{market}_audit_state.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    return p


# ---------------------------------------------------------------------------
# Small I/O helpers (NEVER raise)
# ---------------------------------------------------------------------------

def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _read_jsonl_tail(p: Path, n: int = 200) -> list[dict]:
    """Read the last n lines of a JSONL file.  Returns [] on any error."""
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        rows: list[dict] = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
        return rows
    except Exception:  # noqa: BLE001
        return []


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _truncate_bytes(text: str, budget: int) -> str:
    """Truncate a string to at most budget bytes (UTF-8).  Adds sentinel if truncated."""
    encoded = text.encode("utf-8")
    if len(encoded) <= budget:
        return text
    truncated = encoded[:budget].decode("utf-8", errors="ignore")
    return truncated + "\n[TRUNCATED — budget exhausted]"


def _json_truncated(obj: Any, budget: int) -> str:
    """JSON-encode obj and truncate to budget bytes."""
    try:
        text = json.dumps(obj, indent=2, default=str)
    except Exception:  # noqa: BLE001
        text = str(obj)
    return _truncate_bytes(text, budget)


# ---------------------------------------------------------------------------
# Audit state helpers (NEVER raise)
# ---------------------------------------------------------------------------

def _read_audit_state(market: str, root: Path) -> dict:
    """Read the audit state JSON for the given market.  Returns {} on any error.

    F2 FIX: normalises the organ-stamp alias key 'last_graded_asof' (written by
    engine/standout_audit.py) into the auditor's canonical key
    'last_audit_graded_as_of' so the organ stamp advances the cursor without
    requiring a separate state writer.  The auditor's own key takes precedence
    (set by run_audit's post-audit stamp).
    """
    try:
        p = _state_path(market, root)
        if not p.exists():
            return {}
        raw = _read_json(p) or {}
        # F2: if the auditor's canonical key is absent but the organ alias is present,
        # promote the organ alias so downstream readers see a unified cursor.
        if _STATE_KEY_GRADED not in raw and _STATE_KEY_GRADED_ORGAN in raw:
            raw = dict(raw)
            raw[_STATE_KEY_GRADED] = raw[_STATE_KEY_GRADED_ORGAN]
        return raw
    except Exception:  # noqa: BLE001
        return {}


def _count_graded_rows_since_audit(market: str, root: Path, last_audit_graded_as_of: str | None) -> int:
    """Count newly matured graded rows since the last audit.

    Uses the attribution parquet if available, else falls back to evidence JSONL.
    'Newly matured' means rows whose date_col > last_audit_graded_as_of (or all
    rows if last_audit_graded_as_of is None/absent).

    F1 FIX: uses _DATE_COL[market] to handle the US ('as_of') vs CN ('date')
    schema difference.  A KeyError on the expected column is now a loud WARNING
    with status="schema_error" surfaced via the caller — never a silent zero.

    NEVER raises.
    """
    try:
        date_col = _DATE_COL.get(market, "as_of")
        attr_p = _attribution_path(market, root)
        if attr_p.exists():
            try:
                import pandas as pd  # type: ignore[import]
                # F1: check schema BEFORE reading to distinguish "column absent"
                # (schema mismatch = loud error sentinel) from other read errors
                # (fallback to JSONL).  pyarrow.parquet.ParquetFile.schema_arrow
                # is cheap (no row scan) and available in all supported versions.
                try:
                    import pyarrow.parquet as _pq  # type: ignore[import]
                    _schema = _pq.ParquetFile(str(attr_p)).schema_arrow
                    _available = {str(f.name) for f in _schema}
                except Exception:  # noqa: BLE001
                    _available = None  # cannot verify schema → fall through to read

                if _available is not None and date_col not in _available:
                    log.error(
                        "standout_auditor: _count_graded_rows_since_audit(%s): "
                        "expected column %r absent in attribution parquet "
                        "(available: %s) — schema mismatch; "
                        "returning -1 as error sentinel",
                        market, date_col, sorted(_available),
                    )
                    return -1  # loud error sentinel; audit_due will surface schema_error

                df = pd.read_parquet(str(attr_p), columns=[date_col])
                if df.empty:
                    return 0
                if last_audit_graded_as_of:
                    # Count rows with date_col strictly after the last audit snapshot
                    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                    cutoff = pd.to_datetime(last_audit_graded_as_of, errors="coerce")
                    if cutoff is not pd.NaT:  # type: ignore[comparison-overlap]
                        return int((df[date_col] > cutoff).sum())
                return len(df)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "standout_auditor: _count_graded_rows_since_audit(%s): "
                    "parquet read failed (%s); falling back to evidence JSONL",
                    market, exc,
                )

        # Fallback: count evidence JSONL rows (evidence uses market-native date key)
        # CN evidence rows use 'date'; US evidence rows use 'as_of'
        ev_date_key = date_col  # same mapping applies to JSONL evidence rows
        ev_p = _evidence_path(market, root)
        if not ev_p.exists():
            return 0
        rows = _read_jsonl_tail(ev_p, n=10_000)
        if not rows:
            return 0
        if last_audit_graded_as_of:
            return sum(
                1 for r in rows
                if str(r.get(ev_date_key) or r.get("as_of") or "") > last_audit_graded_as_of
            )
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: _count_graded_rows_since_audit(%s): %s", market, exc)
        return 0


def _days_since_last_postmortem(market: str, root: Path, last_postmortem_cycle_id: str | None) -> int | None:
    """Return days since the last postmortem was written, or None if unknown.

    Reads the postmortem file's 'ts' field.  NEVER raises.
    """
    if not last_postmortem_cycle_id:
        return None
    try:
        pm_dir = _postmortems_dir(root)
        pm_path = pm_dir / f"{market}-{last_postmortem_cycle_id}.json"
        if not pm_path.exists():
            # Try scanning for most recent
            matches = sorted(pm_dir.glob(f"{market}-*.json"), reverse=True)
            if not matches:
                return None
            pm_path = matches[0]

        pm = _read_json(pm_path)
        if not pm:
            return None
        ts_str = pm.get("ts") or pm.get("created_at")
        if not ts_str:
            return None
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max(0, (now - ts).days)
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: _days_since_last_postmortem(%s): %s", market, exc)
        return None


# ---------------------------------------------------------------------------
# Context assembler §5 (NEVER raise)
# ---------------------------------------------------------------------------

def build_context(market: str, root: Path | None = None) -> dict:
    """Assemble the §5 audit context blocks for the given market.

    Returns a dict with keys: schema, market, ts, blocks, data_gaps.
    Each block is a string (JSON or text), truncated to its byte budget.
    NEVER raises; missing stores produce honest data_gap entries.
    """
    try:
        repo = _repo_root(root)
        ts = _now_utc()
        data_gaps: list[str] = []
        blocks: dict[str, str] = {}

        # (a) Stratified scoreboard
        try:
            sb_path = _scoreboard_path(market, repo)
            if sb_path.exists():
                sb = _read_json(sb_path)
                blocks["scoreboard"] = _json_truncated(sb, _SCOREBOARD_BUDGET_BYTES)
            else:
                data_gaps.append(f"scoreboard: {sb_path} absent")
                blocks["scoreboard"] = json.dumps({"data_gap": str(sb_path)})
        except Exception as exc:  # noqa: BLE001
            data_gaps.append(f"scoreboard: {exc}")
            blocks["scoreboard"] = json.dumps({"data_gap": str(exc)})

        # (b) Evidence packs tail since last audit
        try:
            state = _read_audit_state(market, repo)
            last_graded = state.get(_STATE_KEY_GRADED)
            ev_path = _evidence_path(market, repo)
            # F1: use market-aware date key for evidence JSONL filtering
            ev_date_key = _DATE_COL.get(market, "as_of")
            if ev_path.exists():
                ev_rows = _read_jsonl_tail(ev_path, n=500)
                # Filter to rows since last audit; fall back to 'as_of' for cross-market safety
                if last_graded and ev_rows:
                    ev_rows = [
                        r for r in ev_rows
                        if str(r.get(ev_date_key) or r.get("as_of") or "") > last_graded
                    ]
                ev_text = "\n".join(
                    json.dumps(r, default=str) for r in ev_rows
                )
                blocks["evidence_packs"] = _truncate_bytes(ev_text, _EVIDENCE_BUDGET_BYTES)
            else:
                data_gaps.append(f"evidence_packs: {ev_path} absent")
                blocks["evidence_packs"] = json.dumps({"data_gap": str(ev_path)})
        except Exception as exc:  # noqa: BLE001
            data_gaps.append(f"evidence_packs: {exc}")
            blocks["evidence_packs"] = json.dumps({"data_gap": str(exc)})

        # (c) Coverage monitor (embedded in scoreboard or fitness card)
        try:
            sb_raw = _read_json(_scoreboard_path(market, repo)) if _scoreboard_path(market, repo).exists() else {}
            coverage = sb_raw.get("coverage_monitor") or sb_raw.get("coverage") or {}
            blocks["coverage_monitor"] = _json_truncated(coverage, _COVERAGE_BUDGET_BYTES)
        except Exception as exc:  # noqa: BLE001
            data_gaps.append(f"coverage_monitor: {exc}")
            blocks["coverage_monitor"] = json.dumps({"data_gap": str(exc)})

        # (d) Upstream concordance table (embedded in scoreboard)
        try:
            sb_raw2 = _read_json(_scoreboard_path(market, repo)) if _scoreboard_path(market, repo).exists() else {}
            concordance = sb_raw2.get("upstream_concordance") or {}
            blocks["concordance"] = _json_truncated(concordance, _CONCORDANCE_BUDGET_BYTES)
        except Exception as exc:  # noqa: BLE001
            data_gaps.append(f"concordance: {exc}")
            blocks["concordance"] = json.dumps({"data_gap": str(exc)})

        # (e) Fitness card
        try:
            fc_path = _fitness_path(market, repo)
            if fc_path.exists():
                fc = _read_json(fc_path)
                blocks["fitness_card"] = _json_truncated(fc, _FITNESS_BUDGET_BYTES)
            else:
                data_gaps.append(f"fitness_card: {fc_path} absent")
                blocks["fitness_card"] = json.dumps({"data_gap": str(fc_path)})
        except Exception as exc:  # noqa: BLE001
            data_gaps.append(f"fitness_card: {exc}")
            blocks["fitness_card"] = json.dumps({"data_gap": str(exc)})

        # (f) Prior post-mortems (anti-repetition)
        try:
            pm_dir = _postmortems_dir(repo)
            pm_files = sorted(pm_dir.glob(f"{market}-*.json"), reverse=True)[:_MAX_PRIOR_POSTMORTEMS]
            prior_pms = []
            for pm_path in pm_files:
                try:
                    pm_data = _read_json(pm_path)
                    if pm_data:
                        # Include only the summary fields to stay within budget
                        prior_pms.append({
                            "cycle_id": pm_data.get("cycle_id"),
                            "ts": pm_data.get("ts"),
                            "hypotheses": pm_data.get("hypotheses", [])[:3],
                            "honesty_notes": pm_data.get("honesty_notes"),
                        })
                except Exception:  # noqa: BLE001
                    continue
            blocks["prior_postmortems"] = _json_truncated(prior_pms, _PRIOR_PM_BUDGET_BYTES)
        except Exception as exc:  # noqa: BLE001
            data_gaps.append(f"prior_postmortems: {exc}")
            blocks["prior_postmortems"] = json.dumps({"data_gap": str(exc)})

        # (g) NW mission block
        try:
            mission_path = _nw_mission_path(repo)
            if mission_path.exists():
                mission_text = mission_path.read_text(encoding="utf-8")
                blocks["nw_mission"] = _truncate_bytes(mission_text, _MISSION_BUDGET_BYTES)
            else:
                data_gaps.append(f"nw_mission: {mission_path} absent")
                blocks["nw_mission"] = "(absent)"
        except Exception as exc:  # noqa: BLE001
            data_gaps.append(f"nw_mission: {exc}")
            blocks["nw_mission"] = "(error loading mission)"

        # (h) SA-R13 verbatim
        blocks["sa_r13"] = _SA_R13_VERBATIM

        return {
            "schema": SCHEMA_CONTEXT,
            "market": market,
            "ts": ts,
            "blocks": blocks,
            "data_gaps": data_gaps,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: build_context(%s): %s", market, exc)
        return {
            "schema": SCHEMA_CONTEXT,
            "market": market,
            "ts": _now_utc(),
            "blocks": {},
            "data_gaps": [f"build_context failed: {exc}"],
        }


# ---------------------------------------------------------------------------
# audit_due (SA-R9, stateless-cattle, NEVER raise)
# ---------------------------------------------------------------------------

def audit_due(market: str, root: Path | None = None) -> dict:
    """Determine whether a standout audit should run for the given market.

    SA-R9 trigger (stateless — derived from ledger state each call):
      newly_matured_graded_rows_since_last_audit >= 15
      OR (>= 5 AND >= 14 days since last postmortem)

    Returns:
      {
        "schema": "standout_auditor.audit_due.v1",
        "market": str,
        "due": bool,
        "reason": str,
        "newly_matured_rows": int,
        "days_since_postmortem": int | null,
        "last_audit_graded_as_of": str | null,
        "last_postmortem_cycle_id": str | null,
      }

    NEVER raises; returns due=False on any read error (fail-safe).
    """
    try:
        repo = _repo_root(root)
        state = _read_audit_state(market, repo)

        last_graded = state.get(_STATE_KEY_GRADED)
        last_pm_cycle = state.get(_STATE_KEY_PM_CYCLE)

        new_rows = _count_graded_rows_since_audit(market, repo, last_graded)

        # F1: -1 is the loud schema-error sentinel from _count_graded_rows_since_audit
        if new_rows < 0:
            return {
                "schema": SCHEMA_AUDIT_DUE,
                "market": market,
                "due": False,
                "reason": (
                    f"schema_error: attribution parquet for {market} missing expected "
                    f"column '{_DATE_COL.get(market, 'as_of')}' — check CN vs US schema; "
                    f"audit_due blocked to avoid false-zero trigger"
                ),
                "newly_matured_rows": 0,
                "days_since_postmortem": None,
                "last_audit_graded_as_of": last_graded,
                "last_postmortem_cycle_id": last_pm_cycle,
                "status": "schema_error",
            }

        days_pm = _days_since_last_postmortem(market, repo, last_pm_cycle)

        # SA-R9 trigger logic
        hard_trigger = new_rows >= _TRIGGER_NEW_ROWS_HARD
        soft_trigger = (
            new_rows >= _TRIGGER_NEW_ROWS_SOFT
            and days_pm is not None
            and days_pm >= _TRIGGER_DAYS_SINCE_PM
        )

        if hard_trigger:
            due = True
            reason = (
                f"hard trigger: {new_rows} newly matured graded rows "
                f">= {_TRIGGER_NEW_ROWS_HARD} threshold"
            )
        elif soft_trigger:
            due = True
            reason = (
                f"soft trigger: {new_rows} newly matured rows "
                f">= {_TRIGGER_NEW_ROWS_SOFT} AND {days_pm} days since last postmortem "
                f">= {_TRIGGER_DAYS_SINCE_PM}"
            )
        else:
            due = False
            days_str = str(days_pm) if days_pm is not None else "unknown"
            reason = (
                f"not due: {new_rows} newly matured rows "
                f"(hard threshold {_TRIGGER_NEW_ROWS_HARD}); "
                f"{days_str} days since last postmortem "
                f"(soft threshold requires {_TRIGGER_NEW_ROWS_SOFT} rows + {_TRIGGER_DAYS_SINCE_PM} days)"
            )

        return {
            "schema": SCHEMA_AUDIT_DUE,
            "market": market,
            "due": due,
            "reason": reason,
            "newly_matured_rows": new_rows,
            "days_since_postmortem": days_pm,
            "last_audit_graded_as_of": last_graded,
            "last_postmortem_cycle_id": last_pm_cycle,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: audit_due(%s): %s", market, exc)
        return {
            "schema": SCHEMA_AUDIT_DUE,
            "market": market,
            "due": False,
            "reason": f"audit_due check failed: {exc}",
            "newly_matured_rows": 0,
            "days_since_postmortem": None,
            "last_audit_graded_as_of": None,
            "last_postmortem_cycle_id": None,
        }


# ---------------------------------------------------------------------------
# audit_due_emitter — insight_bus registration (NEVER raise)
# ---------------------------------------------------------------------------

def audit_due_emitter(root: Path | None = None, cycle_id: str | None = None) -> list[dict]:
    """Emit insight_bus rows for markets where audit_due() == True.

    Registered in insight_bus.run_all_emitters().  Returns a list of bus rows.
    The kind 'audit_due' is in _KINDS (wired in insight_bus.py).

    F2 FIX: row identity is keyed on today_str (day granularity) and
    last_audit_graded_as_of so the insight_id is stable until the audit state
    actually advances.  Emits at most once per day per market (cooldown mirrors
    comeback_clock_emitter's today_str pattern in insight_bus.py:452).

    NEVER raises.
    """
    try:
        from engine.metabolism.insight_bus import (  # type: ignore[import]
            build_row, AUTHORITY_BLOCK,
        )
        # Day-granularity stable ts — same pattern as comeback_clock_emitter
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        rows: list[dict] = []
        for market in ("us", "cn"):
            try:
                result = audit_due(market, root=root)
                if not result.get("due"):
                    continue

                # Stable ts: day + last_audit_graded_as_of so insight_id
                # does not change between calls on the same day with the same
                # ledger state, enabling proper dedup in run_all_emitters.
                last_graded = result.get("last_audit_graded_as_of") or "none"
                stable_ts = f"{today_str}T00:00:00+00:00"

                row = build_row(
                    emitter=f"standout_auditor.{market}",
                    kind="audit_due",
                    severity="medium",
                    entities=[f"site-{market}-standouts", f"last_graded:{last_graded}"],
                    evidence_ref=None,
                    summary=(
                        f"standout audit due for {market.upper()}: "
                        f"{result.get('newly_matured_rows', 0)} newly matured rows — "
                        f"{result.get('reason', '')}"
                    ),
                    cycle_id=cycle_id,
                    ts=stable_ts,
                )
                rows.append(row)
            except Exception as exc:  # noqa: BLE001
                log.warning("standout_auditor: audit_due_emitter[%s]: %s", market, exc)
                continue
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: audit_due_emitter: %s", exc)
        return []


# ---------------------------------------------------------------------------
# LLM invocation (Opus-tier, hard-law; NEVER raise)
# ---------------------------------------------------------------------------

def _invoke_auditor_llm(
    context: dict,
    market: str,
    cycle_id: str,
    cfg: dict[str, Any] | None = None,
    model_caller: Callable | None = None,
) -> tuple[str | None, str | None]:
    """Call the Opus-tier LLM for the audit post-mortem.

    Returns (reply_text, provider_used).  NEVER raises.
    model_caller: optional injection point for tests (signature: (system, user) -> str | None).
    """
    try:
        blocks = context.get("blocks", {})
        data_gaps = context.get("data_gaps", [])

        system = (
            "You are the Standout Auditor — a stateless Opus analyst that reads "
            "evidence packs from the standout attribution pipeline and writes "
            "structured post-mortems.\n\n"
            "INERTNESS GUARANTEE: you write one artifact only. You dispatch nothing, "
            "grant nothing, open no PR, change no lobe roster, emit no signal, score, "
            "rank, or escalation. You are inert under AUTONOMY_PAUSED.\n\n"
            f"SA-R13 LAW (verbatim): {_SA_R13_VERBATIM}\n\n"
            "Your output MUST be a single JSON object with these keys:\n"
            "  per_cohort_postmortems: list of objects {cohort, outcome_cause_analysis, "
            "process_fault_analysis, remedy_class}\n"
            "  hypotheses: list of objects {rank, description, lane, fitness_contract, "
            "falsifiable_claim} where lane in ['standout_review', 'experiment book', 'code fix']\n"
            "  honesty_notes: string — what cannot be concluded at current effective n\n"
            "  market: string\n"
            "  cycle_id: string\n\n"
            "For hypotheses with lane='standout_review', also include: "
            "{market, param, delta_steps, rationale_ref, proposer} in the object — "
            "these become proposal files.\n\n"
            "fitness_contract must carry check_by >= sensor maturity_date "
            "(US: 2026-09-15, CN: 2026-10-15).\n"
            "Never use the word 'validated' in user-facing text."
        )

        user_parts = [
            f"MARKET: {market}",
            f"CYCLE_ID: {cycle_id}",
            "",
        ]
        if data_gaps:
            user_parts.append(f"DATA GAPS (honest null disclosure): {json.dumps(data_gaps)}")
            user_parts.append("")

        for block_name in (
            "scoreboard", "evidence_packs", "coverage_monitor",
            "concordance", "fitness_card", "prior_postmortems",
            "nw_mission", "sa_r13",
        ):
            block_val = blocks.get(block_name, "(absent)")
            user_parts.append(f"=== {block_name.upper()} ===")
            user_parts.append(block_val)
            user_parts.append("")

        user_parts.append("Write your structured post-mortem JSON now.")
        user = "\n".join(user_parts)

        # Injected model_caller (test seam)
        if model_caller is not None:
            try:
                result = model_caller(system, user)
                if isinstance(result, str):
                    return result, "injected"
                return None, "injected_returned_none"
            except Exception as exc:  # noqa: BLE001
                log.warning("standout_auditor: injected model_caller failed: %s", exc)
                return None, "injected_error"

        # Real LLM call via shared llm_auth waterfall
        conf = {**_LLM_CFG, **(cfg or {})}
        try:
            from engine import llm_auth  # type: ignore[import]
            providers = llm_auth.build_providers(
                conf,
                opus_model=conf.get("opus_model"),
                deepseek_model=conf.get("deepseek_model"),
            )
            if not providers:
                log.warning("standout_auditor: no LLM providers available")
                return None, "no_provider"

            max_tokens = int(conf.get("max_tokens", 6000))

            def _do_call(client: Any, model: str) -> tuple:
                resp = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    # temperature removed — rejected (400) on opus-4.7+ per Anthropic API
                )
                if getattr(resp, "stop_reason", None) == "refusal":
                    return None, "stop_refusal", resp
                text = "".join(
                    b.text for b in resp.content if getattr(b, "type", "") == "text"
                )
                return (text or None), None, resp

            text, reason, provider = llm_auth.make_call(
                providers, _do_call, context="standout_auditor"
            )
            return text, provider
        except Exception as exc:  # noqa: BLE001
            log.warning("standout_auditor: LLM invocation failed: %s", exc)
            return None, "llm_error"

    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: _invoke_auditor_llm: %s", exc)
        return None, "fatal_error"


def _parse_postmortem_json(text: str | None) -> dict | None:
    """Parse the LLM reply into a postmortem dict.  Returns None on failure."""
    if not text:
        return None
    try:
        import re
        s = text.strip()
        # Strip code fences
        if s.startswith("```"):
            s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
            s = re.sub(r"\n?```$", "", s).strip()
        # Try to parse JSON
        try:
            data = json.loads(s)
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            pass
        # Try to find JSON object in prose
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    return data
            except Exception:  # noqa: BLE001
                pass
        return None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Proposal file handoff (NEVER raise)
# ---------------------------------------------------------------------------

def _write_proposals(
    postmortem: dict,
    market: str,
    cycle_id: str,
    root: Path,
    dry_run: bool = False,
) -> list[str]:
    """Extract 'standout_review' hypotheses and write proposal files.

    F3 FIX (defense-in-depth): validates param against standout_review's
    canonical whitelist (_WHITELIST_CANONICAL_KEYS) before writing, clamps
    abs(delta_steps) <= 1, and records rejected hypotheses in the postmortem
    artifact under 'rejected_hypotheses' with reasons (honest, inert).

    dry_run=True: writes to shadow proposals dir (never real proposals/).
    Returns list of written paths.  NEVER raises.
    """
    written: list[str] = []
    rejected_hypotheses: list[dict] = []
    try:
        # Import the canonical whitelist from standout_review (single source of truth)
        try:
            from engine.standout_review import _WHITELIST_CANONICAL_KEYS as _WL_KEYS  # type: ignore[import]
            valid_params: frozenset[str] = _WL_KEYS
        except Exception:  # noqa: BLE001
            # Fallback: use the module-level copy (kept in sync at import time)
            valid_params = _PROPOSAL_REQUIRED_FIELDS  # minimal guard only
            log.warning("standout_auditor: cannot import _WHITELIST_CANONICAL_KEYS — "
                        "param validation uses fallback")

        hypotheses = postmortem.get("hypotheses") or []
        if dry_run:
            props_dir = _shadow_proposals_dir(root, cycle_id)
        else:
            props_dir = _proposals_dir(root)

        for i, hyp in enumerate(hypotheses):
            if not isinstance(hyp, dict):
                continue
            if str(hyp.get("lane") or "") != "standout_review":
                continue

            raw_param = str(hyp.get("param") or "")
            raw_delta = hyp.get("delta_steps")

            # F3: validate param against canonical whitelist
            if raw_param not in valid_params:
                reason = f"param_not_whitelisted:{raw_param!r}"
                log.warning(
                    "standout_auditor: proposal %d rejected — %s", i, reason
                )
                rejected_hypotheses.append({
                    "hypothesis_rank": i,
                    "param": raw_param,
                    "reason": reason,
                })
                continue

            # F3: clamp abs(delta_steps) <= 1
            try:
                delta_steps = int(raw_delta or 0)
            except (ValueError, TypeError):
                delta_steps = 0
            if abs(delta_steps) > 1:
                clamped = 1 if delta_steps > 0 else -1
                log.warning(
                    "standout_auditor: proposal %d delta_steps=%d clamped to %d",
                    i, delta_steps, clamped,
                )
                delta_steps = clamped

            # Build proposal dict matching standout_review.py schema
            proposal: dict[str, Any] = {
                "schema": "standout_review.proposal.v1",
                "ts": _now_utc(),
                "market": str(hyp.get("market") or market),
                "param": raw_param,
                "delta_steps": delta_steps,
                "rationale_ref": str(
                    hyp.get("rationale_ref")
                    or f"data/standout_audit/postmortems/{market}-{cycle_id}.json"
                ),
                "proposer": "standout_auditor",
                "cycle_id": cycle_id,
                "hypothesis_rank": i,
                "description": str(hyp.get("description") or ""),
                "fitness_contract": hyp.get("fitness_contract") or {},
            }

            # Validate required fields
            missing = [f for f in _PROPOSAL_REQUIRED_FIELDS if not proposal.get(f)]
            if missing:
                reason = f"missing_required_fields:{missing}"
                log.warning(
                    "standout_auditor: proposal %d rejected — %s", i, reason
                )
                rejected_hypotheses.append({
                    "hypothesis_rank": i,
                    "param": raw_param,
                    "reason": reason,
                })
                continue

            fname = f"{market}-{cycle_id}-prop{i:03d}.json"
            out_path = props_dir / fname
            try:
                out_path.write_text(
                    json.dumps(proposal, indent=2, default=str), encoding="utf-8"
                )
                written.append(str(out_path))
            except Exception as exc:  # noqa: BLE001
                log.warning("standout_auditor: write proposal %s: %s", out_path, exc)

        # Record rejected hypotheses in the postmortem dict (honest, inert)
        if rejected_hypotheses:
            postmortem["rejected_hypotheses"] = rejected_hypotheses

        return written
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: _write_proposals: %s", exc)
        return []


# ---------------------------------------------------------------------------
# insight_bus rows for non-standout_review hypotheses (NEVER raise)
# ---------------------------------------------------------------------------

def _emit_hypothesis_bus_rows(
    postmortem: dict,
    market: str,
    cycle_id: str,
    root: Path,
    dry_run: bool = False,
) -> list[str]:
    """Emit insight_bus rows for experiment/code-fix hypotheses.

    dry_run=True: writes to the shadow bus file (never appends the real bus).
    Returns list of emitted insight_ids.  NEVER raises.
    """
    emitted: list[str] = []
    try:
        from engine.metabolism.insight_bus import (  # type: ignore[import]
            build_row, append_row,
        )
        hypotheses = postmortem.get("hypotheses") or []
        for hyp in hypotheses:
            if not isinstance(hyp, dict):
                continue
            lane = str(hyp.get("lane") or "")
            if lane == "standout_review":
                continue  # handled by _write_proposals

            # Map lane to insight kind
            kind_map = {
                "experiment book": "health_transition",  # closest available kind
                "code fix": "contradiction",
            }
            kind = kind_map.get(lane, "health_transition")

            row = build_row(
                emitter=f"standout_auditor.{market}",
                kind=kind,
                severity="low",
                entities=[f"site-{market}-standouts"],
                evidence_ref=None,
                summary=(
                    f"[{lane}] hypothesis from {market.upper()} postmortem {cycle_id}: "
                    f"{str(hyp.get('description') or '')[:200]}"
                ),
                cycle_id=cycle_id,
            )
            try:
                if dry_run:
                    # F1: write to shadow bus file, never the real one
                    shadow_bus = _shadow_bus_path(root, cycle_id)
                    with shadow_bus.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    emitted.append(row.get("insight_id", ""))
                elif append_row(row, root=root):
                    emitted.append(row.get("insight_id", ""))
            except Exception as exc:  # noqa: BLE001
                log.warning("standout_auditor: append hypothesis row: %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: _emit_hypothesis_bus_rows: %s", exc)
    return emitted


# ---------------------------------------------------------------------------
# run_audit (NEVER raise)
# ---------------------------------------------------------------------------

def run_audit(
    market: str,
    cycle_id: str,
    model_caller: Callable | None = None,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the standout audit for the given market.

    dry_run=True behaviour (F1 fix — true by construction):
      - model_caller MUST be injected; None → status='refused' immediately.
        dry_run can never reach the real LLM waterfall.
      - ALL writes go under data/metabolism/shadow/<cycle_id>/standout_audit/
        (postmortem, proposals, insight-bus rows, audit_state cache).
        The real data/standout_audit/postmortems/, data/standout_review/proposals/,
        and data/metabolism/insight_bus.jsonl are never touched.
      - The AUTONOMY_PAUSED gate is skipped (shadow writes are inert).

    Armed (non-dry) run:
      1. Gate: AUTONOMY_PAUSED check — fail-closed when guard unavailable
      2. Build context (§5 blocks)
      3. Invoke Opus LLM via injected model_caller or real llm_auth waterfall
      4. Write postmortem (atomic temp→rename, keep-first per market/cycle_id)
      5. Write standout_review proposal files
      6. Emit insight_bus rows for experiment/code-fix hypotheses

    Returns a result dict with schema, market, cycle_id, status, artifact, note.
    NEVER raises.
    """
    try:
        repo = _repo_root(root)
        ts = _now_utc()

        # ── F1: dry_run contract — true by construction ───────────────────
        if dry_run:
            # (b) dry_run requires an injected model_caller — NEVER reaches real LLM
            if model_caller is None:
                return {
                    "schema": SCHEMA_POSTMORTEM,
                    "market": market,
                    "cycle_id": cycle_id,
                    "status": "refused",
                    "artifact": None,
                    "note": "dry_run requires injected model_caller — "
                            "dry_run can never reach the real LLM waterfall",
                }

            # Build context (reads real stores; write targets redirected below)
            context = build_context(market, root=repo)

            # Invoke LLM via injected caller only (no real provider waterfall)
            reply_text, provider = _invoke_auditor_llm(
                context, market, cycle_id, model_caller=model_caller
            )

            if not reply_text:
                return {
                    "schema": SCHEMA_POSTMORTEM,
                    "market": market,
                    "cycle_id": cycle_id,
                    "status": "no_llm_reply",
                    "artifact": None,
                    "note": f"injected model_caller returned no reply — provider={provider}",
                    "data_gaps": context.get("data_gaps", []),
                    "dry_run": True,
                }

            pm = _parse_postmortem_json(reply_text)
            if pm is None:
                pm = {"parse_failed": True, "raw_reply": reply_text[:2000]}

            pm.update({
                "schema": SCHEMA_POSTMORTEM,
                "market": market,
                "cycle_id": cycle_id,
                "ts": ts,
                "provider": provider,
                "data_gaps": context.get("data_gaps", []),
                "dry_run": True,
            })

            # (a) ALL writes → shadow dir; real stores NEVER touched
            # Postmortem: atomic temp→rename, keep-first per (market, cycle_id)
            pm_dir = _shadow_postmortems_dir(repo, cycle_id)
            pm_path = pm_dir / f"{market}-{cycle_id}.json"
            artifact_path: str | None = None
            try:
                # F1(f): keep-first — skip if postmortem already exists for this run
                if pm_path.exists():
                    log.info(
                        "standout_auditor[dry_run]: postmortem already exists at %s — skipping",
                        pm_path,
                    )
                    artifact_path = str(pm_path)
                else:
                    # Atomic write: temp file in same dir, then rename
                    import tempfile as _tempfile
                    tmp_fd, tmp_name = _tempfile.mkstemp(
                        dir=str(pm_dir), prefix=f".{market}-{cycle_id}-", suffix=".tmp"
                    )
                    try:
                        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                            fh.write(json.dumps(pm, indent=2, default=str))
                        os.replace(tmp_name, str(pm_path))
                        artifact_path = str(pm_path)
                    except Exception:  # noqa: BLE001
                        try:
                            os.unlink(tmp_name)
                        except Exception:  # noqa: BLE001
                            pass
                        raise
                log.info("standout_auditor[dry_run]: postmortem → %s", pm_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("standout_auditor[dry_run]: write postmortem: %s", exc)

            # Proposals → shadow proposals dir
            if not pm.get("parse_failed"):
                proposal_paths = _write_proposals(
                    pm, market, cycle_id, repo, dry_run=True
                )
                pm["_proposal_files"] = proposal_paths
            else:
                proposal_paths = []

            # insight_bus rows → shadow bus file
            if not pm.get("parse_failed"):
                emitted_ids = _emit_hypothesis_bus_rows(
                    pm, market, cycle_id, repo, dry_run=True
                )
                pm["_insight_bus_ids"] = emitted_ids
            else:
                emitted_ids = []

            return {
                "schema": SCHEMA_POSTMORTEM,
                "market": market,
                "cycle_id": cycle_id,
                "status": "ok" if artifact_path else "write_failed",
                "artifact": artifact_path,
                "note": (
                    f"[dry_run] shadow postmortem written; "
                    f"{len(proposal_paths)} proposals; "
                    f"{len(emitted_ids)} shadow bus rows; provider={provider}; "
                    f"real stores untouched"
                ),
                "data_gaps": context.get("data_gaps", []),
                "dry_run": True,
            }

        # ── Armed (non-dry) run ────────────────────────────────────────────

        # ── Inertness gate: AUTONOMY_PAUSED (mirrors dream.py) ───────────────
        try:
            from scripts.metabolism_guard import is_paused  # type: ignore[import]
            if is_paused():
                log.info("standout_auditor: AUTONOMY_PAUSED — skipping run_audit(%s)", market)
                return {
                    "schema": SCHEMA_POSTMORTEM,
                    "market": market,
                    "cycle_id": cycle_id,
                    "status": "paused",
                    "artifact": None,
                    "note": "AUTONOMY_PAUSED — audit skipped (inertness guarantee)",
                }
        except Exception:  # noqa: BLE001
            # Fail-closed: treat guard unavailable as PAUSED
            if os.environ.get("AUTONOMY_PAUSED", "").strip().lower() != "false":
                log.info(
                    "standout_auditor: guard unavailable + not explicitly armed — "
                    "skipping (fail-closed)"
                )
                return {
                    "schema": SCHEMA_POSTMORTEM,
                    "market": market,
                    "cycle_id": cycle_id,
                    "status": "paused",
                    "artifact": None,
                    "note": "guard unavailable, fail-closed — audit skipped",
                }

        # ── Build context ──────────────────────────────────────────────────
        context = build_context(market, root=repo)

        # ── Invoke LLM ────────────────────────────────────────────────────
        reply_text, provider = _invoke_auditor_llm(
            context, market, cycle_id, model_caller=model_caller
        )

        if not reply_text:
            log.warning(
                "standout_auditor: no LLM reply for %s/%s (provider=%s)",
                market, cycle_id, provider,
            )
            return {
                "schema": SCHEMA_POSTMORTEM,
                "market": market,
                "cycle_id": cycle_id,
                "status": "no_llm_reply",
                "artifact": None,
                "note": f"LLM returned no reply — provider={provider}",
                "data_gaps": context.get("data_gaps", []),
            }

        # ── Parse postmortem ──────────────────────────────────────────────
        pm = _parse_postmortem_json(reply_text)
        if pm is None:
            # Store raw reply for forensics
            pm = {
                "parse_failed": True,
                "raw_reply": reply_text[:2000],
            }
            log.warning(
                "standout_auditor: postmortem parse failed for %s/%s",
                market, cycle_id,
            )

        # ── Enrich postmortem ─────────────────────────────────────────────
        pm.update({
            "schema": SCHEMA_POSTMORTEM,
            "market": market,
            "cycle_id": cycle_id,
            "ts": ts,
            "provider": provider,
            "data_gaps": context.get("data_gaps", []),
        })

        # ── Write postmortem artifact (F1f: atomic, keep-first) ───────────
        pm_dir = _postmortems_dir(repo)
        pm_path = pm_dir / f"{market}-{cycle_id}.json"
        artifact_path = None
        try:
            # F1(f): keep-first — if this (market, cycle_id) postmortem already exists, skip
            if pm_path.exists():
                log.info(
                    "standout_auditor: postmortem already exists at %s — skipping write "
                    "(keep-first per market/cycle_id)",
                    pm_path,
                )
                artifact_path = str(pm_path)
            else:
                # Atomic write: temp file in same dir, then os.replace
                import tempfile as _tempfile
                tmp_fd, tmp_name = _tempfile.mkstemp(
                    dir=str(pm_dir), prefix=f".{market}-{cycle_id}-", suffix=".tmp"
                )
                try:
                    with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                        fh.write(json.dumps(pm, indent=2, default=str))
                    os.replace(tmp_name, str(pm_path))
                    artifact_path = str(pm_path)
                except Exception:  # noqa: BLE001
                    try:
                        os.unlink(tmp_name)
                    except Exception:  # noqa: BLE001
                        pass
                    raise
            log.info(
                "standout_auditor: postmortem written to %s (provider=%s)",
                pm_path, provider,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("standout_auditor: write postmortem %s: %s", pm_path, exc)

        # ── Write standout_review proposal files ──────────────────────────
        if not pm.get("parse_failed"):
            proposal_paths = _write_proposals(pm, market, cycle_id, repo, dry_run=False)
            pm["_proposal_files"] = proposal_paths
        else:
            proposal_paths = []

        # ── Emit insight_bus rows for other hypotheses ────────────────────
        if not pm.get("parse_failed"):
            emitted_ids = _emit_hypothesis_bus_rows(pm, market, cycle_id, repo, dry_run=False)
            pm["_insight_bus_ids"] = emitted_ids
        else:
            emitted_ids = []

        # ── F2: advance the audit cursor in the state file ────────────────
        # Write last_audit_graded_as_of and last_postmortem_cycle_id so that
        # subsequent audit_due() calls see an advanced cursor and do not
        # immediately re-trigger (the cursor was never written before this fix).
        # NEVER raises (NEVER-RAISE contract).
        try:
            sp = _state_path(market, repo)
            sp.parent.mkdir(parents=True, exist_ok=True)
            existing_state: dict = {}
            if sp.exists():
                try:
                    existing_state = json.loads(sp.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    existing_state = {}
            # Read the current max date from the attribution parquet to stamp cursor
            date_col = _DATE_COL.get(market, "as_of")
            new_graded_asof: str | None = None
            try:
                attr_p = _attribution_path(market, repo)
                if attr_p.exists():
                    import pandas as pd  # type: ignore[import]
                    _df = pd.read_parquet(str(attr_p), columns=[date_col])
                    if not _df.empty:
                        new_graded_asof = str(_df[date_col].max())
            except Exception:  # noqa: BLE001
                pass
            existing_state[_STATE_KEY_GRADED] = new_graded_asof or ts
            existing_state[_STATE_KEY_PM_CYCLE] = cycle_id
            existing_state["last_run_utc"] = ts
            sp.write_text(json.dumps(existing_state, indent=2, default=str), encoding="utf-8")
            log.info(
                "standout_auditor: audit cursor advanced → %s=%s, %s=%s",
                _STATE_KEY_GRADED, existing_state[_STATE_KEY_GRADED],
                _STATE_KEY_PM_CYCLE, cycle_id,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("standout_auditor: failed to write audit state cursor: %s", exc)

        return {
            "schema": SCHEMA_POSTMORTEM,
            "market": market,
            "cycle_id": cycle_id,
            "status": "ok" if artifact_path else "write_failed",
            "artifact": artifact_path,
            "note": (
                f"postmortem written; {len(proposal_paths)} proposals; "
                f"{len(emitted_ids)} insight_bus rows; provider={provider}"
            ),
            "data_gaps": context.get("data_gaps", []),
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: run_audit(%s, %s): %s", market, cycle_id, exc)
        return {
            "schema": SCHEMA_POSTMORTEM,
            "market": market,
            "cycle_id": cycle_id,
            "status": "error",
            "artifact": None,
            "note": f"run_audit failed: {exc}",
            "data_gaps": [],
        }


# ---------------------------------------------------------------------------
# PR-R3: Per-pick autopsy stage (Prophet W2)
# ---------------------------------------------------------------------------

# Closed enum for mitigation_verdict (PR-R3 spec)
_MITIGATION_VERDICTS = frozenset({
    "mitigable_process",
    "mitigable_conditioning",
    "external_unforeseeable",
    "external_foreseeable_unpriced",
    "not_a_failure",
})

SCHEMA_PICK_AUTOPSY = "prophet.pick_autopsy/v1"


def _autopsy_cap_from_config(root: Path) -> int:
    """Read prophet.autopsy_cap_per_cycle from config.yml, fail-soft to 12."""
    try:
        from lib import config as _cfg  # noqa: PLC0415
        data = _cfg.load()
        cap = data.get("prophet", {}).get("autopsy_cap_per_cycle", 12)
        return int(cap)
    except Exception:  # noqa: BLE001
        return 12


def _autopsy_dir(market: str, root: Path) -> Path:
    """Return the per-market autopsy directory, creating it if needed."""
    p = root / "data" / "standout_audit" / "pick_autopsies" / market
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    return p


def select_autopsy_picks(
    market: str,
    attribution_df,  # pd.DataFrame
    cap: int = 12,
) -> list[dict]:
    """Select picks for per-pick autopsy: extremes-first, capped.

    Selection order (PR-R3):
    1. ALL gate_suppressed rows
    2. ALL data_fault rows
    3. Top-K winners by excess_21d (highest excess first)
    4. Bottom-K losers by excess_21d (lowest excess first)
    K is derived from cap after mandatory rows are allocated.

    Returns list of row dicts from the attribution frame.  NEVER raises.
    """
    try:
        import pandas as pd  # noqa: PLC0415
        if attribution_df is None or attribution_df.empty:
            return []

        df = attribution_df.copy()

        # Identify process_fault column
        pf_col = "process_fault"
        if pf_col not in df.columns:
            return []

        # Mandatory rows
        suppressed_mask = df[pf_col] == "gate_suppressed"
        fault_mask = df[pf_col] == "data_fault"
        mandatory_rows = df[suppressed_mask | fault_mask]

        # Identify excess column for ranking
        excess_col = None
        for candidate in ("excess_spy", "excess_21d", "excess_sector"):
            if candidate in df.columns:
                excess_col = candidate
                break

        # Extremes from non-mandatory rows
        non_mandatory = df[~(suppressed_mask | fault_mask)]
        top_k_rows = []
        bottom_k_rows = []
        if excess_col and not non_mandatory.empty:
            remaining_cap = max(0, cap - len(mandatory_rows))
            k = max(1, remaining_cap // 2)
            non_mandatory_sorted = non_mandatory.sort_values(excess_col, ascending=False)
            top_k_rows = non_mandatory_sorted.head(k).to_dict("records")
            bottom_k_rows = non_mandatory_sorted.tail(k).to_dict("records")

        mandatory_list = mandatory_rows.to_dict("records")

        # Combine: mandatory first, then extremes; deduplicate by pick identity
        seen: set[tuple] = set()
        result: list[dict] = []
        for row in [*mandatory_list, *top_k_rows, *bottom_k_rows]:
            key = (
                str(row.get("ticker", "")),
                str(row.get("as_of", row.get("entry_date", ""))),
                str(row.get("lane", "")),
            )
            if key not in seen:
                seen.add(key)
                result.append(row)
            if len(result) >= cap:
                break
        return result[:cap]
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: select_autopsy_picks(%s): %s", market, exc)
        return []


def _pick_id(row: dict) -> str:
    """Build a stable pick identifier from the attribution row."""
    ticker = str(row.get("ticker", "")).replace("/", "_").replace(" ", "_")
    asof = str(row.get("as_of", row.get("entry_date", "unknown"))).split("T")[0]
    lane = str(row.get("lane", "default"))
    return f"{ticker}-{asof}-{lane}"


def _invoke_autopsy_llm(
    market: str,
    picks: list[dict],
    cycle_id: str,
    model_caller: Callable | None,
    root: Path,
) -> list[dict]:
    """Invoke LLM for per-pick autopsies in a single batched call.

    Returns a list of parsed autopsy dicts (one per pick).
    model_caller must be injected (dry_run contract).  NEVER raises.
    """
    if not picks or model_caller is None:
        return []

    try:
        # Build the batch prompt
        picks_summary = []
        for i, pick in enumerate(picks):
            picks_summary.append(
                f"Pick {i+1}: {pick.get('ticker')} | "
                f"date={pick.get('as_of', pick.get('entry_date', '?'))} | "
                f"lane={pick.get('lane', '?')} | "
                f"outcome_cause={pick.get('outcome_cause', '?')} | "
                f"process_fault={pick.get('process_fault', '?')} | "
                f"excess_spy={pick.get('excess_spy', '?')} | "
                f"sector={pick.get('sector', '?')} | "
                f"board_tenure_days={pick.get('board_tenure_days', '?')} | "
                f"quad_hard_label={pick.get('quad_hard_label', '?')} | "
                f"terminal_state={pick.get('terminal_state_clean8_21', '?')}"
            )

        picks_text = "\n".join(picks_summary)

        prompt = f"""You are the Prophet standout-audit lobe for the {market.upper()} market.
Analyze these {len(picks)} matured picks from audit cycle {cycle_id} and write
a per-pick postmortem for each.

SA-R13 VERBATIM (non-negotiable):
{_SA_R13_VERBATIM}

Operator cause taxonomy (Prophet §3):
Failures: missed/late sector-rotation read; extended-sector rollover;
fake breakout/failed cycle; external news/event (check ex-ante visibility);
process faults (chased late, gate margin thin, stale data).
Successes: rotation identified early; T1-T4 confluence timing; momentum preceding news;
external re-rating with visible ex-ante accumulation.

For EACH pick, you MUST produce:
- root_cause: 1-3 sentences naming what drove the outcome (was it mitigable?)
- mitigation_verdict: EXACTLY one of: mitigable_process | mitigable_conditioning |
  external_unforeseeable | external_foreseeable_unpriced | not_a_failure
- lesson: 1 sentence tagging which engines/books surfaced or missed this
- engines_credit: 1 sentence naming which books/organs were role models or laggards

DO NOT include any numbers, percentages, or scores in your prose — those come from
the attribution system. Write ONLY prose + the closed enum verdict.

Picks to analyze:
{picks_text}

Return a JSON array of objects, one per pick, in the SAME ORDER as the picks above.
Each object must have exactly these keys:
  pick_index (int, 1-based)
  root_cause (str)
  mitigation_verdict (str, must be exactly one of the closed enum values)
  lesson (str)
  engines_credit (str)
"""

        reply_text = None
        try:
            result = model_caller(prompt)
            if isinstance(result, tuple):
                reply_text = result[0]
            else:
                reply_text = str(result) if result else None
        except Exception as exc:  # noqa: BLE001
            log.warning("standout_auditor: autopsy LLM call failed: %s", exc)
            return []

        if not reply_text:
            return []

        # Parse JSON array
        parsed: list[dict] = []
        try:
            # Find JSON array in the reply
            import re  # noqa: PLC0415
            match = re.search(r'\[.*\]', reply_text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
        except Exception:  # noqa: BLE001
            pass

        if not isinstance(parsed, list):
            return []

        # Validate verdicts, normalize
        result_list: list[dict] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            verdict = str(item.get("mitigation_verdict", "")).strip()
            if verdict not in _MITIGATION_VERDICTS:
                verdict = "external_unforeseeable"  # safe fallback
            result_list.append({
                "pick_index": item.get("pick_index"),
                "root_cause": str(item.get("root_cause", ""))[:500],
                "mitigation_verdict": verdict,
                "lesson": str(item.get("lesson", ""))[:300],
                "engines_credit": str(item.get("engines_credit", ""))[:300],
            })
        return result_list

    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: _invoke_autopsy_llm: %s", exc)
        return []


def _write_pick_autopsies(
    market: str,
    picks: list[dict],
    llm_results: list[dict],
    cycle_id: str,
    model: str,
    root: Path,
    dry_run: bool = False,
) -> list[str]:
    """Write per-pick autopsy artifacts.

    One file per pick at data/standout_audit/pick_autopsies/<market>/<pick_id>.json.
    Returns list of written file paths.  NEVER raises.
    """
    written: list[str] = []
    ts = _now_utc()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Build LLM result map by pick_index
    llm_by_idx: dict[int, dict] = {}
    for r in llm_results:
        idx = r.get("pick_index")
        if idx is not None:
            llm_by_idx[int(idx)] = r

    try:
        if dry_run:
            autopsy_dir = _shadow_base(root, cycle_id) / "pick_autopsies" / market
        else:
            autopsy_dir = _autopsy_dir(market, root)
        autopsy_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: _write_pick_autopsies: mkdir failed: %s", exc)
        return written

    for i, pick in enumerate(picks, start=1):
        pick_id = _pick_id(pick)
        autopsy_path = autopsy_dir / f"{pick_id}.json"

        # LLM block
        llm_block = llm_by_idx.get(i) or {}
        llm_doc = {
            "root_cause": llm_block.get("root_cause", ""),
            "mitigation_verdict": llm_block.get("mitigation_verdict", ""),
            "lesson": llm_block.get("lesson", ""),
            "engines_credit": llm_block.get("engines_credit", ""),
        }

        # Validate verdict; if missing, mark clearly
        if llm_doc["mitigation_verdict"] not in _MITIGATION_VERDICTS:
            if llm_doc["root_cause"]:
                llm_doc["mitigation_verdict"] = "external_unforeseeable"
            else:
                llm_doc["mitigation_verdict"] = ""

        doc = {
            "schema": SCHEMA_PICK_AUTOPSY,
            "market": market,
            "pick_id": pick_id,
            "ticker": pick.get("ticker"),
            "entry_date": pick.get("as_of", pick.get("entry_date")),
            "ledger_key": {
                "ticker": pick.get("ticker"),
                "as_of": pick.get("as_of", pick.get("entry_date")),
                "lane": pick.get("lane"),
                "horizon": pick.get("horizon"),
            },
            "attribution": {k: v for k, v in pick.items()
                            if not k.startswith("_")},
            "llm": llm_doc,
            "model": model,
            "cycle_id": cycle_id,
            "asof": today,
            "ts": ts,
        }

        try:
            import tempfile as _tempfile  # noqa: PLC0415
            tmp_fd, tmp_name = _tempfile.mkstemp(
                dir=str(autopsy_dir), prefix=f".{pick_id}-", suffix=".tmp"
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(doc, indent=2, default=str))
                os.replace(tmp_name, str(autopsy_path))
                written.append(str(autopsy_path))
                log.debug("standout_auditor: pick autopsy → %s", autopsy_path)
            except Exception:  # noqa: BLE001
                try:
                    os.unlink(tmp_name)
                except Exception:  # noqa: BLE001
                    pass
                raise
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "standout_auditor: write pick autopsy %s: %s", autopsy_path, exc
            )

    log.info(
        "standout_auditor: wrote %d/%d pick autopsies for %s/%s%s",
        len(written), len(picks), market, cycle_id,
        " [dry_run]" if dry_run else "",
    )
    return written


def run_pick_autopsies(
    market: str,
    cycle_id: str,
    model_caller: Callable | None = None,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Run per-pick autopsy stage for a given market and cycle.

    Selects autopsy picks from the attribution parquet, invokes LLM in a single
    batched call, writes per-pick artifacts.

    dry_run=True: model_caller MUST be injected; writes go to shadow dir.
    Armed run: AUTONOMY_PAUSED gate applies.

    Cursor semantics: autopsies ride the same cycle as the cohort postmortem.
    A crash before postmortem commit re-derives idempotently — the autopsy cursor
    does NOT advance independently.

    NEVER raises.  Returns status dict.
    """
    try:
        repo = _repo_root(root)

        if dry_run and model_caller is None:
            return {
                "schema": SCHEMA_PICK_AUTOPSY,
                "market": market,
                "cycle_id": cycle_id,
                "status": "refused",
                "note": "dry_run requires injected model_caller",
                "written": [],
            }

        if not dry_run:
            # AUTONOMY_PAUSED gate (mirrors run_audit)
            try:
                from scripts.metabolism_guard import is_paused  # type: ignore[import]
                if is_paused():
                    return {
                        "schema": SCHEMA_PICK_AUTOPSY,
                        "market": market,
                        "cycle_id": cycle_id,
                        "status": "paused",
                        "note": "AUTONOMY_PAUSED — autopsy skipped",
                        "written": [],
                    }
            except Exception:  # noqa: BLE001
                if os.environ.get("AUTONOMY_PAUSED", "").strip().lower() != "false":
                    return {
                        "schema": SCHEMA_PICK_AUTOPSY,
                        "market": market,
                        "cycle_id": cycle_id,
                        "status": "paused",
                        "note": "guard unavailable, fail-closed",
                        "written": [],
                    }

        # Read attribution parquet
        attr_path = _attribution_path(market, repo)
        if not attr_path.exists():
            return {
                "schema": SCHEMA_PICK_AUTOPSY,
                "market": market,
                "cycle_id": cycle_id,
                "status": "data_gap",
                "note": f"attribution parquet absent: {attr_path}",
                "written": [],
            }

        try:
            import pandas as pd  # noqa: PLC0415
            attr_df = pd.read_parquet(str(attr_path))
        except Exception as exc:  # noqa: BLE001
            return {
                "schema": SCHEMA_PICK_AUTOPSY,
                "market": market,
                "cycle_id": cycle_id,
                "status": "data_gap",
                "note": f"attribution parquet read error: {exc}",
                "written": [],
            }

        cap = _autopsy_cap_from_config(repo)
        picks = select_autopsy_picks(market, attr_df, cap=cap)

        if not picks:
            return {
                "schema": SCHEMA_PICK_AUTOPSY,
                "market": market,
                "cycle_id": cycle_id,
                "status": "no_picks",
                "note": "no picks selected for autopsy (attribution accruing)",
                "written": [],
            }

        # LLM batch call
        llm_results = _invoke_autopsy_llm(
            market, picks, cycle_id, model_caller, repo
        )

        # Write artifacts
        written = _write_pick_autopsies(
            market, picks, llm_results, cycle_id,
            model=_OPUS_MODEL,
            root=repo,
            dry_run=dry_run,
        )

        return {
            "schema": SCHEMA_PICK_AUTOPSY,
            "market": market,
            "cycle_id": cycle_id,
            "status": "ok" if written else "write_failed",
            "note": (
                f"{len(written)}/{len(picks)} autopsies written; "
                f"{len(llm_results)} LLM results; dry_run={dry_run}"
            ),
            "written": written,
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("standout_auditor: run_pick_autopsies(%s, %s): %s",
                    market, cycle_id, exc)
        return {
            "schema": SCHEMA_PICK_AUTOPSY,
            "market": market,
            "cycle_id": cycle_id,
            "status": "error",
            "note": f"run_pick_autopsies failed: {exc}",
            "written": [],
        }
