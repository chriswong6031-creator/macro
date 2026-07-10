"""engine.metabolism.revamp_adjudicator — Revamp-vs-Fix adjudicator (V2-C Unit 6).

WHAT IT DOES
------------
For a demoted / failing lobe, classifies the FAILURE TOPOLOGY from its lifecycle
breach journal + trajectory + regime context, then RECOMMENDS one of:

    logic_error          → in_place_fix        (a code/logic fault in an organ that
                                                 was otherwise working — fix the code)
    stale_construct      → revamp_new_charter  (the construction is dead as the world
                                                 moved on — reset to `proposed` and
                                                 re-charter)
    domain_shift         → hold_operator       (a dead feed or a regime change — the
                                                 measurement lens can't blame the lobe;
                                                 route to operator, R-V2-10)
    insufficient_evidence→ accruing            (too few journal rows — honest null)

WHY IT IS SAFE
--------------
  * DETERMINISTIC, NO LLM.  Pure rules over the breach journal (R-V2-9: the loop
    investigates, it never declares).
  * INERT.  The output is a RECOMMENDATION artifact only.  It does NOT call
    lifecycle.transition, never edits a charter, never auto-retires.  The actual
    revamp (probation/demoted → proposed, both T1 operator-initiated edges that
    already exist in lifecycle.py) or in-place fix runs through the normal
    gauntlet + operator (R-V2-3).
  * REGIME-AWARE, KILL-ON-DOUBT.  Health-excluded misses (missing/degraded/stale)
    and regime pauses route to `hold_operator`, never to a demotion — a dead feed
    is not a bad lobe (R-V2-3 demotion safety; R-V2-10 ambiguous-kill posture).
  * NEVER-RAISE.  Every public function returns safe defaults on any error.

Artifacts:
  data/metabolism/revamp_adjudications/<cycle>_<lobe>.json

Schema: metabolism.revamp_adjudication.v1
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.revamp_adjudication.v1"

LIFECYCLE_DIR = ("data", "metabolism", "lifecycle")          # per-lobe breach journals
REVAMP_DIR = ("data", "metabolism", "revamp_adjudications")   # our output

# Failure topologies
TOPOLOGY_LOGIC_ERROR = "logic_error"
TOPOLOGY_STALE_CONSTRUCT = "stale_construct"
TOPOLOGY_DOMAIN_SHIFT = "domain_shift"
TOPOLOGY_INSUFFICIENT = "insufficient_evidence"

# Recommendations
REC_IN_PLACE_FIX = "in_place_fix"
REC_REVAMP = "revamp_new_charter"
REC_HOLD_OPERATOR = "hold_operator"
REC_ACCRUING = "accruing"

# Minimum journal rows before a topology may be declared (honest-null below this).
MIN_ROWS_FOR_CLASSIFICATION = 3

# Health statuses that must NOT be blamed on the lobe (mirror verify._HEALTH_EXCLUDED_STATUSES).
_HEALTH_EXCLUDED_STATUSES = frozenset({"missing", "degraded", "stale", "unknown"})

# Lifecycle revamp edges that already exist (lifecycle.py) — noted, never executed here.
_REVAMP_EDGES = {
    "probation": ("probation", "proposed"),
    "demoted": ("demoted", "proposed"),
    "active": ("active", "probation"),  # a still-active failing lobe demotes first
}

_AUTHORITY_BLOCK = {
    "is_context_only": True,
    "display_only": True,
    "not_a_signal": True,
    "note": (
        "Revamp-vs-fix RECOMMENDATION. INERT: does not execute any transition, "
        "never edits a charter, never auto-retires. The actual revamp "
        "(probation/demoted->proposed) or in-place fix goes through the normal "
        "gauntlet + operator (R-V2-3/R-V2-10)."
    ),
}


# ── Root + IO helpers ─────────────────────────────────────────────────────────

def _resolve_root(root: str | Path | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_journal_rows(lobe_id: str, root: Path) -> list[dict]:
    """Read a lobe's lifecycle breach journal.  Returns [] on any error.

    Mirrors verify._read_journal_rows (same file, same schema).
    """
    try:
        p = root.joinpath(*LIFECYCLE_DIR) / f"{lobe_id}.jsonl"
        if not p.exists():
            return []
        rows: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            # Keep only object rows — a non-dict line must not crash the classifier
            # mid-loop and collapse a real logic failure into a false "insufficient".
            if isinstance(obj, dict):
                rows.append(obj)
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("revamp_adjudicator._read_journal_rows(%s): %s", lobe_id, exc)
        return []


# ── Classification (deterministic) ────────────────────────────────────────────

def classify_failure_topology(
    rows: list[dict],
    *,
    regime_paused: bool = False,
    trajectory_label: str | None = None,
    health_status: str | None = None,
) -> dict[str, Any]:
    """Classify a lobe's failure topology from its breach journal + context.

    The discriminator between logic_error and stale_construct is the TRAJECTORY:
    a sustained `degrading` slope means the construction is decaying as the world
    moves on (stale_construct → revamp); genuine logic breaches WITHOUT a
    sustained decline are a code fault in an otherwise-working organ
    (logic_error → in_place_fix).  When the trajectory is unknown, we default to
    the cheaper, less destructive in_place_fix.

    Returns dict: {topology, recommendation, confidence, evidence, rationale}.
    NEVER raises.
    """
    evidence: dict[str, Any] = {
        "n_rows": 0,
        "counted_logic_breaches": 0,
        "health_miss_rows": 0,
        "consecutive_counted": 0,
        "any_all_inputs_absent": False,
        "regime_paused": bool(regime_paused),
        "trajectory_label": trajectory_label,
        "health_status": health_status,
    }
    try:
        rows = rows or []
        evidence["n_rows"] = len(rows)

        counted = 0
        health_miss = 0
        any_absent = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            is_counted = row.get("counted") is True
            if is_counted:
                counted += 1
            if row.get("all_inputs_absent") is True:
                any_absent = True
            # A row is a health miss if it is typed as one OR carries an excluded
            # health_status — but ONLY when it is NOT a counted logic breach. A
            # counted logic breach is a genuine fault and must never be laundered
            # into a "dead feed" that suppresses the classification (verify.py
            # guarantees counted=True ⟹ health not excluded; this guards a
            # malformed journal too).
            if is_counted:
                continue
            hs = row.get("health_status")
            if row.get("breach_type") == "health_miss" or hs in _HEALTH_EXCLUDED_STATUSES:
                health_miss += 1

        # consecutive counted breaches at the tail (mirror verify._consecutive_counted_breaches)
        consecutive = 0
        for row in reversed(rows):
            if not isinstance(row, dict):
                continue
            if row.get("breach_type") == "pass":
                break
            if row.get("counted") is True:
                consecutive += 1

        evidence["counted_logic_breaches"] = counted
        evidence["health_miss_rows"] = health_miss
        evidence["consecutive_counted"] = consecutive
        evidence["any_all_inputs_absent"] = any_absent

        # 1) Honest null — too little evidence to declare a topology.
        if len(rows) < MIN_ROWS_FOR_CLASSIFICATION:
            return {
                "topology": TOPOLOGY_INSUFFICIENT,
                "recommendation": REC_ACCRUING,
                "confidence": "none",
                "evidence": evidence,
                "rationale": (
                    f"Only {len(rows)} journal row(s) (< {MIN_ROWS_FOR_CLASSIFICATION}); "
                    f"insufficient evidence to classify failure topology. Accruing."
                ),
            }

        # 2) Domain shift — a dead feed or a regime the measurement lens can't rule
        #    out. NEVER blame the lobe; route to operator (R-V2-3/R-V2-10).
        health_dominant = health_miss > 0 and health_miss >= counted
        if regime_paused or health_dominant or (any_absent and counted == 0):
            reasons = []
            if regime_paused:
                reasons.append("regime-aware pause active")
            if health_dominant:
                reasons.append(
                    f"health-excluded misses dominate ({health_miss} >= {counted} counted)"
                )
            if any_absent and counted == 0:
                reasons.append("all-inputs-absent with no counted logic breach")
            return {
                "topology": TOPOLOGY_DOMAIN_SHIFT,
                "recommendation": REC_HOLD_OPERATOR,
                "confidence": "high" if regime_paused else "medium",
                "evidence": evidence,
                "rationale": (
                    "Failure looks like a domain shift / dead feed, not a bad lobe: "
                    + "; ".join(reasons)
                    + ". Measurement lens cannot rule out regime; route to operator "
                    "(R-V2-10). Auto-revert HELD."
                ),
            }

        # 3) Genuine counted logic failures present.
        if counted >= 1:
            if trajectory_label == "degrading":
                return {
                    "topology": TOPOLOGY_STALE_CONSTRUCT,
                    "recommendation": REC_REVAMP,
                    "confidence": "high",
                    "evidence": evidence,
                    "rationale": (
                        f"{counted} counted logic breach(es) alongside a sustained "
                        f"'degrading' trajectory: the construction is decaying as the "
                        f"world moved on. Recommend a full revamp (reset to 'proposed' "
                        f"and re-charter)."
                    ),
                }
            return {
                "topology": TOPOLOGY_LOGIC_ERROR,
                "recommendation": REC_IN_PLACE_FIX,
                "confidence": "high" if trajectory_label else "medium",
                "evidence": evidence,
                "rationale": (
                    f"{counted} counted logic breach(es) without a sustained decline "
                    f"(trajectory={trajectory_label!r}): a code/logic fault in an "
                    f"otherwise-working organ. Recommend an in-place fix."
                ),
            }

        # 4) No counted logic failures and no clear domain-shift signal → ambiguous.
        return {
            "topology": TOPOLOGY_DOMAIN_SHIFT,
            "recommendation": REC_HOLD_OPERATOR,
            "confidence": "low",
            "evidence": evidence,
            "rationale": (
                "No counted logic breaches and no decisive signal; ambiguous. "
                "Route to operator rather than act (kill-on-doubt, R-V2-10)."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("revamp_adjudicator.classify_failure_topology: %s", exc)
        return {
            "topology": TOPOLOGY_INSUFFICIENT,
            "recommendation": REC_ACCRUING,
            "confidence": "none",
            "evidence": evidence,
            "rationale": f"classification error: {exc}",
        }


def _recommended_next(recommendation: str, current_lifecycle_state: str) -> dict[str, Any]:
    """Describe the eligible next step for this recommendation (NEVER executed here)."""
    if recommendation == REC_REVAMP:
        edge = _REVAMP_EDGES.get(current_lifecycle_state)
        return {
            "path": "lifecycle_revamp",
            "eligible_edge": list(edge) if edge else None,
            "note": (
                "Operator-initiated revamp edge in lifecycle.py "
                "(reset to 'proposed'); runs through the gauntlet. Not executed here."
            ),
        }
    if recommendation == REC_IN_PLACE_FIX:
        return {
            "path": "propose_engine_fix",
            "eligible_edge": None,
            "note": (
                "Charter is retained; the code fix enters the normal PROPOSE->BUILD "
                "gauntlet as an engine change. Not executed here."
            ),
        }
    if recommendation == REC_HOLD_OPERATOR:
        return {
            "path": "operator_tap",
            "eligible_edge": None,
            "note": "Ambiguous / regime-suspect. Held for operator review (R-V2-10).",
        }
    return {"path": "none", "eligible_edge": None, "note": "Accruing; no action."}


# ── Public API ────────────────────────────────────────────────────────────────

def adjudicate_lobe(
    lobe_id: str,
    current_lifecycle_state: str,
    *,
    cycle_id: str | None = None,
    regime_paused: bool = False,
    trajectory_label: str | None = None,
    health_status: str | None = None,
    root: str | Path | None = None,
    emit: bool = True,
) -> dict[str, Any]:
    """Adjudicate revamp-vs-fix for a demoted/failing lobe.

    Parameters
    ----------
    lobe_id : str
    current_lifecycle_state : str
        The lobe's current lifecycle_state (active|probation|demoted|...).
    cycle_id : str | None
    regime_paused : bool
        True if the lobe is in a regime-aware pause (routes to hold_operator).
    trajectory_label : str | None
        organism_state trajectory label (compounding|stagnating|degrading|accruing).
        The discriminator between logic_error and stale_construct.
    health_status : str | None
        The health.py status (fresh/stale/missing/degraded/unknown).
    root : str | Path | None
    emit : bool
        If True (default), write the recommendation artifact + insight-bus row.
        If False, compute the recommendation with ZERO I/O (dry-run).

    Returns
    -------
    dict (schema metabolism.revamp_adjudication.v1).  NEVER raises.
    """
    ts = _now_utc()
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "ts": ts,
        "cycle_id": cycle_id,
        "lobe_id": lobe_id,
        "current_lifecycle_state": current_lifecycle_state,
        "topology": TOPOLOGY_INSUFFICIENT,
        "recommendation": REC_ACCRUING,
        "confidence": "none",
        "evidence": {},
        "recommended_next": {},
        "rationale": "",
        "generated_by": "metabolism_revamp_adjudicator",
        "authority": dict(_AUTHORITY_BLOCK),
    }
    try:
        r = _resolve_root(root)
        rows = _read_journal_rows(lobe_id, r)
        classification = classify_failure_topology(
            rows,
            regime_paused=regime_paused,
            trajectory_label=trajectory_label,
            health_status=health_status,
        )
        result["topology"] = classification["topology"]
        result["recommendation"] = classification["recommendation"]
        result["confidence"] = classification["confidence"]
        result["evidence"] = classification["evidence"]
        result["rationale"] = classification["rationale"]
        result["recommended_next"] = _recommended_next(
            classification["recommendation"], current_lifecycle_state
        )

        if emit:
            _write_recommendation(result, r)
            _emit_insight(result, r)

    except Exception as exc:  # noqa: BLE001
        log.warning("revamp_adjudicator.adjudicate_lobe(%s): %s", lobe_id, exc)
        result["error"] = str(exc)

    return result


def _recommendation_path(lobe_id: str, cycle_id: str | None, root: Path) -> Path:
    slug = str(lobe_id).replace("/", "_")
    cyc = str(cycle_id or "nocycle").replace("/", "_")
    return root.joinpath(*REVAMP_DIR) / f"{cyc}_{slug}.json"


def _write_recommendation(result: dict, root: Path) -> bool:
    try:
        path = _recommendation_path(result.get("lobe_id"), result.get("cycle_id"), root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("revamp_adjudicator._write_recommendation: %s", exc)
        return False


def _emit_insight(result: dict, root: Path) -> bool:
    try:
        from engine.metabolism.insight_bus import append_row, build_row  # noqa: PLC0415
        lobe_id = result.get("lobe_id")
        row = build_row(
            emitter="metabolism_revamp_adjudicator",
            kind="revamp_recommendation",
            severity="low" if result.get("recommendation") == REC_ACCRUING else "medium",
            entities=[str(lobe_id)],
            summary=(
                f"{lobe_id}: topology={result.get('topology')} -> "
                f"recommend {result.get('recommendation')} "
                f"(confidence={result.get('confidence')})."
            ),
            evidence_ref=str(_recommendation_path(lobe_id, result.get("cycle_id"), root)),
            cycle_id=result.get("cycle_id"),
        )
        return append_row(row, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("revamp_adjudicator._emit_insight: %s", exc)
        return False
