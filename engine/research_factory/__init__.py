"""engine.research_factory — cross-domain orchestration layer.

Charter: display-only, authority ceiling A0–A2 (observe / explain / attend).

This package owns candidate identity, state, transitions, challenge packets,
review packets, paper-monitor metadata, and retirement.  It delegates ALL
evaluation to existing engines (Oracle, cortex, alpha grammar, species).
Nothing in this package touches the board, alert triage, or scored surfaces.

Authority ceiling (binding — research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md §1):
  A0 observe   — read engine artifacts passively.
  A1 explain   — emit challenge packets (advisory-only, no gate authority).
  A2 attend    — populate the human review queue.
  Article 1 (origination ban) is the hard ceiling: no factory output — LLM or
  script — may originate a signal, trade, escalation, or claim.

Every artifact row carries ``"authority": "display_only"`` (RF-11).
"""
from __future__ import annotations

from engine.research_factory.schema import (
    CANDIDATE_TYPES,
    CLAIM_SHAPES,
    SOURCES,
    STATES,
    validate_candidate,
    validate_challenge,
    validate_health,
    validate_paper_monitor,
    validate_transition,
)
from engine.research_factory.state import (
    ALLOWED_TRANSITIONS,
    IllegalTransition,
    transition,
)
from engine.research_factory.ledger import (
    append_row,
    keep_first,
    load_jsonl,
)

__all__ = [
    # schema
    "CANDIDATE_TYPES",
    "CLAIM_SHAPES",
    "SOURCES",
    "STATES",
    "validate_candidate",
    "validate_challenge",
    "validate_health",
    "validate_paper_monitor",
    "validate_transition",
    # state machine
    "ALLOWED_TRANSITIONS",
    "IllegalTransition",
    "transition",
    # ledger
    "append_row",
    "keep_first",
    "load_jsonl",
]
