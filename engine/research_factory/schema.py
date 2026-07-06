"""engine.research_factory.schema — validators for §5 schemas.

All schema validators enforce the required top-level field
``"authority": "display_only"`` (RF-11).  Validation is pure (no I/O, no side
effects); validators return a list of human-readable violation strings —
empty list means clean.

Schemas implemented (research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md §5):
  candidate.v1      — data/research_factory/candidates.jsonl
  transition.v1     — data/research_factory/transitions.jsonl
  challenge.v1      — data/research_factory/challenges/<id>.json
  paper_monitor.v1  — data/research_factory/paper_monitor.jsonl
  health.v1         — data/research_factory/health.jsonl

Pure stdlib: no pandas, no yaml, no third-party imports.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants (enumerations from §3–§5)
# ---------------------------------------------------------------------------

STATES = frozenset({
    "proposed",
    "schema_rejected",
    "deduped",
    "registered",
    "awaiting_data",
    "screened",
    "numeric_rejected",
    "challenged",
    "human_review",
    "paper",
    "deferred",
    "promote_eligible",
    "scoped_build",
    "rejected",
    "retired",
})

# §5.1: candidate_type enum (RF-3)
CANDIDATE_TYPES = frozenset({
    "oracle_compound",
    "cortex_hypothesis",
    "alpha_family",
    "species",
    "external_idea",
    # CPI (cycle_pattern) domain — single additive value. Cycle-pattern
    # candidates are domain-homed lattice/feature-trial rules, not species
    # (which carry species-registry semantics in challenge.py dedup and
    # review_queue ordering) nor external human ideas; mapping onto either
    # existing generic type would misrepresent the taxonomy the same way
    # 'oracle_compound' and 'alpha_family' are domain-specific.  See
    # engine/research_factory/adapter_cycle_pattern.py.
    "cycle_pattern_rule",
})

# §5.1: source enum
SOURCES = frozenset({
    "oracle_brainstorm",
    "cortex",
    "alpha_grammar",
    "human",
    "external_report",
    "research_queue",
    "domain_registry",   # A2 amendment (W7): RF-2 pointer adoption of existing domain-homed compounds
    "cycle_pattern_scan",  # CPI (P2): the cycle_pattern lattice/FT scan that emits pattern_candidates.jsonl
})

# §5.1: claim_shape — RESERVED for metabolism enum (RF-3).
# These are the 4 legal values from engine/neuralweb/metabolism.py
# (CLAIM_SHAPES dict).  A factory row MUST pass through the metabolism-issued
# value verbatim or set claim_shape to null.  The factory NEVER invents one.
CLAIM_SHAPES = frozenset({
    "lead_lag",
    "conditional_regime",
    "entry_quality",
    "sector_conditional",
})

# §5.1: trial_accounting mode enum (RF-6)
TRIAL_ACCOUNTING_MODES = frozenset({
    "rf_family",
    "cortex_shared",
    "oracle_screen",
    "read_only",
})

# §5.1: domain enum
DOMAINS = frozenset({
    "oracle",
    "neuralweb",
    "entry",
    "factor",
    "macro",
    "options",
    "china",
    "us_stocks",
    "cycle_pattern",   # CPI (masterplan §6): Cycle-owned candidate lifecycle homed in the factory
})

# §5.3: reviewer recommendation advisory enum
REVIEWER_RECOMMENDATIONS = frozenset({
    "ADVISORY_REJECT",
    "ADVISORY_REVIEW",
    "ADVISORY_PASS",
})

# §5.3: blocker severity enum
BLOCKER_SEVERITIES = frozenset({"blocker", "major", "minor"})

# §5.3: blocker category enum
BLOCKER_CATEGORIES = frozenset({
    "lookahead",
    "parametric_lookahead",
    "survivorship",
    "overfit",
    "cost",
    "regime",
    "mechanism",
    "implementation",
    "data",
    "authority",
    "duplicate",
})

# §5.4: paper_status enum
PAPER_STATUSES = frozenset({
    "warmup",
    "operating",
    "review",
    "retire_recommended",
})

# §5.4: action enum
PAPER_ACTIONS = frozenset({"continue", "review", "retire_recommended"})

# RF-6: rf.* trial-family regex — must match and be <40 chars.
# Production family names read from data/trial_ledger.jsonl at validation time.
_RF_FAMILY_RE = re.compile(r"^rf\.[a-z_]+\.[a-z0-9_]+\Z")

# ---------------------------------------------------------------------------
# rf.* family helpers
# ---------------------------------------------------------------------------


def is_valid_rf_family_name(name: str) -> bool:
    """Return True if ``name`` matches the rf.* regex and is <40 chars."""
    return bool(_RF_FAMILY_RE.match(name)) and len(name) < 40


def _load_production_families(ledger_path: str | Path | None = None) -> frozenset[str]:
    """Load existing production trial family names from data/trial_ledger.jsonl.

    Absent-file-safe: returns empty frozenset if the file does not exist.
    Pure stdlib — no pandas.
    """
    import json

    path = Path(ledger_path) if ledger_path else Path("data") / "trial_ledger.jsonl"
    if not path.exists():
        return frozenset()
    families: set[str] = set()
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                fam = row.get("family")
                if fam and isinstance(fam, str):
                    families.add(fam)
    except OSError:
        pass
    return frozenset(families)


def validate_rf_family(name: str,
                       ledger_path: str | Path | None = None) -> list[str]:
    """Validate an rf.* trial family name per RF-6.

    Checks regex, length, and collision with existing production families from
    data/trial_ledger.jsonl (absent-file-safe).  Returns violation strings.
    """
    errs: list[str] = []
    if not is_valid_rf_family_name(name):
        errs.append(
            f"rf family {name!r} does not match ^rf\\.[a-z_]+\\.[a-z0-9_]+$ "
            f"or is >=40 chars"
        )
    prod_families = _load_production_families(ledger_path)
    if name in prod_families:
        errs.append(
            f"rf family {name!r} collides with an existing production family "
            f"in data/trial_ledger.jsonl — choose a distinct name"
        )
    return errs


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _req(row: dict, field: str, errs: list[str], label: str) -> Any:
    """Assert field present (not None) in row; append error if missing."""
    val = row.get(field)
    if val is None:
        errs.append(f"{label}: missing required field {field!r}")
    return val


def _authority_check(row: dict, errs: list[str], label: str) -> None:
    """All factory rows must carry authority='display_only' (RF-11)."""
    auth = row.get("authority")
    if auth != "display_only":
        errs.append(
            f"{label}: 'authority' must be 'display_only', got {auth!r}"
        )


# ---------------------------------------------------------------------------
# Validator: candidate.v1 (§5.1)
# ---------------------------------------------------------------------------

def validate_candidate(row: dict) -> list[str]:
    """Validate a research_factory.candidate.v1 row.

    Returns a list of human-readable violation strings (empty = clean).
    """
    errs: list[str] = []
    label = f"candidate({row.get('candidate_id', '?')})"

    _authority_check(row, errs, label)

    schema = row.get("schema")
    if schema != "research_factory.candidate.v1":
        errs.append(f"{label}: schema must be 'research_factory.candidate.v1', got {schema!r}")

    _req(row, "candidate_id", errs, label)
    _req(row, "created_at", errs, label)
    _req(row, "hypothesis", errs, label)
    _req(row, "mechanism", errs, label)

    # source is required (§4 proposed row); must be a known enum value when present.
    source = _req(row, "source", errs, label)
    if source is not None and source not in SOURCES:
        errs.append(f"{label}: source {source!r} not in {sorted(SOURCES)}")

    # candidate_type is required (§4 proposed row); must be a known enum value when present.
    ctype = _req(row, "candidate_type", errs, label)
    if ctype is not None and ctype not in CANDIDATE_TYPES:
        errs.append(f"{label}: candidate_type {ctype!r} not in {sorted(CANDIDATE_TYPES)}")

    domain = row.get("domain")
    if domain is not None and domain not in DOMAINS:
        errs.append(f"{label}: domain {domain!r} not in {sorted(DOMAINS)}")

    status = row.get("status")
    if status is not None and status not in STATES:
        errs.append(f"{label}: status {status!r} not in known states")

    # claim_shape: passthrough nullable (RF-3); when non-null must be one of
    # the 4 legal metabolism values (hardcoded here — see CLAIM_SHAPES comment).
    claim_shape = row.get("claim_shape")
    if claim_shape is not None and claim_shape not in CLAIM_SHAPES:
        errs.append(
            f"{label}: claim_shape {claim_shape!r} is not a valid metabolism "
            f"CLAIM_SHAPES value ({sorted(CLAIM_SHAPES)}) — the factory must "
            f"never invent a claim_shape; copy verbatim from the metabolism row "
            f"or leave null (RF-3)"
        )

    # trial_accounting validation (RF-6)
    ta = row.get("trial_accounting")
    if ta is not None:
        if not isinstance(ta, dict):
            errs.append(f"{label}: trial_accounting must be a dict")
        else:
            mode = ta.get("mode")
            if mode is not None and mode not in TRIAL_ACCOUNTING_MODES:
                errs.append(
                    f"{label}: trial_accounting.mode {mode!r} not in "
                    f"{sorted(TRIAL_ACCOUNTING_MODES)}"
                )
            if mode == "rf_family":
                fam = ta.get("family")
                if not fam or not isinstance(fam, str):
                    errs.append(
                        f"{label}: trial_accounting.mode='rf_family' requires "
                        f"a non-empty family string"
                    )
                elif not is_valid_rf_family_name(fam):
                    errs.append(
                        f"{label}: trial_accounting.family {fam!r} does not "
                        f"match ^rf\\.[a-z_]+\\.[a-z0-9_]+$ or is >=40 chars"
                    )

    # lineage (RF-15)
    lineage = row.get("lineage")
    if lineage is not None:
        if not isinstance(lineage, dict):
            errs.append(f"{label}: lineage must be a dict")
        else:
            gen = lineage.get("refinement_generation", 0)
            if not isinstance(gen, int) or gen < 0:
                errs.append(f"{label}: lineage.refinement_generation must be a non-negative int")
            if gen > 2:
                errs.append(
                    f"{label}: refinement_generation={gen} exceeds hard cap of 2 "
                    f"(RF-15 — generation 3 forces terminal rejected)"
                )

    return errs


# ---------------------------------------------------------------------------
# Validator: transition.v1 (§5.2)
# ---------------------------------------------------------------------------

# Actor enum
ACTORS = frozenset({"script", "codex", "sonnet", "fable", "operator"})
# Human actors — require actor_ref (RF-5)
HUMAN_ACTORS = frozenset({"fable", "operator"})


def validate_transition(row: dict) -> list[str]:
    """Validate a research_factory.transition.v1 row."""
    errs: list[str] = []
    label = f"transition({row.get('candidate_id', '?')} {row.get('from','?')}→{row.get('to','?')})"

    _authority_check(row, errs, label)

    schema = row.get("schema")
    if schema != "research_factory.transition.v1":
        errs.append(f"{label}: schema must be 'research_factory.transition.v1', got {schema!r}")

    _req(row, "candidate_id", errs, label)
    _req(row, "as_of", errs, label)

    from_state = row.get("from")
    to_state = row.get("to")
    if from_state is not None and from_state not in STATES:
        errs.append(f"{label}: 'from' state {from_state!r} is not a known state")
    if to_state is not None and to_state not in STATES:
        errs.append(f"{label}: 'to' state {to_state!r} is not a known state")

    actor = row.get("actor")
    if actor is not None and actor not in ACTORS:
        errs.append(f"{label}: actor {actor!r} not in {sorted(ACTORS)}")

    # Human actors require actor_ref (RF-5)
    if actor in HUMAN_ACTORS:
        actor_ref = row.get("actor_ref")
        if not actor_ref:
            errs.append(
                f"{label}: actor={actor!r} is a human actor — "
                f"'actor_ref' (session/PR ref) is required (RF-5)"
            )

    return errs


# ---------------------------------------------------------------------------
# Validator: challenge.v1 (§5.3)
# ---------------------------------------------------------------------------

def validate_challenge(row: dict) -> list[str]:
    """Validate a research_factory.challenge.v1 row."""
    errs: list[str] = []
    label = f"challenge({row.get('candidate_id', '?')})"

    _authority_check(row, errs, label)

    schema = row.get("schema")
    if schema != "research_factory.challenge.v1":
        errs.append(f"{label}: schema must be 'research_factory.challenge.v1', got {schema!r}")

    _req(row, "candidate_id", errs, label)
    _req(row, "challenged_at", errs, label)

    reviewer = row.get("reviewer")
    if reviewer is not None:
        if not isinstance(reviewer, dict):
            errs.append(f"{label}: reviewer must be a dict")
        else:
            rec = reviewer.get("recommendation")
            if rec is not None and rec not in REVIEWER_RECOMMENDATIONS:
                errs.append(
                    f"{label}: reviewer.recommendation {rec!r} not in "
                    f"{sorted(REVIEWER_RECOMMENDATIONS)}"
                )
            # Confidence scores are forbidden (RF-7, RF-16)
            if reviewer.get("confidence_score") is not None:
                errs.append(
                    f"{label}: reviewer.confidence_score is forbidden (RF-7/RF-16 — "
                    f"LLM confidence scores prohibited)"
                )
            blockers = reviewer.get("blockers", [])
            for i, b in enumerate(blockers or []):
                if not isinstance(b, dict):
                    continue
                sev = b.get("severity")
                if sev is not None and sev not in BLOCKER_SEVERITIES:
                    errs.append(f"{label}: blocker[{i}].severity {sev!r} not in {sorted(BLOCKER_SEVERITIES)}")
                cat = b.get("category")
                if cat is not None and cat not in BLOCKER_CATEGORIES:
                    errs.append(f"{label}: blocker[{i}].category {cat!r} not in {sorted(BLOCKER_CATEGORIES)}")

    return errs


# ---------------------------------------------------------------------------
# Validator: paper_monitor.v1 (§5.4)
# ---------------------------------------------------------------------------

def validate_paper_monitor(row: dict) -> list[str]:
    """Validate a research_factory.paper_monitor.v1 row."""
    errs: list[str] = []
    label = f"paper_monitor({row.get('candidate_id', '?')} as_of={row.get('as_of','?')})"

    _authority_check(row, errs, label)

    schema = row.get("schema")
    if schema != "research_factory.paper_monitor.v1":
        errs.append(f"{label}: schema must be 'research_factory.paper_monitor.v1', got {schema!r}")

    _req(row, "candidate_id", errs, label)
    _req(row, "as_of", errs, label)

    status = row.get("paper_status")
    if status is not None and status not in PAPER_STATUSES:
        errs.append(f"{label}: paper_status {status!r} not in {sorted(PAPER_STATUSES)}")

    action = row.get("action")
    if action is not None and action not in PAPER_ACTIONS:
        errs.append(f"{label}: action {action!r} not in {sorted(PAPER_ACTIONS)}")

    return errs


# ---------------------------------------------------------------------------
# Validator: health.v1 (§5.5)
# ---------------------------------------------------------------------------

def validate_health(row: dict) -> list[str]:
    """Validate a research_factory.health.v1 row."""
    errs: list[str] = []
    label = f"health(as_of={row.get('as_of','?')})"

    _authority_check(row, errs, label)

    schema = row.get("schema")
    if schema != "research_factory.health.v1":
        errs.append(f"{label}: schema must be 'research_factory.health.v1', got {schema!r}")

    _req(row, "as_of", errs, label)

    return errs
