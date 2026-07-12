"""engine.metabolism.standout_auditor — SA-W3: standout-lobe audit organ.

Implements the stateless-cattle auditor that triggers post-mortems on standout
attribution data when enough newly-matured graded rows accumulate (SA-R9).

NEVER-RAISE CONTRACT: every public function catches ALL exceptions and returns
a safe fallback.  An auditor failure must never abort the metabolism cycle.

INERTNESS GUARANTEE: this module writes artifacts only.  It dispatches nothing,
grants nothing, escalates nothing, opens no PR, changes no lobe roster.
It is inert under AUTONOMY_PAUSED (same guard as dream.py).

SHADOW / DRY-RUN MODE: run_audit() accepts a dry_run= flag; when dry_run=True
it writes to shadow_root instead of the real standout_audit/ path.

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
    """Read the audit state JSON for the given market.  Returns {} on any error."""
    try:
        p = _state_path(market, root)
        if not p.exists():
            return {}
        return _read_json(p) or {}
    except Exception:  # noqa: BLE001
        return {}


def _count_graded_rows_since_audit(market: str, root: Path, last_audit_graded_as_of: str | None) -> int:
    """Count newly matured graded rows since the last audit.

    Uses the attribution parquet if available, else falls back to evidence JSONL.
    'Newly matured' means rows whose as_of > last_audit_graded_as_of (or all
    rows if last_audit_graded_as_of is None/absent).
    NEVER raises.
    """
    try:
        attr_p = _attribution_path(market, root)
        if attr_p.exists():
            try:
                import pandas as pd  # type: ignore[import]
                df = pd.read_parquet(str(attr_p), columns=["as_of"])
                if df.empty:
                    return 0
                if last_audit_graded_as_of:
                    # Count rows with as_of strictly after the last audit snapshot
                    df["as_of"] = pd.to_datetime(df["as_of"], errors="coerce")
                    cutoff = pd.to_datetime(last_audit_graded_as_of, errors="coerce")
                    if cutoff is not pd.NaT:  # type: ignore[comparison-overlap]
                        return int((df["as_of"] > cutoff).sum())
                return len(df)
            except Exception:  # noqa: BLE001
                pass

        # Fallback: count evidence JSONL rows
        ev_p = _evidence_path(market, root)
        if not ev_p.exists():
            return 0
        rows = _read_jsonl_tail(ev_p, n=10_000)
        if not rows:
            return 0
        if last_audit_graded_as_of:
            return sum(
                1 for r in rows
                if str(r.get("as_of") or "") > last_audit_graded_as_of
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
            last_graded = state.get("last_audit_graded_as_of")
            ev_path = _evidence_path(market, repo)
            if ev_path.exists():
                ev_rows = _read_jsonl_tail(ev_path, n=500)
                # Filter to rows since last audit
                if last_graded and ev_rows:
                    ev_rows = [r for r in ev_rows if str(r.get("as_of") or "") > last_graded]
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

        last_graded = state.get("last_audit_graded_as_of")
        last_pm_cycle = state.get("last_postmortem_cycle_id")

        new_rows = _count_graded_rows_since_audit(market, repo, last_graded)
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
    NEVER raises.
    """
    try:
        from engine.metabolism.insight_bus import (  # type: ignore[import]
            build_row, AUTHORITY_BLOCK,
        )
        rows: list[dict] = []
        for market in ("us", "cn"):
            try:
                result = audit_due(market, root=root)
                if not result.get("due"):
                    continue
                row = build_row(
                    emitter=f"standout_auditor.{market}",
                    kind="audit_due",
                    severity="medium",
                    entities=[f"site-{market}-standouts"],
                    evidence_ref=None,
                    summary=(
                        f"standout audit due for {market.upper()}: "
                        f"{result.get('newly_matured_rows', 0)} newly matured rows — "
                        f"{result.get('reason', '')}"
                    ),
                    cycle_id=cycle_id,
                    authority=AUTHORITY_BLOCK,
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

            def _do_call(client: Any, model: str) -> tuple[str | None, str | None]:
                resp = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    temperature=0,
                )
                if getattr(resp, "stop_reason", None) == "refusal":
                    return None, "stop_refusal"
                text = "".join(
                    b.text for b in resp.content if getattr(b, "type", "") == "text"
                )
                return (text or None), None

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
) -> list[str]:
    """Extract 'standout_review' hypotheses and write proposal files.

    Returns list of written paths.  NEVER raises.
    """
    written: list[str] = []
    try:
        hypotheses = postmortem.get("hypotheses") or []
        props_dir = _proposals_dir(root)

        for i, hyp in enumerate(hypotheses):
            if not isinstance(hyp, dict):
                continue
            if str(hyp.get("lane") or "") != "standout_review":
                continue

            # Build proposal dict matching standout_review.py schema
            proposal: dict[str, Any] = {
                "schema": "standout_review.proposal.v1",
                "ts": _now_utc(),
                "market": str(hyp.get("market") or market),
                "param": str(hyp.get("param") or ""),
                "delta_steps": int(hyp.get("delta_steps") or 0),
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
                log.warning(
                    "standout_auditor: proposal %d missing fields %s — skipping",
                    i, missing,
                )
                continue
            if not proposal["param"]:
                log.warning("standout_auditor: proposal %d has empty param — skipping", i)
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
) -> list[str]:
    """Emit insight_bus rows for experiment/code-fix hypotheses.

    Returns list of emitted insight_ids.  NEVER raises.
    """
    emitted: list[str] = []
    try:
        from engine.metabolism.insight_bus import (  # type: ignore[import]
            build_row, append_row, AUTHORITY_BLOCK,
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
                authority=AUTHORITY_BLOCK,
            )
            try:
                if append_row(row, root=root):
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

    1. Gate: AUTONOMY_PAUSED check (inert when paused, unless dry_run=True)
    2. Gate: armed check — fail-closed unless explicitly armed
    3. Build context (§5 blocks)
    4. Invoke Opus LLM via shared llm_auth waterfall
    5. Write postmortem artifact to data/standout_audit/postmortems/<market>-<cycle_id>.json
    6. Write standout_review proposal files for 'standout_review' lane hypotheses
    7. Emit insight_bus rows for experiment/code-fix hypotheses

    Returns a result dict with schema, market, cycle_id, status, artifact, note.
    NEVER raises.
    """
    try:
        repo = _repo_root(root)
        ts = _now_utc()

        # ── Inertness gate: AUTONOMY_PAUSED (mirrors dream.py) ───────────────
        if not dry_run:
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

        # ── Write postmortem artifact ─────────────────────────────────────
        pm_dir = _postmortems_dir(repo)
        pm_path = pm_dir / f"{market}-{cycle_id}.json"
        artifact_path: str | None = None
        try:
            pm_path.write_text(json.dumps(pm, indent=2, default=str), encoding="utf-8")
            artifact_path = str(pm_path)
            log.info(
                "standout_auditor: postmortem written to %s (provider=%s)",
                pm_path, provider,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("standout_auditor: write postmortem %s: %s", pm_path, exc)

        # ── Write standout_review proposal files ──────────────────────────
        if not pm.get("parse_failed"):
            proposal_paths = _write_proposals(pm, market, cycle_id, repo)
            pm["_proposal_files"] = proposal_paths
        else:
            proposal_paths = []

        # ── Emit insight_bus rows for other hypotheses ────────────────────
        if not pm.get("parse_failed"):
            emitted_ids = _emit_hypothesis_bus_rows(pm, market, cycle_id, repo)
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
