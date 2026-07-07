"""engine.research_factory.state — §4 state machine.

Enforces: allowed-pair matrix, actor-class allowlist, mandatory-field
presence, monotonic as_of, and the respin human-gate.

All logic is pure (no I/O except the one optional ledger existence check for
the 'screened' gate).  Callers do the I/O; this module just validates.

Note: the on-disk append-only discipline lives in ledger.py (RF-8).

State machine source: research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md §4.
Actor law source: §3 RF-5.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Allowed-transition matrix (§4, canonical)
# ---------------------------------------------------------------------------
# Map: from_state -> frozenset of allowed to_states.

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed":         frozenset({"schema_rejected", "deduped", "registered"}),
    "schema_rejected":  frozenset(),           # terminal
    "deduped":          frozenset(),           # terminal
    "registered":       frozenset({"screened", "awaiting_data", "rejected"}),
    "awaiting_data":    frozenset({"registered", "screened", "retired"}),
    "screened":         frozenset({"challenged", "numeric_rejected", "awaiting_data"}),
    "numeric_rejected": frozenset(),           # terminal* (requeue pointer written separately)
    "challenged":       frozenset({"human_review"}),
    "human_review":     frozenset({"paper", "deferred", "rejected", "scoped_build"}),
    "paper":            frozenset({"promote_eligible", "human_review", "retired"}),
    "deferred":         frozenset({"human_review", "retired"}),
    "promote_eligible": frozenset({"deferred", "scoped_build", "rejected"}),
    "scoped_build":     frozenset(),           # terminal
    "rejected":         frozenset(),           # terminal
    "retired":          frozenset(),           # terminal
}

# ---------------------------------------------------------------------------
# Actor-class rules (RF-5 / RF-5b RUL-SUCC-7)
# ---------------------------------------------------------------------------
# Script actors (mechanical): ingest/engine artefact-driven transitions.
SCRIPT_ACTORS = frozenset({"script", "codex", "sonnet"})
# Human-gate actors: require actor_ref.
HUMAN_ACTORS = frozenset({"fable", "operator"})
# Model adjudicators (RF-5b, RUL-SUCC-7): Opus may execute gate decisions
# with a machine-checkable audit artifact (packet_ref required for human-gate
# targets).  See research/FABLE_SUCCESSION_OPERATING_SYSTEM.md for the
# succession protocol; adjudication packets live in
# data/neuralweb/adjudication_queue.json (existence is NOT validated here —
# state.py stays filesystem-pure; use scripts/check_adjudication_packet.py).
MODEL_ADJUDICATORS = frozenset({"opus"})
ALL_ACTORS = SCRIPT_ACTORS | HUMAN_ACTORS | MODEL_ADJUDICATORS

# Script actors are NEVER permitted to enter these states (RF-5).
# Only human actors (fable/operator) or model adjudicators (opus, with both
# actor_ref AND packet_ref) may author them.
_HUMAN_GATE_TARGETS: frozenset[str] = frozenset({
    "paper",
    "deferred",
    "rejected",
    "scoped_build",
    "retired",
})

# Transitions INTO `human_review` are mechanical (packet + transition are
# script-authored unconditionally — RF-5/RF-7).  The FROM states that are
# human-gate targets require a human actor when LEAVING them.

# ---------------------------------------------------------------------------
# Mandatory fields per destination state (RF-5/RF-4 table)
# ---------------------------------------------------------------------------
# Each entry is: to_state -> list of required fields in the transition row.
_MANDATORY_ON_ENTRY: dict[str, list[str]] = {
    # awaiting_data: come_back_on required (RF-4/RF-5)
    "awaiting_data":    ["come_back_on"],
    # deferred: come_back_on required (RF-4)
    "deferred":         ["come_back_on"],
    # numeric_rejected: kill_evidence required (RF-10)
    "numeric_rejected": ["kill_evidence"],
    # rejected: kill_evidence required (RF-10)
    "rejected":         ["kill_evidence"],
    # retired: kill_evidence required (RF-10)
    "retired":          ["kill_evidence"],
    # scoped_build: new program doc ref required (RF-4)
    "scoped_build":     ["program_doc_ref"],
    # screened: artifact_refs required (§4 table)
    "screened":         ["artifact_refs"],
    # challenged: challenge_packet_ref required (§4 table)
    "challenged":       ["challenge_packet_ref"],
    # human_review: review_packet_ref required (§4 table)
    "human_review":     ["review_packet_ref"],
    # paper: seed_entry_ref, regime_at_entry, expected_half_life_d required (§4 table)
    "paper":            ["seed_entry_ref", "regime_at_entry", "expected_half_life_d"],
    # promote_eligible: promotion_gate_ref required (§4 table)
    "promote_eligible": ["promotion_gate_ref"],
}

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class IllegalTransition(Exception):
    """Raised when a requested transition violates the state machine rules."""


# ---------------------------------------------------------------------------
# Core transition validator (pure)
# ---------------------------------------------------------------------------


def _check_screened_gate(candidate: dict | None,
                         ledger_path: str | Path | None = None) -> str | None:
    """Check the RF-6 screened-gate: trial_accounting must be set, and for
    rf_family mode the family must exist (declared budget) in trial_ledger.jsonl.

    Returns an error string if the gate fails, or None if it passes.
    Absent ledger file is safe (treated as no declared families).
    """
    import json as _json

    if candidate is None:
        return None  # no candidate context — skip the gate (caller's responsibility)

    ta = candidate.get("trial_accounting")
    if not ta or not isinstance(ta, dict):
        return (
            "the 'screened' transition is refused: candidate.trial_accounting must be "
            "set before a candidate can be screened (RF-6)"
        )
    mode = ta.get("mode")
    if not mode:
        return (
            "the 'screened' transition is refused: candidate.trial_accounting.mode "
            "must be set (RF-6)"
        )

    if mode == "rf_family":
        family = ta.get("family")
        if not family:
            return (
                "the 'screened' transition is refused: trial_accounting.mode='rf_family' "
                "requires a non-empty family name (RF-6)"
            )
        # Check the family is KNOWN to the trial ledger.
        # RF-6 permits two declaration paths:
        #   (a) log_declared_budget() — writes a row with kind=='declared_budget'
        #   (b) log_grid()/log_trial() — writes rows with a config_hash and family
        #       (no 'kind' field); log_grid() rows and per-trial rows are
        #       structurally identical, so this gate proves the family exists in
        #       the ledger but CANNOT enforce the before-screening temporal order.
        #       That ordering guarantee is a caller/ingest responsibility enforced
        #       at W2, not by this gate.
        # Either path satisfies the ledger-known requirement.
        path = Path(ledger_path) if ledger_path else Path("data") / "trial_ledger.jsonl"
        declared_families: set[str] = set()
        if path.exists():
            try:
                with path.open(encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = _json.loads(line)
                        except Exception:
                            continue
                        fam = row.get("family")
                        if not fam:
                            continue
                        # Path (a): explicit declared_budget row
                        if row.get("kind") == "declared_budget":
                            declared_families.add(fam)
                        # Path (b): grid/trial row — presence of config_hash proves
                        # the family is known to the ledger (temporal ordering is a
                        # W2 ingest responsibility, not enforced here)
                        elif row.get("config_hash"):
                            declared_families.add(fam)
            except OSError:
                pass
        if family not in declared_families:
            return (
                f"the 'screened' transition is refused: rf_family {family!r} has no "
                f"declared-budget/grid row in data/trial_ledger.jsonl — call "
                f"TrialLedger.log_declared_budget() or log_grid() before screening (RF-6)"
            )

    return None  # gate passed


def transition(
    from_state: str,
    to_state: str,
    actor: str,
    transition_row: dict,
    candidate: dict | None = None,
    ledger_path: str | Path | None = None,
) -> None:
    """Validate a requested state transition.

    Parameters
    ----------
    from_state      : Current state of the candidate.
    to_state        : Requested next state.
    actor           : Who is performing the transition.
    transition_row  : The full transition dict (for mandatory-field checks).
    candidate       : Optional current candidate dict (for screened gate, RF-6,
                      respin gate, and monotonic as_of check).
    ledger_path     : Optional override for trial_ledger.jsonl path.

    Raises
    ------
    IllegalTransition
        On any violation: disallowed pair, actor-class violation, missing
        mandatory fields, screened-without-accounting, non-monotonic as_of,
        or respin registration by a script actor.
    """
    # 1. Both states must be known.
    if from_state not in ALLOWED_TRANSITIONS:
        raise IllegalTransition(
            f"unknown from_state {from_state!r}; "
            f"valid states: {sorted(ALLOWED_TRANSITIONS)}"
        )
    if to_state not in ALLOWED_TRANSITIONS:
        raise IllegalTransition(
            f"unknown to_state {to_state!r}; "
            f"valid states: {sorted(ALLOWED_TRANSITIONS)}"
        )

    # 2. Pair must be in the allowed-transition matrix.
    if to_state not in ALLOWED_TRANSITIONS[from_state]:
        allowed = sorted(ALLOWED_TRANSITIONS[from_state])
        raise IllegalTransition(
            f"{from_state!r} → {to_state!r} is not in the allowed-transition matrix. "
            f"Allowed from {from_state!r}: {allowed}"
        )

    # 3. Actor must be known.
    if actor not in ALL_ACTORS:
        raise IllegalTransition(
            f"actor {actor!r} is not a known actor class. "
            f"Valid actors: {sorted(ALL_ACTORS)}"
        )

    # 4. Actor-class gate: script actors cannot drive human-gate target states.
    if actor in SCRIPT_ACTORS and to_state in _HUMAN_GATE_TARGETS:
        raise IllegalTransition(
            f"actor={actor!r} (script class) is not permitted to transition "
            f"to {to_state!r} — only human actors (fable/operator) or model "
            f"adjudicators (opus, with actor_ref+packet_ref) may author "
            f"this state (RF-5)"
        )

    # 4b. RF-5b (RUL-SUCC-7): model adjudicators entering human-gate targets
    # require BOTH a non-empty actor_ref AND a non-empty packet_ref.
    # For non-human-gate transitions, model adjudicators are treated like
    # script actors — no additional constraints.
    if actor in MODEL_ADJUDICATORS and to_state in _HUMAN_GATE_TARGETS:
        actor_ref_ma = transition_row.get("actor_ref")
        packet_ref_ma = transition_row.get("packet_ref")
        if not actor_ref_ma:
            raise IllegalTransition(
                f"actor={actor!r} (model adjudicator) transitioning to "
                f"{to_state!r} requires a non-empty 'actor_ref' "
                f"(session/PR reference) in the transition row (RF-5b/RUL-SUCC-7)"
            )
        if not packet_ref_ma:
            raise IllegalTransition(
                f"actor={actor!r} (model adjudicator) transitioning to "
                f"{to_state!r} requires a non-empty 'packet_ref' "
                f"(adjudication packet id, e.g. 'adj-2026-07-06-example') in "
                f"the transition row (RF-5b/RUL-SUCC-7). Packets live in "
                f"data/neuralweb/adjudication_queue.json; existence is validated "
                f"separately by scripts/check_adjudication_packet.py."
            )

    # 5. Human actors require actor_ref.
    if actor in HUMAN_ACTORS:
        actor_ref = transition_row.get("actor_ref")
        if not actor_ref:
            raise IllegalTransition(
                f"actor={actor!r} is a human actor — 'actor_ref' "
                f"(session/PR reference) is required in the transition row (RF-5)"
            )

    # 6. Mandatory fields per destination state.
    required = _MANDATORY_ON_ENTRY.get(to_state, [])
    missing = [f for f in required if not transition_row.get(f)]
    if missing:
        raise IllegalTransition(
            f"transition to {to_state!r} is missing mandatory field(s): "
            f"{missing} (RF-4/RF-5 §4 table)"
        )

    # 7. Screened gate (RF-6): trial_accounting must be declared before screened.
    if to_state == "screened":
        err = _check_screened_gate(candidate, ledger_path)
        if err:
            raise IllegalTransition(err)

    # 8. Monotonic as_of: the new transition's as_of must be >= the last logged as_of.
    # Only checked when a candidate with a non-empty transition_log is provided.
    if candidate is not None:
        transition_log = candidate.get("transition_log") or []
        if transition_log:
            last_as_of = transition_log[-1].get("as_of", "")
            new_as_of = transition_row.get("as_of", "")
            if last_as_of and new_as_of and new_as_of < last_as_of:
                raise IllegalTransition(
                    f"non-monotonic as_of: transition as_of={new_as_of!r} is earlier "
                    f"than last logged as_of={last_as_of!r} — transitions must be "
                    f"appended in chronological order"
                )

    # 9. Respin human-gate (RF-5/RF-10/RF-15): registration of a respin candidate
    # (lineage.respin_of non-null, proposed→registered) requires a human actor.
    # Clock resurfacing (deferred→human_review, awaiting_data→registered|screened)
    # is mechanical A2 attention-routing and is NOT gated here.
    # RUL-SUCC-7 RULING: respin registration remains human-only (fable/operator).
    # Model adjudicators (opus) are NOT permitted to register respins — the
    # trial-spending commitment requires full human accountability.
    if to_state == "registered" and from_state == "proposed":
        lineage = (candidate or {}).get("lineage") or {}
        respin_of = lineage.get("respin_of")
        if respin_of:
            if actor in SCRIPT_ACTORS or actor in MODEL_ADJUDICATORS:
                raise IllegalTransition(
                    f"actor={actor!r} is not permitted to register a "
                    f"respin candidate (lineage.respin_of={respin_of!r}) — respin "
                    f"registration re-spends trials and requires a human actor "
                    f"(fable/operator) with actor_ref (RF-5/RUL-SUCC-7)"
                )

    # Passed all checks.
