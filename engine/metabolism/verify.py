"""engine.metabolism.verify — Realized-delta grader for VERIFY stage (A6).

After a proposal's check_by date arrives, re-grade the realized fitness delta
vs the registered contract and apply the regime-aware measurement-lens triage
protocol (R-AUT-11).

Design (reusing existing organs, never reinventing):
  - Contract re-grading reuses engine.qledger_falsifier.evaluate_check()
    to evaluate the registered fitness contract's falsifier spec.
  - Regime-aware triage mirrors memory `measurement-lens-reassessment-protocol`:
      mechanism-false (clean overfit) → emit auto-revert plan artifact
      regime-change / estimator-broken (ambiguous) → operator-tap governance row, revert HELD
  - Output: data/metabolism/verify/<cycle_id>.json

Output schema: metabolism.verify.v1
  {
    "schema": "metabolism.verify.v1",
    "cycle_id": str,
    "proposal_id": str | null,
    "check_by": str (ISO date),
    "contract": dict,           # the registered fitness contract
    "realized": {               # what actually happened
      "outcome": str,           # "CONFIRMED" | "FALSIFIER_TRIPPED" | "UNVERIFIABLE"
      "detail": str,
      "delta_vs_contract": str | null,
    },
    "triage": {
      "classification": str,    # "confirmed" | "overfit" | "regime_change" | "estimator_broken" | "unverifiable"
      "action": str,            # "keep" | "revert_plan" | "operator_tap"
      "revert_plan": dict | null,  # only when action=="revert_plan"
      "operator_tap_reason": str | null,  # only when action=="operator_tap"
    },
    "authority": { is_context_only: true, ... },
    "ts": ISO str,
  }

NEVER-RAISE CONTRACT: all functions return safe defaults on any error.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.verify.v1"
OUTPUT_PATH = ("data", "metabolism", "verify")

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "shadow",
    "forbidden_uses": [
        "ranking", "sizing", "alert_escalation", "board_ordering",
        "mastermind_arming", "scored_path", "auto_revert_without_operator",
    ],
}

# Outcome constants (from qledger_falsifier)
_CONFIRMED = "CONFIRMED"
_TRIPPED = "FALSIFIER_TRIPPED"
_UNVERIFIABLE = "UNVERIFIABLE"


# ── Measurement-lens triage ────────────────────────────────────────────────────

def _measurement_lens_triage(
    outcome: str,
    contract: dict,
    context: dict | None = None,
) -> dict[str, Any]:
    """Apply the regime-aware measurement-lens reassessment protocol (R-AUT-11).

    The protocol separates: mechanism-false vs regime-change vs estimator-broken.

    Parameters
    ----------
    outcome : str — "CONFIRMED" | "FALSIFIER_TRIPPED" | "UNVERIFIABLE"
    contract : dict — the registered fitness contract
    context  : dict | None — optional context (regime, market conditions, etc.)

    Returns
    -------
    dict with keys: classification, action, revert_plan, operator_tap_reason
    """
    if outcome == _CONFIRMED:
        return {
            "classification": "confirmed",
            "action": "keep",
            "revert_plan": None,
            "operator_tap_reason": None,
            "note": "Realized delta confirms the registered contract. Organ retained.",
        }

    if outcome == _UNVERIFIABLE:
        return {
            "classification": "unverifiable",
            "action": "operator_tap",
            "revert_plan": None,
            "operator_tap_reason": (
                "Outcome unverifiable: missing data, soft check, or spec unparseable. "
                "Operator should review whether the check_by spec can be revised."
            ),
            "note": "UNVERIFIABLE outcome routes to operator tap per R-AUT-11.",
        }

    # Outcome is FALSIFIER_TRIPPED (miss).
    # Apply measurement-lens triage to separate mechanism-false from regime/estimator.
    ctx = context or {}
    regime_flag = ctx.get("regime_change_suspected", False)
    estimator_flag = ctx.get("estimator_broken_suspected", False)

    if regime_flag or estimator_flag:
        # Ambiguous: possible regime change or estimator issue — operator tap
        reason_parts = []
        if regime_flag:
            reason_parts.append("regime change suspected")
        if estimator_flag:
            reason_parts.append("estimator may be broken on current data")
        reason = "; ".join(reason_parts)
        return {
            "classification": "regime_change" if regime_flag else "estimator_broken",
            "action": "operator_tap",
            "revert_plan": None,
            "operator_tap_reason": (
                f"Missed registered band, but {reason}. "
                f"Per R-AUT-11, ambiguous misses route to operator review; "
                f"auto-revert HELD until operator confirms overfit vs regime."
            ),
            "note": (
                "R-AUT-11: 'A backtest FAIL assumes stationarity; an honest generalizing organ "
                "can miss its band in a new regime and must not be auto-killed.'"
            ),
        }

    # Clean overfit: emit auto-revert plan + DO_NOT_REBUILD row
    proposal_id = contract.get("proposal_id") or contract.get("dedup_hash") or "unknown"
    revert_plan = {
        "action": "git_revert",
        "target": contract.get("branch") or f"metabolism/{proposal_id}",
        "proposal_id": proposal_id,
        "do_not_rebuild_row": {
            "title": contract.get("title", ""),
            "rationale": (
                f"Fitness contract missed: {contract.get('sensor')} "
                f"expected {contract.get('expected_sign')} in band {contract.get('band')!r}. "
                f"Realized outcome: FALSIFIER_TRIPPED. Clean overfit per R-AUT-11."
            ),
            "appended_by": "metabolism_verify",
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "note": (
            "This is a PLAN artifact only. Execution of the git revert is gated on "
            "the operator arming the loop AND this cycle's governance row being a T0 grant. "
            "The actual git-revert execution does not happen in this PR."
        ),
    }

    return {
        "classification": "overfit",
        "action": "revert_plan",
        "revert_plan": revert_plan,
        "operator_tap_reason": None,
        "note": (
            "Clean overfit: registered band missed with no regime or estimator flags. "
            "Auto-revert PLAN emitted (execution gated on operator arming)."
        ),
    }


# ── Main verify function ───────────────────────────────────────────────────────

def verify_proposal(
    cycle_id: str,
    contract: dict,
    root: Path,
    today: str | None = None,
    context: dict | None = None,
) -> dict[str, Any]:
    """Verify a proposal's realized fitness delta vs its registered contract.

    Parameters
    ----------
    cycle_id  : str
    contract  : dict — the registered fitness contract from the docket
                {sensor, expected_sign, band, check_by, placebo_to_beat,
                 falsifier_spec (a qledger-compatible check dict), ...}
    root      : Path — repo root
    today     : str | None — ISO date; defaults to today()
    context   : dict | None — optional regime context for triage

    Returns
    -------
    dict — verify record (schema metabolism.verify.v1).  Never raises.
    """
    try:
        if today is None:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        check_by = contract.get("check_by") or today
        if check_by > today:
            # check_by hasn't arrived yet — return pending record
            return _pending_record(cycle_id, contract, check_by)

        # Extract the falsifier spec (qledger-compatible check dict)
        falsifier_spec = contract.get("falsifier_spec") or {}
        asof = contract.get("asof") or ""

        # Re-grade using qledger_falsifier.evaluate_check()
        outcome, detail = _evaluate_contract(falsifier_spec, asof, check_by, root)

        # Apply measurement-lens triage
        triage = _measurement_lens_triage(outcome, contract, context)

        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record: dict[str, Any] = {
            "schema": SCHEMA,
            "cycle_id": cycle_id,
            "proposal_id": contract.get("proposal_id") or contract.get("dedup_hash"),
            "check_by": check_by,
            "contract": contract,
            "realized": {
                "outcome": outcome,
                "detail": detail,
                "delta_vs_contract": _delta_summary(outcome, contract),
            },
            "triage": triage,
            "authority": AUTHORITY_BLOCK,
            "ts": ts,
        }

        # If operator tap required, also append a governance row (NEVER-RAISE)
        if triage["action"] == "operator_tap":
            _append_governance_tap(cycle_id, contract, triage, root)

        # Append a lesson to lessons.jsonl so PROPOSE stops repeating dead constructions
        _append_lesson_from_verify(cycle_id, contract, triage, outcome, root)

        # Archive-on-verify: save the contract + outcome to agenda_archive/ for dream cycle
        _archive_on_verify(cycle_id, contract, record, root)

        return record

    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_verify.verify_proposal(%s): %s", cycle_id, exc)
        return {
            "schema": SCHEMA,
            "cycle_id": cycle_id,
            "proposal_id": None,
            "check_by": contract.get("check_by") if contract else None,
            "contract": contract or {},
            "realized": {"outcome": _UNVERIFIABLE, "detail": str(exc), "delta_vs_contract": None},
            "triage": {
                "classification": "unverifiable",
                "action": "operator_tap",
                "revert_plan": None,
                "operator_tap_reason": f"verify_proposal raised: {exc}",
            },
            "authority": AUTHORITY_BLOCK,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


def _evaluate_contract(
    falsifier_spec: dict,
    asof: str,
    check_by: str,
    root: Path,
) -> tuple[str, str]:
    """Delegate to qledger_falsifier.evaluate_check().  Returns (outcome, detail)."""
    try:
        from engine.qledger_falsifier import evaluate_check  # type: ignore[import]
        return evaluate_check(falsifier_spec or None, asof, check_by, root)
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_verify._evaluate_contract: %s", exc)
        return _UNVERIFIABLE, f"evaluate_check raised: {exc}"


def _delta_summary(outcome: str, contract: dict) -> str | None:
    """Return a one-line summary of the realized delta vs the contract."""
    sensor = contract.get("sensor", "")
    expected = contract.get("expected_sign", "")
    band = contract.get("band", "")
    return f"sensor={sensor} expected={expected} band={band!r} outcome={outcome}"


def _pending_record(cycle_id: str, contract: dict, check_by: str) -> dict[str, Any]:
    """Return a 'pending' verify record when check_by hasn't arrived."""
    return {
        "schema": SCHEMA,
        "cycle_id": cycle_id,
        "proposal_id": contract.get("proposal_id") or contract.get("dedup_hash"),
        "check_by": check_by,
        "contract": contract,
        "realized": {
            "outcome": "PENDING",
            "detail": f"check_by={check_by} has not yet arrived",
            "delta_vs_contract": None,
        },
        "triage": {
            "classification": "pending",
            "action": "wait",
            "revert_plan": None,
            "operator_tap_reason": None,
        },
        "authority": AUTHORITY_BLOCK,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _archive_on_verify(
    cycle_id: str,
    contract: dict,
    verify_record: dict,
    root: Path,
) -> None:
    """Archive agenda + verify outcome to agenda_archive/ for the dream cycle (NEVER-RAISE)."""
    try:
        from engine.metabolism.memory import archive_agenda  # type: ignore[import]
        # Load the agenda file for this cycle if available
        agenda_path = root / "data" / "metabolism" / "agenda" / f"{cycle_id}.json"
        agenda_data: dict = {}
        if agenda_path.exists():
            try:
                agenda_data = json.loads(agenda_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                agenda_data = {"contract": contract}
        else:
            agenda_data = {"contract": contract}
        archive_agenda(
            cycle_id=cycle_id,
            agenda_data=agenda_data,
            verify_outcome=verify_record,
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_verify._archive_on_verify: %s", exc)


def _append_lesson_from_verify(
    cycle_id: str,
    contract: dict,
    triage: dict,
    outcome: str,
    root: Path,
) -> None:
    """Append a lesson to lessons.jsonl after VERIFY grading (NEVER-RAISE).

    Encodes what worked, what failed, and the construction so PROPOSE stops
    repeating dead constructions.
    """
    try:
        from engine.metabolism.memory import append_lesson  # type: ignore[import]
        classification = triage.get("classification", "unknown")
        action = triage.get("action", "")
        what_worked = ""
        what_failed = ""
        if classification == "confirmed":
            what_worked = (
                f"Fitness contract held: sensor={contract.get('sensor')}, "
                f"band={contract.get('band')!r}, outcome={outcome}."
            )
        elif action == "revert_plan":
            what_failed = (
                f"Fitness contract missed (clean overfit): sensor={contract.get('sensor')}, "
                f"expected={contract.get('expected_sign')}, band={contract.get('band')!r}, "
                f"outcome={outcome}."
            )
        elif action == "operator_tap":
            what_failed = (
                f"Outcome ambiguous — operator tap required: "
                f"{triage.get('operator_tap_reason', '')} (outcome={outcome})."
            )
        else:
            what_failed = f"Outcome={outcome}, classification={classification}."

        construction = (
            f"sensor={contract.get('sensor')} kind={contract.get('kind')} "
            f"tier={contract.get('tier')} title={contract.get('title','')!r}"
        )
        append_lesson(
            cycle_id=cycle_id,
            verdict=classification,
            what_worked=what_worked,
            what_failed=what_failed,
            construction=construction,
            proposal_id=str(contract.get("proposal_id") or contract.get("dedup_hash") or ""),
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_verify._append_lesson_from_verify: %s", exc)


def _append_governance_tap(
    cycle_id: str,
    contract: dict,
    triage: dict,
    root: Path,
) -> None:
    """Append an operator-tap governance row (NEVER-RAISE).

    Uses engine.neuralweb.governance.append_event() so the row lands in
    the same governance.jsonl ledger that other organs use.
    """
    try:
        from engine.neuralweb.governance import append_event  # type: ignore[import]
        append_event(
            event_type="operator_override",
            target=f"metabolism.verify/{cycle_id}",
            article=None,
            authored_by="metabolism_verify",
            evidence={
                "cycle_id": cycle_id,
                "proposal_id": contract.get("proposal_id"),
                "triage_classification": triage.get("classification"),
                "operator_tap_reason": triage.get("operator_tap_reason"),
            },
            note=(
                f"Metabolism VERIFY stage requests operator review: "
                f"{triage.get('operator_tap_reason', '')}"
            ),
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_verify._append_governance_tap: %s", exc)


# ── File writer ────────────────────────────────────────────────────────────────

def write_verify_record(
    record: dict[str, Any],
    root: Path,
) -> Path | None:
    """Write a verify record to data/metabolism/verify/<cycle_id>.json atomically.

    Returns the path written, or None on error.  NEVER raises.
    """
    try:
        cycle_id = record.get("cycle_id", "unknown")
        out_dir = root.joinpath(*OUTPUT_PATH)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{cycle_id}.json"
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        tmp.replace(out_path)
        return out_path
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_verify.write_verify_record: %s", exc)
        return None
