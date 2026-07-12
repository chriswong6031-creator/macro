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
import re
from datetime import date, datetime, timezone
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


# ── Shared date parser (R-V5-4) ───────────────────────────────────────────────

def parse_check_by(s: str) -> date | None:
    """Robustly parse a check_by string to a date object.

    Handles:
      - "YYYY-MM-DD"                 — canonical ISO date
      - "YYYY-M-D", "YYYY-M-DD", etc — non-zero-padded (LLM-authored)
      - ISO datetime with T/Z suffix — e.g. "2026-07-15T00:00:00Z"

    Returns None if the string is unparseable, so callers can route to
    operator visibility instead of silently mis-ordering.

    NEVER raises.
    """
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    # Strip optional time component: "2026-07-15T00:00:00Z" → "2026-07-15"
    # Match the date portion before any 'T' or space
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if not m:
        return None
    try:
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))
        return date(year, month, day)
    except (ValueError, OverflowError):
        return None


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

        check_by_raw = str(contract.get("check_by") or today)
        check_by_date = parse_check_by(check_by_raw)
        today_date = parse_check_by(today)

        # R-V5-4: unparseable check_by → operator visibility (quarantined)
        if check_by_date is None:
            log.warning(
                "metabolism_verify.verify_proposal: malformed check_by %r in cycle %s — "
                "quarantining as UNVERIFIABLE",
                check_by_raw, cycle_id,
            )
            triage = _measurement_lens_triage(_UNVERIFIABLE, contract, context)
            triage["operator_tap_reason"] = (
                f"malformed check_by quarantined: {check_by_raw!r} — "
                + (triage.get("operator_tap_reason") or "")
            )
            triage["classification"] = "unverifiable"
            triage["note"] = f"check_by {check_by_raw!r} could not be parsed (R-V5-4)"
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            record: dict[str, Any] = {
                "schema": SCHEMA,
                "cycle_id": cycle_id,
                "proposal_id": contract.get("proposal_id") or contract.get("dedup_hash"),
                "check_by": check_by_raw,
                "contract": contract,
                "realized": {
                    "outcome": _UNVERIFIABLE,
                    "detail": f"malformed check_by quarantined: {check_by_raw!r}",
                    "delta_vs_contract": None,
                },
                "triage": triage,
                "authority": AUTHORITY_BLOCK,
                "ts": ts,
            }
            if triage["action"] == "operator_tap":
                _append_governance_tap(cycle_id, contract, triage, root)
            return record

        check_by = check_by_date.strftime("%Y-%m-%d")  # normalized canonical form
        if today_date is None or check_by_date > today_date:
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

        # Append a strategic memory row so the steering loop remembers outcomes (R-V4-3e)
        _append_strategic_memory_from_verify(cycle_id, contract, triage, outcome, root)

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
        lobe = str(contract.get("lobe") or contract.get("lobe_id") or "")
        append_lesson(
            cycle_id=cycle_id,
            verdict=classification,
            what_worked=what_worked,
            what_failed=what_failed,
            construction=construction,
            proposal_id=str(contract.get("proposal_id") or contract.get("dedup_hash") or ""),
            lobe=lobe,
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_verify._append_lesson_from_verify: %s", exc)


def _append_strategic_memory_from_verify(
    cycle_id: str,
    contract: dict,
    triage: dict,
    outcome: str,
    root: Path,
) -> None:
    """Append a deterministic strategic memory row after VERIFY grading (NEVER-RAISE).

    Verdict and measurement_lens_class are copied verbatim from the verify
    outcome — no LLM text, no origination.  Called only from verify_proposal()
    so it runs exactly once per closed contract.
    """
    try:
        from engine.metabolism.mission import append_strategic_memory  # type: ignore[import]
        classification = triage.get("classification", "unknown")
        row: dict = {
            "lobe": contract.get("lobe") or contract.get("lobe_id") or "",
            "cycle_id": cycle_id,
            "sensor": str(contract.get("sensor") or ""),
            "verdict": outcome,                    # verbatim from verify
            "measurement_lens_class": classification,  # verbatim from triage
            "check_by": contract.get("check_by"),
            "notes": f"triage_action={triage.get('action', '')}",
        }
        append_strategic_memory(row, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_verify._append_strategic_memory_from_verify: %s", exc)


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


# ── Fitness-floor demotion ladder (V2-C) ──────────────────────────────────────
#
# Per-lobe journal at data/metabolism/lifecycle/<lobe_id>.jsonl.
# Each row: {ts, lobe_id, breach_type, counted, reason, regime_paused, health_status}.
#
# Breach types:
#   logic_breach  — a real fitness-floor failure (the only type that counts toward
#                   the circuit breaker).
#   health_miss   — health.py reports missing/degraded/stale (NOT counted; dead feed
#                   ≠ bad lobe per R-V2-3 demotion-safety).
#
# Circuit breaker:
#   logic breaches >= BREAKER_TRIP_ACTIVE → proposal: active→probation
#   logic breaches >= BREAKER_TRIP_PROBATION → proposal: probation→demoted
#   demoted → emits a DO_NOT_REBUILD docket row
#
# INERT: emits proposals + docket items, never auto-retires.

SCHEMA_LIFECYCLE_JOURNAL = "metabolism.lifecycle_journal.v1"
LIFECYCLE_DIR = ("data", "metabolism", "lifecycle")

# Health statuses that must NOT count as logic breaches (R-V2-3 demotion safety)
_HEALTH_EXCLUDED_STATUSES = frozenset({"missing", "degraded", "stale", "unknown"})

_BREAKER_TRIP_ACTIVE = 3     # consecutive logic breaches → active→probation
_BREAKER_TRIP_PROBATION = 3  # consecutive logic breaches while on probation → demoted


def _lobe_journal_path(lobe_id: str, root: Path) -> Path:
    """Return the path for a lobe's lifecycle journal."""
    return root.joinpath(*LIFECYCLE_DIR) / f"{lobe_id}.jsonl"


def journal_breach(
    lobe_id: str,
    *,
    breach_type: str,
    health_status: str | None = None,
    reason: str = "",
    regime_paused: bool = False,
    all_inputs_absent: bool = False,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Journal one fitness-floor assessment row for a lobe.

    Parameters
    ----------
    lobe_id : str
    breach_type : str
        "logic_breach" — a real fitness-floor failure (counted toward breaker).
        "health_miss"  — health.py missing/degraded/stale (NOT counted).
        "pass"         — floor passed (resets consecutive breach counter).
    health_status : str | None
        The health.py status string (fresh/stale/missing/degraded/unknown).
        If this is in _HEALTH_EXCLUDED_STATUSES, the breach is NOT counted.
    reason : str
    regime_paused : bool
        If True, the lobe is in a regime-aware pause (no demotion emitted even
        if breaker would trip).
    all_inputs_absent : bool
        If True, this is an all-inputs-absent case.  An adversary non-veto is
        required before any demotion proposal; this is noted in the journal row.
    root : str | Path | None

    Returns
    -------
    dict — the journal row written.  NEVER raises.
    """
    try:
        r = Path(root) if root is not None else Path(__file__).resolve().parent.parent.parent
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Determine whether this breach actually counts toward the circuit breaker
        excluded_by_health = (
            health_status is not None
            and health_status in _HEALTH_EXCLUDED_STATUSES
        )
        counted = (
            breach_type == "logic_breach"
            and not excluded_by_health
            and not regime_paused
        )

        row: dict[str, Any] = {
            "schema": SCHEMA_LIFECYCLE_JOURNAL,
            "ts": ts,
            "lobe_id": lobe_id,
            "breach_type": breach_type,
            "health_status": health_status,
            "counted": counted,
            "reason": reason,
            "regime_paused": regime_paused,
            "all_inputs_absent": all_inputs_absent,
            "adversary_nonveto_required": all_inputs_absent,
            "authority": {
                "is_context_only": True,
                "display_only": True,
                "not_a_signal": True,
                "note": (
                    "Lifecycle journal row. Demotion proposals are emitted by "
                    "grade_demotion_ladder(); nothing is auto-retired in this PR."
                ),
            },
        }

        # Append to lobe journal
        journal_dir = r.joinpath(*LIFECYCLE_DIR)
        journal_dir.mkdir(parents=True, exist_ok=True)
        journal_path = journal_dir / f"{lobe_id}.jsonl"
        with journal_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        return row
    except Exception as exc:  # noqa: BLE001
        log.warning("verify.journal_breach(%s): %s", lobe_id, exc)
        return {
            "schema": SCHEMA_LIFECYCLE_JOURNAL,
            "lobe_id": lobe_id,
            "breach_type": breach_type,
            "counted": False,
            "error": str(exc),
        }


def _read_journal_rows(lobe_id: str, root: Path) -> list[dict]:
    """Read all journal rows for a lobe.  Returns [] on any error."""
    try:
        p = _lobe_journal_path(lobe_id, root)
        if not p.exists():
            return []
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("verify._read_journal_rows(%s): %s", lobe_id, exc)
        return []


def _consecutive_counted_breaches(rows: list[dict]) -> int:
    """Return the count of consecutive counted breaches at the tail of the journal."""
    count = 0
    for row in reversed(rows):
        if row.get("breach_type") == "pass":
            break
        if row.get("counted", False):
            count += 1
        else:
            # uncounted row (health miss, regime paused) — does NOT reset the streak
            # but also doesn't count; skip and keep scanning
            pass
    return count


def _load_max_probation(root: Path) -> int | None:
    """Read max_probation_lobes from the IMMUTABLE metabolism_budget.yml. None on error."""
    try:
        import yaml  # noqa: PLC0415
        cfg = yaml.safe_load((Path(root) / "config" / "metabolism_budget.yml").read_text())
        v = (cfg or {}).get("max_probation_lobes")
        return int(v) if v is not None else None
    except Exception:  # noqa: BLE001
        return None


def grade_demotion_ladder(
    lobe_id: str,
    current_lifecycle_state: str,
    *,
    regime_paused: bool = False,
    all_inputs_absent: bool = False,
    adversary_nonveto: bool = False,   # FAIL-CLOSED (R-V2-3): absent adversary → block
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate the demotion ladder for a lobe and emit a lifecycle proposal if warranted.

    Reads data/metabolism/lifecycle/<lobe_id>.jsonl and counts consecutive
    logic breaches.  If the circuit breaker trips, calls lifecycle.transition()
    to emit a proposal (INERT: proposal + docket item only, never auto-retires).

    DEMOTION SAFETY (R-V2-3):
      - Only counted=True rows (logic_breach, not health-excluded, not regime-paused)
        count toward the circuit breaker.
      - all_inputs_absent → the adversary must AFFIRMATIVELY non-veto (default
        False = fail-closed); demotion of an all-inputs-absent lobe is blocked
        unless the caller wires a genuine adversary non-veto.
      - regime_paused=True → no demotion emitted.

    Returns
    -------
    dict — ladder state + proposal result.  NEVER raises.
    """
    result: dict[str, Any] = {
        "lobe_id": lobe_id,
        "current_lifecycle_state": current_lifecycle_state,
        "consecutive_counted_breaches": 0,
        "breaker_tripped": False,
        "regime_paused": regime_paused,
        "all_inputs_absent": all_inputs_absent,
        "adversary_nonveto_blocked": False,
        "proposal": None,
        "authority": {
            "is_context_only": True,
            "display_only": True,
            "not_a_signal": True,
            "note": "Demotion ladder state. INERT: proposals only, no autonomous retires.",
        },
    }
    try:
        r = Path(root) if root is not None else Path(__file__).resolve().parent.parent.parent

        rows = _read_journal_rows(lobe_id, r)
        consecutive = _consecutive_counted_breaches(rows)
        result["consecutive_counted_breaches"] = consecutive

        # Regime-aware pause — no demotion even if breaker trips
        if regime_paused:
            result["breaker_tripped"] = False
            return result

        # All-inputs-absent: require adversary non-veto
        if all_inputs_absent and not adversary_nonveto:
            result["adversary_nonveto_blocked"] = True
            log.info(
                "lifecycle.grade_demotion_ladder: %s all_inputs_absent + no adversary "
                "non-veto — demotion blocked",
                lobe_id,
            )
            return result

        # Determine if breaker trips
        trip_threshold = (
            _BREAKER_TRIP_PROBATION
            if current_lifecycle_state == "probation"
            else _BREAKER_TRIP_ACTIVE
        )

        if consecutive < trip_threshold:
            return result

        result["breaker_tripped"] = True

        # Determine the demotion edge
        from_to_map = {
            "active": ("active", "probation"),
            "probation": ("probation", "demoted"),
            "demoted": ("demoted", "retired"),
        }
        edge = from_to_map.get(current_lifecycle_state)
        if edge is None:
            log.info(
                "lifecycle.grade_demotion_ladder: %s in state %r — no demotion edge",
                lobe_id, current_lifecycle_state,
            )
            return result

        from_state, to_state = edge

        # ANTI-CASCADE CAP (R-V2-7): do not push a NEW lobe into probation once
        # max_probation_lobes are already there — a feed outage that trips many
        # active lobes at once must not cascade the whole roster to probation.
        if to_state == "probation":
            try:
                from engine.metabolism.lobe_registry import probation_count  # noqa: PLC0415
                cap = _load_max_probation(r)
                cur = probation_count(root=r)
                if cap is not None and cur >= cap:
                    result["probation_cap_held"] = True
                    log.info(
                        "grade_demotion_ladder: %s active->probation HELD — probation "
                        "count %d >= cap %d (anti-cascade)", lobe_id, cur, cap,
                    )
                    return result
            except Exception as exc:  # noqa: BLE001
                # Fail-closed: if we cannot verify the cap, do NOT emit the demotion.
                log.warning("grade_demotion_ladder: probation-cap check failed (%s) — "
                            "holding demotion (fail-closed)", exc)
                result["probation_cap_held"] = True
                return result

        # Emit lifecycle proposal (INERT)
        from engine.metabolism.lifecycle import transition  # noqa: PLC0415
        proposal = transition(
            from_state, to_state, lobe_id,
            reason=(
                f"Fitness-floor demotion ladder: {consecutive} consecutive counted "
                f"logic breaches (threshold={trip_threshold}). "
                f"health.py missing/degraded/stale rows excluded per R-V2-3."
            ),
            root=r,
        )
        result["proposal"] = proposal

    except Exception as exc:  # noqa: BLE001
        log.warning("verify.grade_demotion_ladder(%s): %s", lobe_id, exc)
        result["error"] = str(exc)

    return result
