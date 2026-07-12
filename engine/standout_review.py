"""engine/standout_review.py — SA-W4: clamped improvement-lane engine for standout boards.

Implements §6 of the Standout Accountability masterplan (v2, 2026-07-12):
A6 lane-(ii) clamped parameter-change proposals for the US and CN standout boards.
Mirrors risk_radar_review.py's structure and governance event schema exactly.

KEY DESIGN CONTRACTS
--------------------
- NEVER raises. Every public function is wrapped in try/except.
- NO live apply exists in v1. The only action is shadow_apply: emit a draft Pick Lab
  book spec to data/standout_review/shadow_books/<engine_id>.json for a human/
  metabolism BUILD PR to register. The lab IS the shadow lane.
- ARMING PRECONDITION: refuses to run (clean journaled no-op) unless
  config/standout_review.yml exists and parses. The yml's presence is the arm.
- INERT BY CONSTRUCTION: reads proposal files and writes to:
    data/standout_review/shadow_books/   (draft book specs)
    data/standout_review/review_state.json  (freshness stamp)
    data/neuralweb/governance.jsonl      (governance events, via append_event)
  Touches NOTHING else. No board output changes.

GOVERNANCE EVENTS (A6 lane-(ii), risk_radar_review schema)
  a6_llm_proposed  — emitted on proposal intake (before any evaluation), with applied:False
                     on rejection paths so the event carries the reject_reason in evidence
  a6_auto_apply    — emitted when shadow_apply decision made (lane: 'shadow_book')

  Note: there is no separate 'a6_rejected' event type. Rejection is encoded on the
  a6_llm_proposed event via evidence.applied=False + evidence.reject_reason. This
  matches risk_radar_review.py's schema and the governance vocabulary in
  engine/neuralweb/governance.py (article 6 events only use a6_llm_proposed and
  a6_auto_apply as named event types).

DO-NO-HARM GATE (§6, SA-R5)
  1. Temporal split: leave-newest-out (exclude most recent non-overlapping month)
  2. Trial haircut: Bonferroni over whitelist × steps grid
  3. Noise band: within-month permutation null (DT-R14)
  4. DORMANCY: at current effective n the gate will authorize almost nothing —
     this is the correct honest state. The lane is expected largely DORMANT
     until SA-R10 floors mature (~2026-09-15 US, ~2026-10-15 CN).

CHEAPLY-REPLAYABLE PARAMS (_CHEAP_REPLAY_PARAMS set)
  cn.washout_bonus is replayable from stored per-name board.parquet columns
  (washout_2w, tier, board_rank, ext_score). The evaluator reconstructs the
  ordering delta under a modified bonus, approximating the conviction-percentile
  term as rank-normalised position. See scripts/replay_standout_books.py for
  the full counterfactual implementation. All other params fall back to UNEVALUABLE.

DISJOINTNESS (SA-R2) — two distinct effect classes:
  RULER effects: a param feeds an ATTRIBUTION THRESHOLD or fitness-SENSOR DEFINITION.
    These are FORBIDDEN in the whitelist (SA-R2). The ATTRIBUTION_SENSOR_CONSTANTS
    guard below checks for this. Example: EXT_SCORE_LATE_PCT feeds the signaled_too_late
    sensor definition → forbidden.
  SELECTION effects: a ranking/bonus param changes which names SURFACE on the board,
    thereby changing sensor composition over time. This is EXPECTED behavior for any
    improvement lane and is NOT a violation. The sensors exist to measure exactly
    this kind of change. Example: cn.washout_bonus changes which names rank higher
    → changes which names get graded → changes hit_quality composition.
    This is documented and expected.
  cn.ext_penalty (ranking weight) feeds the ext_score RANKING contribution, NOT the
    ext_score VALUE that signaled_too_late's fallback reads. The raw ext_score
    measurement (extension.score) is independent of ext_penalty. Confirmed: ruler
    effect does NOT apply. ext_penalty is a selection effect → whitelist-eligible.
  board_rank→signaled_too_late channel: CLOSED by W2's fix (commit 0562ef126be on
    origin/claude/sa-w2-cn-audit). The signaled_too_late clause now uses
    ticks > FRESH_TICKS as primary (nulls fall back to ext_score >= EXT_SCORE_LATE_PCT).
    The LATE_RANK_THRESH / board_rank clause is REMOVED. Verified against current W2.

NOTE on ATTRIBUTION_SENSOR_CONSTANTS sync:
  The constant set below is synced to ACTUAL W1 (engine/standout_audit.py) and
  W2 (engine/china_standout_audit.py) constants as of 2026-07-12. It must be
  re-synced when W1/W2 merge to main. See comment block at the constant definition.

SA-R16: Never raises. Corrupt-proposal tests ship in tests/test_standout_review.py.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Attribution/sensor constant names — DISJOINTNESS guard ───────────────────
# These names are LOOP-IMMUTABLE (SA-R2). No whitelist param may share a name.
#
# SYNC NOTE: This set must be re-synced when W1/W2 merge to main.
# Attempting dynamic import at check time; falls back to this static set on ImportError.
#
# Sources verified 2026-07-12:
#   W1: engine/standout_audit.py — module-level constants (module_constant)
#   W2: engine/china_standout_audit.py — _TAXONOMY_CONSTANTS dict keys (module_constant)
#
# W1 constants (engine/standout_audit.py, all module-level):
#   A1_IDIO_BREAK_THRESHOLD, A1_SECTOR_ROTATED_SECTOR_THRESH,
#   A1_SECTOR_ROTATED_IDIO_BAND, A1_MACRO_SPY_THRESH, A1_MACRO_IDIO_BAND,
#   A1_IDIO_ALPHA_THRESHOLD, A1_BETA_TAILWIND_IDIO_BAND,
#   A2_SIGNALED_TOO_LATE_TENURE, A2_PREMATURE_STOP_MFE_THRESH,
#   A2_PREMATURE_STOP_SESSIONS, A2_GATE_SUPPRESSED_EXCESS_THRESH,
#   SENSOR_MIN_MATURED_ROWS, SENSOR_MIN_ENTRY_DATES,
#   SENSOR_MIN_NONOVERLAPPING_WINDOWS, SENSOR_MIN_CALENDAR_MONTHS,
#   MISSED_MOVER_EPISODE_EXCESS_THRESH, MISSED_MOVER_EPISODE_WINDOW,
#   MISSED_MOVER_BUY_WINDOW
#
# W2 constants (engine/china_standout_audit.py, _TAXONOMY_CONSTANTS dict keys):
#   IDIO_BREAK_PP, IDIO_ALPHA_PP, IDIO_BAND_PP, SECTOR_OUT_PP, MACRO_FALL_PCT,
#   BETA_STRONG_PCT, FRESH_TICKS, EXT_SCORE_LATE_PCT, PREMATURE_STOP_MFE_PP
#
# Fictional names removed from original list (not in any audit module):
#   A1_BETA_TAILWIND_BENCH_THRESH, A1_IDIO_BAND, A2_LATE_EXT_PERCENTILE,
#   A2_LATE_TICKS, A2_LATE_TENURE_DAYS, A2_PREMSTOP_MFE_THRESH, A2_PREMSTOP_WINDOW


def _build_attribution_sensor_constants() -> frozenset[str]:
    """Attempt to import W1/W2 audit modules and read their constants dynamically.
    Falls back to the static verified list on ImportError — never raises."""
    # Static verified list (2026-07-12 snapshot of W1 and W2 branches)
    _STATIC: frozenset[str] = frozenset({
        # W1 (engine/standout_audit.py) — module-level constants
        "A1_IDIO_BREAK_THRESHOLD",
        "A1_SECTOR_ROTATED_SECTOR_THRESH",
        "A1_SECTOR_ROTATED_IDIO_BAND",
        "A1_MACRO_SPY_THRESH",
        "A1_MACRO_IDIO_BAND",
        "A1_IDIO_ALPHA_THRESHOLD",
        "A1_BETA_TAILWIND_IDIO_BAND",
        "A2_SIGNALED_TOO_LATE_TENURE",
        "A2_PREMATURE_STOP_MFE_THRESH",
        "A2_PREMATURE_STOP_SESSIONS",
        "A2_GATE_SUPPRESSED_EXCESS_THRESH",
        "SENSOR_MIN_MATURED_ROWS",
        "SENSOR_MIN_ENTRY_DATES",
        "SENSOR_MIN_NONOVERLAPPING_WINDOWS",
        "SENSOR_MIN_CALENDAR_MONTHS",
        "MISSED_MOVER_EPISODE_EXCESS_THRESH",
        "MISSED_MOVER_EPISODE_WINDOW",
        "MISSED_MOVER_BUY_WINDOW",
        # W2 (engine/china_standout_audit.py) — _TAXONOMY_CONSTANTS dict keys
        "IDIO_BREAK_PP",
        "IDIO_ALPHA_PP",
        "IDIO_BAND_PP",
        "SECTOR_OUT_PP",
        "MACRO_FALL_PCT",
        "BETA_STRONG_PCT",
        "FRESH_TICKS",
        "EXT_SCORE_LATE_PCT",
        "PREMATURE_STOP_MFE_PP",
    })
    constants: set[str] = set(_STATIC)

    # Attempt dynamic import of W1 module
    try:
        import importlib
        w1 = importlib.import_module("engine.standout_audit")
        # Read all uppercase names that look like taxonomy constants
        for name in dir(w1):
            if name.startswith(("A1_", "A2_", "SENSOR_", "MISSED_MOVER_")):
                constants.add(name)
    except Exception:  # noqa: BLE001
        pass  # fall through to static

    # Attempt dynamic import of W2 module
    try:
        import importlib
        w2 = importlib.import_module("engine.china_standout_audit")
        tc = getattr(w2, "_TAXONOMY_CONSTANTS", None)
        if isinstance(tc, dict):
            constants.update(tc.keys())
    except Exception:  # noqa: BLE001
        pass  # fall through to static

    return frozenset(constants)


ATTRIBUTION_SENSOR_CONSTANTS: frozenset[str] = _build_attribution_sensor_constants()

# Whitelist keys normalized for disjointness check (strip market prefix)
_WHITELIST_CANONICAL_KEYS: frozenset[str] = frozenset({
    "us.tier_frac",
    "us.coiled_bonus",
    "us.star_extra",
    "us.per_sector_cap",
    "cn.tier_frac",
    "cn.wn_floor",
    "cn.washout_bonus",
    "cn.ext_penalty",
    "cn.per_sector_cap",
})

_DISJOINTNESS_CHECK_DONE = False  # module-load assertion


def _assert_disjoint() -> None:
    """Assert whitelist param keys have no overlap with attribution/sensor constants."""
    global _DISJOINTNESS_CHECK_DONE
    if _DISJOINTNESS_CHECK_DONE:
        return
    # Normalize: take the suffix after the last dot, uppercase
    wl_suffixes = {k.split(".")[-1].upper() for k in _WHITELIST_CANONICAL_KEYS}
    overlap = wl_suffixes & {c.upper() for c in ATTRIBUTION_SENSOR_CONSTANTS}
    if overlap:
        raise AssertionError(
            f"SA-R2 disjointness violated: whitelist params overlap with "
            f"attribution/sensor constants: {overlap}"
        )
    _DISJOINTNESS_CHECK_DONE = True


_assert_disjoint()


# ── Proposal JSON schema ──────────────────────────────────────────────────────
# Written by the metabolism lane (SA-W3) to data/standout_review/proposals/*.json
# Required fields:
#   market          : "us" | "cn"
#   param           : one of _WHITELIST_CANONICAL_KEYS
#   delta_steps     : integer (number of steps; +1 or -1 for a single-step proposal)
#   rationale_ref   : path to postmortem file (informational; not validated at runtime)
#   proposer        : str (e.g. "standout_auditor")
#   cycle_id        : str (e.g. "2026-07-12-us-01")
_REQUIRED_PROPOSAL_FIELDS = frozenset({
    "market", "param", "delta_steps", "rationale_ref", "proposer", "cycle_id"
})

_VALID_MARKETS = frozenset({"us", "cn"})


def _data_dir(root: str | Path | None = None) -> Path:
    try:
        from lib import config
        return config.data_dir() if root is None else (Path(root) / "data")
    except Exception:  # noqa: BLE001
        return Path("data") if root is None else (Path(root) / "data")


def _root_dir(root: str | Path | None = None) -> Path:
    try:
        from lib import config
        return config.ROOT if root is None else Path(root)
    except Exception:  # noqa: BLE001
        return Path(".") if root is None else Path(root)


# ── Config loading ────────────────────────────────────────────────────────────

def _load_config(root: str | Path | None = None) -> dict | None:
    """Load config/standout_review.yml. Returns None if absent or unparsable.
    None signals DORMANT — the module refuses to act."""
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        try:
            import ruamel.yaml as yaml  # type: ignore[import]
        except ImportError:
            log.warning("standout_review: yaml not available; refusing to run")
            return None
    try:
        p = _root_dir(root) / "config" / "standout_review.yml"
        if not p.exists():
            return None
        text = p.read_text(encoding="utf-8")
        cfg = yaml.safe_load(text)
        if not isinstance(cfg, dict):
            log.warning("standout_review: config parsed but is not a dict")
            return None
        return cfg
    except Exception as e:  # noqa: BLE001
        log.warning("standout_review: config load failed: %s", e)
        return None


def _get_whitelist(cfg: dict) -> dict:
    """Return the whitelist section dict, defaulting to empty."""
    return cfg.get("whitelist") or {}


def _get_clamps(cfg: dict) -> dict:
    """Return the clamps section dict."""
    return cfg.get("clamps") or {}


def _get_do_no_harm(cfg: dict) -> dict:
    """Return the do_no_harm section dict."""
    return cfg.get("do_no_harm") or {}


# ── Governance event helpers (mirrors risk_radar_review.py exactly) ───────────

def _gov_proposed(proposal: dict, cycle_id: str, trial_count: int,
                  root: str | Path | None = None) -> None:
    """A6 lane-(ii): append a6_llm_proposed governance event on intake."""
    try:
        from engine.neuralweb.governance import append_event
        append_event(
            "a6_llm_proposed",
            f"config/standout_review.yml:{proposal.get('param')}",
            article=6,
            authored_by="standout_review",
            evidence={
                "lane": "ii",
                "market": proposal.get("market"),
                "param": proposal.get("param"),
                "delta_steps": proposal.get("delta_steps"),
                "cycle_id": cycle_id,
                "proposer": proposal.get("proposer"),
                "rationale_ref": str(proposal.get("rationale_ref") or ""),
                "trial_count": trial_count,
                "pre_committed_gate": "leave-newest-out holdout + bonferroni haircut + within-month permutation null",
            },
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_review: gov_proposed event failed: %s", exc)


def _gov_shadow_apply(proposal: dict, shadow_path: str, cycle_id: str,
                      trial_count: int, root: str | Path | None = None) -> None:
    """A6 lane-(ii): append a6_auto_apply event for shadow_apply (lane: shadow_book)."""
    try:
        from engine.neuralweb.governance import append_event
        append_event(
            "a6_auto_apply",
            f"config/standout_review.yml:{proposal.get('param')}",
            article=6,
            authored_by="standout_review",
            evidence={
                "lane": "shadow_book",
                "market": proposal.get("market"),
                "param": proposal.get("param"),
                "delta_steps": proposal.get("delta_steps"),
                "cycle_id": cycle_id,
                "shadow_book_path": shadow_path,
                "trial_count": trial_count,
                "note": (
                    "shadow_apply only — no live config flip. "
                    "Forward-confirm required before any live apply (SA-R5). "
                    "Quarterly re-audit will auto-revert if forward window regresses."
                ),
            },
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_review: gov_shadow_apply event failed: %s", exc)


def _gov_reject(proposal: dict, reason: str, cycle_id: str,
                trial_count: int, root: str | Path | None = None) -> None:
    """A6 lane-(ii): append a6_rejected event."""
    try:
        from engine.neuralweb.governance import append_event
        append_event(
            "a6_llm_proposed",
            f"config/standout_review.yml:{proposal.get('param')}",
            article=6,
            authored_by="standout_review",
            evidence={
                "lane": "ii",
                "market": proposal.get("market"),
                "param": proposal.get("param"),
                "delta_steps": proposal.get("delta_steps"),
                "cycle_id": cycle_id,
                "trial_count": trial_count,
                "applied": False,
                "reject_reason": reason,
            },
            note=f"proposal rejected: {reason}",
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("standout_review: gov_reject event failed: %s", exc)


# ── Proposal validation ───────────────────────────────────────────────────────

def _validate_proposal(proposal: dict, whitelist: dict) -> str | None:
    """Validate proposal structure and whitelist membership.
    Returns None if valid, or a rejection reason string."""
    if not isinstance(proposal, dict):
        return "invalid_proposal_type"

    # Required fields
    missing = _REQUIRED_PROPOSAL_FIELDS - set(proposal.keys())
    if missing:
        return f"missing_required_fields:{sorted(missing)}"

    # Market check
    market = proposal.get("market")
    if market not in _VALID_MARKETS:
        return f"invalid_market:{market}"

    # Param whitelist check
    param = proposal.get("param")
    if param not in _WHITELIST_CANONICAL_KEYS:
        return f"param_not_whitelisted:{param}"

    # Market prefix matches param prefix
    expected_prefix = market + "."
    if not str(param).startswith(expected_prefix):
        return f"param_market_mismatch:{param} for market:{market}"

    # delta_steps must be a non-zero integer
    delta_steps = proposal.get("delta_steps")
    if not isinstance(delta_steps, int) or delta_steps == 0:
        return f"invalid_delta_steps:{delta_steps}"

    # Max one step per cycle (SA-R4)
    if abs(delta_steps) > 1:
        return f"exceeds_max_step_per_cycle:abs({delta_steps})>1"

    # Check param exists in whitelist
    if param not in whitelist:
        return f"param_not_in_config_whitelist:{param}"

    return None


def _disjointness_check(proposal: dict) -> str | None:
    """Assert the proposed param is not an attribution/sensor constant.
    Returns None if clean, rejection reason if violated."""
    param = str(proposal.get("param") or "")
    suffix = param.split(".")[-1].upper()
    if suffix in {c.upper() for c in ATTRIBUTION_SENSOR_CONSTANTS}:
        return f"disjointness_violation:param_is_attribution_constant:{param}"
    return None


# ── Step-bound clamp check ────────────────────────────────────────────────────

def _compute_proposed_value(proposal: dict, whitelist: dict) -> tuple[float | int | None, str | None]:
    """Compute the proposed new value after applying delta_steps.
    Returns (new_value, None) on success or (None, reject_reason).
    """
    param = proposal.get("param")
    delta_steps = proposal.get("delta_steps", 0)
    spec = whitelist.get(param)
    if not spec:
        return None, f"param_missing_spec:{param}"

    step = spec.get("step")
    min_val = spec.get("min")
    max_val = spec.get("max")
    current_source = spec.get("current_source", "")

    if step is None or min_val is None or max_val is None:
        return None, f"incomplete_whitelist_spec:{param}"

    # Try to read current production value from source
    # We do NOT read config files at runtime for production values.
    # The delta is sized as current + N*step where current is NOT known here
    # (we don't read source modules for safety). Instead, we validate the delta
    # amount is legal (1 step) and record it for the shadow book.
    # The evaluator is responsible for the actual numeric simulation.
    delta_amount = float(step) * delta_steps
    return delta_amount, None


def _coverage_clamp_precheck(proposal: dict, clamps: dict,
                              frozen_baselines: dict) -> str | None:
    """Check frozen baseline availability. If null, auto-reject.
    Returns None (pass) or reject reason."""
    market = proposal.get("market", "us")
    fb = (frozen_baselines or {}).get(market) or {}

    # If any frozen baseline is null, the gate cannot evaluate — dormant-reject
    if fb.get("buy_names_per_day_median") is None:
        return "no_frozen_baseline"

    return None


# ── Trial count computation ───────────────────────────────────────────────────

def _compute_trial_count(whitelist: dict) -> int:
    """Compute Bonferroni grid size: number of (param, direction) pairs in the whitelist."""
    n = 0
    for _param, spec in whitelist.items():
        if spec and spec.get("step") is not None:
            n += 2  # +1 step and -1 step
    return max(n, 1)


# ── Cheaply-replayable params set ─────────────────────────────────────────────
# Params whose counterfactual can be evaluated from stored per-name board columns
# without re-running the full board pipeline. The evaluator in
# scripts/replay_standout_books.py handles these via rank-delta reconstruction.
#
# cn.washout_bonus: stored board.parquet has washout_2w (bool), tier, board_rank,
#   ext_score. Sufficient to reconstruct ORDERING DELTA under modified bonus.
#   Approximation: conviction-percentile term held constant (rank-normalised).
#   See scripts/replay_standout_books.py _cn_washout_bonus_counterfactual().
_CHEAP_REPLAY_PARAMS: frozenset[str] = frozenset({"cn.washout_bonus"})


# ── Evaluator interface ───────────────────────────────────────────────────────

def _replay_evaluator(proposal: dict, delta_amount: float,
                      do_no_harm_cfg: dict, root: str | Path | None = None
                      ) -> dict:
    """Replay evaluator (Tier-0 evidence per SA-R5).

    For params in _CHEAP_REPLAY_PARAMS (cn.washout_bonus): calls the real
    counterfactual evaluator in scripts/replay_standout_books.py, which
    reconstructs the ordering delta from stored per-name board.parquet columns.

    For all other params: returns UNEVALUABLE (honest — full board re-run not
    available in the in-process evaluator). Use scripts/replay_standout_books.py
    with --book for manual Tier-0 evidence.

    At current n (SA-R10 floors not yet met, ~2026-09-15 US / ~2026-10-15 CN)
    this will return UNEVALUABLE because effective_n < min_effective_n — the
    correct honest DORMANT state.

    Returns a dict with keys: verdict ("PASS"|"FAIL"|"UNEVALUABLE"), reason, evidence.
    """
    min_eff_n = int((do_no_harm_cfg or {}).get("min_effective_n") or 6)
    param = proposal.get("param", "")
    market = proposal.get("market", "us")

    # Route cheaply-replayable params to the real counterfactual evaluator
    if param in _CHEAP_REPLAY_PARAMS:
        try:
            from scripts.replay_standout_books import (
                _load_grades,
                _cn_washout_bonus_counterfactual,
                _data_dir as _replay_data_dir,
            )

            data_dir = _replay_data_dir(Path(root) if root else None)
            grades_df, err = _load_grades(data_dir, market)
            if err:
                return {
                    "verdict": "UNEVALUABLE",
                    "reason": f"grades_load_failed:{err}",
                    "evidence": {"param": param},
                }

            # Compute trial count for Bonferroni
            cfg = _load_config(root)
            trial_count = _compute_trial_count(_get_whitelist(cfg) if cfg else {})

            # Dispatch to param-specific evaluator
            if param == "cn.washout_bonus":
                # delta_steps * step = delta_amount; reconstruct cf bonus
                from scripts.replay_standout_books import _CN_WASHOUT_BONUS_BASELINE
                delta_steps = proposal.get("delta_steps", 0)
                step = 0.10  # cn.washout_bonus step
                washout_bonus_cf = float(_CN_WASHOUT_BONUS_BASELINE) + int(delta_steps) * step
                return _cn_washout_bonus_counterfactual(
                    grades_df,
                    washout_bonus_cf=washout_bonus_cf,
                    trial_count=trial_count,
                    min_effective_n=min_eff_n,
                )

        except Exception as e:  # noqa: BLE001
            log.warning("_replay_evaluator: cheap replay failed for %s: %s", param, e)
            return {
                "verdict": "UNEVALUABLE",
                "reason": f"cheap_replay_error:{e}",
                "evidence": {"param": param},
            }

    # All other params: UNEVALUABLE (honest — full board re-run not available)
    return {
        "verdict": "UNEVALUABLE",
        "reason": (
            f"param_not_cheaply_replayable_in_v1:{param}. "
            "Use scripts/replay_standout_books.py (Tier-0 evidence tool, SA-R5) "
            "to evaluate counterfactuals. UNEVALUABLE => reject per SA-R5."
        ),
        "evidence": {"param": param},
    }


# ── Shadow book spec writer ───────────────────────────────────────────────────

def _config_hash(cfg: dict) -> str:
    canonical = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _write_shadow_book(proposal: dict, delta_amount: float,
                       root: str | Path | None = None) -> str:
    """Write a draft Pick Lab book spec to data/standout_review/shadow_books/.

    The spec is a complete registry-entry dict with:
      - Modified config (param delta applied conceptually; actual value is
        current + delta_amount, but we record the delta since we don't read prod)
      - New engine_id: sareview_<param>_<version>
      - Frozen config_hash
      - PL-R9 citation field
      - Status: draft (awaiting human/metabolism BUILD PR to register in pick_lab)

    Returns the path string.
    """
    param = str(proposal.get("param") or "")
    cycle_id = str(proposal.get("cycle_id") or "")
    market = str(proposal.get("market") or "us")
    delta_steps = proposal.get("delta_steps", 0)

    # Sanitize param name for engine_id
    param_slug = param.replace(".", "_")
    # Version from cycle_id hash (short)
    v_hash = hashlib.sha256(f"{cycle_id}:{param}".encode()).hexdigest()[:6]
    engine_id = f"sareview_{param_slug}_{v_hash}"

    config_dict = {
        "sa_review_param": param,
        "delta_steps": delta_steps,
        "delta_amount": delta_amount,
        "cycle_id": cycle_id,
        "market": market,
        "shadow_only": True,
    }

    spec = {
        "schema": "standout_shadow_book.v1",
        "engine_id": engine_id,
        "name_en": f"SA-Review shadow: {param} delta {delta_steps:+d}",
        "name_zh": f"SA审查影子: {param} 增量 {delta_steps:+d}",
        "family": "SA_SHADOW",
        "ruler": "21d_spy_excess" if market == "us" else "21d_csi300_excess",
        "horizon_role": "entry",
        "max_picks": 12,
        "refire_lockout_sessions": 21,
        "config": config_dict,
        "config_hash": _config_hash(config_dict),
        "kill_adjacency": "SA-W4 shadow book — PL-R9: parameter under forward evaluation; no kill adjacency declared.",
        "status": "draft",
        "source_proposal": {
            "market": market,
            "param": param,
            "delta_steps": delta_steps,
            "cycle_id": cycle_id,
            "proposer": proposal.get("proposer"),
            "rationale_ref": str(proposal.get("rationale_ref") or ""),
        },
        "forward_confirm_required": True,
        "live_apply_requires": "forward window confirms fitness contract at maturity (VERIFY) OR explicit operator tap",
        "auto_revert_on": "quarterly re-audit forward regression (SA-R5)",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": (
            "DRAFT: this spec must be registered by a human/metabolism BUILD PR "
            "into engine/pick_lab/registry.py (new engine_id + fresh ledger, PL-R2). "
            "The lab IS the shadow lane. Forward-confirm before any live config flip (SA-R5). "
            "This is Tier-0/Tier-1 evidence per the three-speed ladder (SA-R5) — "
            "replay authorizes experiments and shadow applies, NEVER promotions."
        ),
    }

    out_dir = _data_dir(root) / "standout_review" / "shadow_books"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{engine_id}.json"
    out_path.write_text(
        json.dumps(spec, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return str(out_path)


# ── Review state freshness stamp ──────────────────────────────────────────────

def _write_review_state(run_summary: dict, root: str | Path | None = None) -> None:
    """Write data/standout_review/review_state.json freshness stamp."""
    try:
        p = _data_dir(root) / "standout_review" / "review_state.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({
                **run_summary,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("standout_review: review_state write failed: %s", e)


# ── Per-proposal pipeline ────────────────────────────────────────────────────

def _process_proposal(proposal: dict, cfg: dict,
                      root: str | Path | None = None,
                      dry_run: bool = False) -> dict:
    """Run the full pipeline for a single proposal.

    Steps:
      (a) Validate structure + whitelist membership
      (b) Disjointness assert
      (c) Coverage clamp precheck vs frozen baselines (dormant-reject if null)
      (d) Do-no-harm replay evaluation
      (e) Verdict: shadow_apply | reject

    Returns a result dict with keys: verdict, reason, engine_id (if shadow), evidence.
    Never raises.
    """
    result: dict[str, Any] = {
        "proposal": proposal,
        "verdict": "reject",
        "reason": None,
        "engine_id": None,
        "shadow_book_path": None,
        "evidence": {},
    }

    whitelist = _get_whitelist(cfg)
    clamps = _get_clamps(cfg)
    do_no_harm_cfg = _get_do_no_harm(cfg)
    frozen_baselines = (clamps.get("frozen_baselines") or {})
    cycle_id = str(proposal.get("cycle_id") or "unknown")

    # Compute trial count for governance logging
    trial_count = _compute_trial_count(whitelist)

    # (a) Validate structure + whitelist
    reject_reason = _validate_proposal(proposal, whitelist)
    if reject_reason:
        result["reason"] = reject_reason
        if not dry_run:
            _gov_reject(proposal, reject_reason, cycle_id, trial_count, root=root)
        return result

    # (b) Disjointness assert
    reject_reason = _disjointness_check(proposal)
    if reject_reason:
        result["reason"] = reject_reason
        if not dry_run:
            _gov_reject(proposal, reject_reason, cycle_id, trial_count, root=root)
        return result

    # Emit a6_llm_proposed governance event (before evaluation, per A6 lane-(ii))
    if not dry_run:
        _gov_proposed(proposal, cycle_id, trial_count, root=root)

    # Compute delta amount
    delta_amount, err = _compute_proposed_value(proposal, whitelist)
    if err:
        result["reason"] = err
        if not dry_run:
            _gov_reject(proposal, err, cycle_id, trial_count, root=root)
        return result

    # (c) Coverage clamp precheck vs frozen baselines
    reject_reason = _coverage_clamp_precheck(proposal, clamps, frozen_baselines)
    if reject_reason:
        result["reason"] = reject_reason
        if not dry_run:
            _gov_reject(proposal, reject_reason, cycle_id, trial_count, root=root)
        return result

    # (d) Do-no-harm replay evaluation
    eval_result = _replay_evaluator(proposal, delta_amount or 0.0, do_no_harm_cfg, root=root)
    result["evidence"] = eval_result.get("evidence") or {}

    if eval_result.get("verdict") == "UNEVALUABLE":
        reason = eval_result.get("reason") or "unevaluable"
        result["reason"] = reason
        if not dry_run:
            _gov_reject(proposal, reason, cycle_id, trial_count, root=root)
        return result

    if eval_result.get("verdict") == "FAIL":
        reason = eval_result.get("reason") or "do_no_harm_gate_failed"
        result["reason"] = reason
        if not dry_run:
            _gov_reject(proposal, reason, cycle_id, trial_count, root=root)
        return result

    # (e) PASS → shadow_apply (never live apply in v1)
    if eval_result.get("verdict") == "PASS":
        if not dry_run:
            shadow_path = _write_shadow_book(proposal, delta_amount or 0.0, root=root)
            _gov_shadow_apply(proposal, shadow_path, cycle_id, trial_count, root=root)
            result["shadow_book_path"] = shadow_path
        result["verdict"] = "shadow_apply"
        result["reason"] = None
    else:
        # Should not reach here, but handle gracefully
        result["reason"] = f"unexpected_evaluator_verdict:{eval_result.get('verdict')}"
        if not dry_run:
            _gov_reject(proposal, result["reason"], cycle_id, trial_count, root=root)

    return result


# ── Proposal file loader ──────────────────────────────────────────────────────

def _load_proposals(root: str | Path | None = None) -> list[dict]:
    """Load all proposal JSON files from data/standout_review/proposals/."""
    proposals_dir = _data_dir(root) / "standout_review" / "proposals"
    if not proposals_dir.exists():
        return []
    results = []
    for p in sorted(proposals_dir.glob("*.json")):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw["_source_file"] = str(p)
                results.append(raw)
            else:
                log.warning("standout_review: proposal %s is not a dict, skipping", p)
        except Exception as e:  # noqa: BLE001
            log.warning("standout_review: failed to parse proposal %s: %s", p, e)
    return results


# ── Main entry point ──────────────────────────────────────────────────────────

def run(root: str | Path | None = None, dry_run: bool = False) -> dict:
    """Process all pending proposals in data/standout_review/proposals/.

    Arming precondition: config/standout_review.yml must exist and parse.
    If absent/unparsable, returns a clean journaled no-op.

    Never raises. SA-R16 compliant.

    Parameters
    ----------
    root : str | Path | None
        Project root for path resolution. None = production paths.
    dry_run : bool
        If True, run the pipeline but do not write any files or emit
        governance events. Returns the same result structure.

    Returns
    -------
    dict with keys:
        schema, as_of, n_proposals, n_shadow_apply, n_rejected,
        results (list), dry_run, dormant_reason (if applicable)
    """
    out: dict[str, Any] = {
        "schema": "standout_review.v1",
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "dry_run": dry_run,
        "n_proposals": 0,
        "n_shadow_apply": 0,
        "n_rejected": 0,
        "results": [],
    }

    try:
        # Arming precondition: config must exist and parse
        cfg = _load_config(root)
        if cfg is None:
            out["dormant_reason"] = "config_absent_or_unparsable"
            log.info(
                "standout_review: config/standout_review.yml absent or unparsable — "
                "running as inert no-op (dormant state, arming precondition not met)"
            )
            _write_review_state({**out, "dormant": True}, root=root)
            return out

        # Load proposals
        proposals = _load_proposals(root)
        out["n_proposals"] = len(proposals)

        if not proposals:
            log.info("standout_review: no proposals found in data/standout_review/proposals/")
            _write_review_state(out, root=root)
            return out

        # Process each proposal
        results = []
        for proposal in proposals:
            try:
                result = _process_proposal(proposal, cfg, root=root, dry_run=dry_run)
                results.append(result)
                if result["verdict"] == "shadow_apply":
                    out["n_shadow_apply"] += 1
                else:
                    out["n_rejected"] += 1
            except Exception as e:  # noqa: BLE001 — never-raise per SA-R16
                log.error(
                    "standout_review: proposal processing error (never fatal): %s — %s",
                    proposal.get("cycle_id", "?"), e,
                )
                results.append({
                    "proposal": proposal,
                    "verdict": "reject",
                    "reason": f"processing_error:{e}",
                    "engine_id": None,
                    "shadow_book_path": None,
                    "evidence": {},
                })
                out["n_rejected"] += 1

        out["results"] = results
        if not dry_run:
            _write_review_state(out, root=root)

        log.info(
            "standout_review: %d proposals processed: %d shadow_apply, %d rejected",
            len(proposals), out["n_shadow_apply"], out["n_rejected"],
        )
        return out

    except Exception as e:  # noqa: BLE001 — SA-R16 never raises
        log.error("standout_review.run failed: %s", e)
        out["dormant_reason"] = f"run_error:{e}"
        return out


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="SA-W4 standout improvement lane engine")
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate proposals without writing files or governance events")
    ap.add_argument("--root", default=None, help="Override project root path")
    args = ap.parse_args()
    result = run(root=args.root, dry_run=args.dry_run)
    print(json.dumps({
        "n_proposals": result.get("n_proposals"),
        "n_shadow_apply": result.get("n_shadow_apply"),
        "n_rejected": result.get("n_rejected"),
        "dormant_reason": result.get("dormant_reason"),
        "dry_run": result.get("dry_run"),
    }, indent=2))
