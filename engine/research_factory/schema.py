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

import hashlib
import json
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
    # Market Memory W6A is a candidate-conformance pointer only. It carries an
    # exact W2A preregistration read-back and no experiment or lifecycle grant.
    "market_memory_candidate",
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
    "market_memory",  # Market Memory W6A: pure preregistration conformance adapter
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
    "market_memory",  # W6A candidate conformance; no evaluator or lifecycle ownership
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


_MARKET_MEMORY_TRIPLE = (
    "market_memory",
    "market_memory_candidate",
    "market_memory",
)
_MARKET_MEMORY_CANDIDATE_FIELDS = frozenset(
    {
        "schema",
        "authority",
        "candidate_id",
        "created_at",
        "source",
        "candidate_type",
        "domain",
        "status",
        "hypothesis",
        "mechanism",
        "claim_shape",
        "spec_ref",
        "expected_failure_modes",
        "decay_conditions",
        "falsifiers",
        "trial_accounting",
        "evaluation_plan",
        "lineage",
        "flags",
        "artifacts",
        "transition_log",
    }
)
_MARKET_MEMORY_ACTION_AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "may_trade": False,
    "may_originate": False,
    "may_select_options_candidate": False,
    "may_execute": False,
    "may_write_options_episode": False,
    "may_append_outcome": False,
    "may_train_prophet": False,
}
_MARKET_MEMORY_CANDIDATE_ID_RE = re.compile(r"rf-market-memory-[a-f0-9]{64}\Z")
_MARKET_MEMORY_SPEC_ID_RE = re.compile(r"mmrfspec_[a-f0-9]{64}\Z")
_MARKET_MEMORY_TRIAL_ID_RE = re.compile(r"mmtrial_[a-f0-9]{64}\Z")
_MARKET_MEMORY_SHA256_RE = re.compile(r"[a-f0-9]{64}\Z")
_MARKET_MEMORY_CREATED_AT_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_MARKET_MEMORY_MAX_BYTES = 256 * 1024


def _market_memory_object(
    value: object,
    fields: frozenset[str],
    *,
    errs: list[str],
    label: str,
) -> dict | None:
    if type(value) is not dict:
        errs.append(f"{label}: must be an exact object")
        return None
    if set(value) != fields:
        errs.append(f"{label}: fields are not canonical")
        return None
    return value


def _market_memory_canonical_bytes(value: object) -> bytes | None:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        return None


def _market_memory_exact_json(value: object, expected: object) -> bool:
    supplied = _market_memory_canonical_bytes(value)
    canonical = _market_memory_canonical_bytes(expected)
    return supplied is not None and supplied == canonical


def _market_memory_bounded_int(
    value: object, *, minimum: int, maximum: int
) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _validate_market_memory_candidate_structure(
    row: dict, errs: list[str], label: str
) -> None:
    """Seal generic ledger admission; exact W2A byte authentication is adapter-owned."""

    supplied = (row.get("source"), row.get("candidate_type"), row.get("domain"))
    if not any(
        value == marker for value, marker in zip(supplied, _MARKET_MEMORY_TRIPLE)
    ):
        return
    mm_label = f"{label}: Market Memory structural projection"
    if supplied != _MARKET_MEMORY_TRIPLE:
        errs.append(f"{mm_label}: discriminator tuple must be exact")

    if set(row) != _MARKET_MEMORY_CANDIDATE_FIELDS:
        errs.append(f"{mm_label}: candidate fields are not canonical")
    body = _market_memory_canonical_bytes(row)
    if body is None or not body or len(body) > _MARKET_MEMORY_MAX_BYTES:
        errs.append(f"{mm_label}: candidate exceeds its canonical JSON bound")

    candidate_id = row.get("candidate_id")
    if type(candidate_id) is not str or not _MARKET_MEMORY_CANDIDATE_ID_RE.fullmatch(
        candidate_id
    ):
        errs.append(f"{mm_label}: candidate_id is malformed")
    spec_ref = row.get("spec_ref")
    if type(spec_ref) is not str or not _MARKET_MEMORY_SPEC_ID_RE.fullmatch(spec_ref):
        errs.append(f"{mm_label}: spec_ref is malformed")
    created_at = row.get("created_at")
    if type(created_at) is not str or not _MARKET_MEMORY_CREATED_AT_RE.fullmatch(
        created_at
    ):
        errs.append(f"{mm_label}: created_at is not exact microsecond UTC")

    exact_top_level = {
        "status": "proposed",
        "claim_shape": None,
        "expected_failure_modes": [
            "w4_retrieval_not_available",
            "w5_evaluation_not_run",
        ],
        "decay_conditions": [],
        "falsifiers": [],
        "trial_accounting": {
            "mode": "read_only",
            "family": None,
            "declared_at": None,
        },
        "evaluation_plan": {
            "status": "not_run",
            "primary_metric": None,
            "horizon_d": None,
            "min_n": None,
            "fdr_scope": None,
            "expected_half_life_d": None,
            "defaulted": False,
            "source": "market_memory_w2a_preregistration",
        },
        "lineage": {
            "respin_of": None,
            "superseded_by": None,
            "refinement_generation": 0,
        },
        "flags": [
            "market_memory_context_only",
            "w4_join_deferred",
            "w5_join_deferred",
        ],
        "transition_log": [],
    }
    for field, expected in exact_top_level.items():
        if not _market_memory_exact_json(row.get(field), expected):
            errs.append(f"{mm_label}: {field} must remain its inert canonical value")

    artifacts = _market_memory_object(
        row.get("artifacts"),
        frozenset({"market_memory_conformance"}),
        errs=errs,
        label=f"{mm_label}.artifacts",
    )
    if artifacts is None:
        return
    conformance = _market_memory_object(
        artifacts.get("market_memory_conformance"),
        frozenset(
            {
                "schema",
                "spec",
                "authority_granted",
                "challenge_completed",
                "challenge_ref",
                "emission_enabled",
                "training_eligible",
                "promotion_eligible",
                "action_authority",
            }
        ),
        errs=errs,
        label=f"{mm_label}.conformance",
    )
    if conformance is None:
        return
    if conformance.get("schema") != (
        "research_factory.market_memory_candidate_conformance.v1"
    ):
        errs.append(f"{mm_label}: conformance schema is not canonical")
    zero_authority = {
        "authority_granted": False,
        "challenge_completed": False,
        "challenge_ref": None,
        "emission_enabled": False,
        "training_eligible": False,
        "promotion_eligible": False,
        "action_authority": _MARKET_MEMORY_ACTION_AUTHORITY,
    }
    for field, expected in zero_authority.items():
        if not _market_memory_exact_json(conformance.get(field), expected):
            errs.append(f"{mm_label}: conformance {field} must remain zero authority")

    spec = _market_memory_object(
        conformance.get("spec"),
        frozenset(
            {
                "schema",
                "trial_registration_id",
                "trial_registration_sha256",
                "trial_registration_bytes",
                "trial_read_back",
                "w4_retrieval_join",
                "w5_evaluation_join",
            }
        ),
        errs=errs,
        label=f"{mm_label}.spec",
    )
    if spec is None:
        return
    if spec.get("schema") != "research_factory.market_memory_candidate_spec.v1":
        errs.append(f"{mm_label}: spec schema is not canonical")
    trial_id = spec.get("trial_registration_id")
    if type(trial_id) is not str or not _MARKET_MEMORY_TRIAL_ID_RE.fullmatch(trial_id):
        errs.append(f"{mm_label}: trial_registration_id is malformed")
    trial_sha = spec.get("trial_registration_sha256")
    if type(trial_sha) is not str or not _MARKET_MEMORY_SHA256_RE.fullmatch(trial_sha):
        errs.append(f"{mm_label}: trial_registration_sha256 is malformed")
    if not _market_memory_bounded_int(
        spec.get("trial_registration_bytes"),
        minimum=1,
        maximum=_MARKET_MEMORY_MAX_BYTES,
    ):
        errs.append(f"{mm_label}: trial_registration_bytes is out of bounds")
    if not _market_memory_exact_json(
        spec.get("w4_retrieval_join"),
        {"status": "deferred", "episode_set_id": None, "evidence_ref": None},
    ):
        errs.append(f"{mm_label}: W4 retrieval join must remain deferred and null")
    if not _market_memory_exact_json(
        spec.get("w5_evaluation_join"),
        {"status": "not_run", "evaluation_id": None, "evidence_ref": None},
    ):
        errs.append(f"{mm_label}: W5 evaluation join must remain not_run and null")

    read_back = _market_memory_object(
        spec.get("trial_read_back"),
        frozenset({"purge", "embargo", "trial_budget", "implementation"}),
        errs=errs,
        label=f"{mm_label}.trial_read_back",
    )
    if read_back is not None:
        purge = _market_memory_object(
            read_back.get("purge"),
            frozenset({"enabled", "before_seconds", "after_seconds"}),
            errs=errs,
            label=f"{mm_label}.purge",
        )
        if purge is not None and (
            purge.get("enabled") is not True
            or not _market_memory_bounded_int(
                purge.get("before_seconds"), minimum=0, maximum=10**9
            )
            or not _market_memory_bounded_int(
                purge.get("after_seconds"), minimum=0, maximum=10**9
            )
        ):
            errs.append(f"{mm_label}: purge read-back is structurally unsafe")
        embargo = _market_memory_object(
            read_back.get("embargo"),
            frozenset({"enabled", "duration_seconds"}),
            errs=errs,
            label=f"{mm_label}.embargo",
        )
        if embargo is not None and (
            embargo.get("enabled") is not True
            or not _market_memory_bounded_int(
                embargo.get("duration_seconds"), minimum=1, maximum=10**9
            )
        ):
            errs.append(f"{mm_label}: embargo read-back is structurally unsafe")
        budget = _market_memory_object(
            read_back.get("trial_budget"),
            frozenset(
                {
                    "max_trials",
                    "max_variants",
                    "family_trials_already_registered",
                }
            ),
            errs=errs,
            label=f"{mm_label}.trial_budget",
        )
        if budget is not None:
            max_trials = budget.get("max_trials")
            max_variants = budget.get("max_variants")
            already = budget.get("family_trials_already_registered")
            if (
                not _market_memory_bounded_int(
                    max_trials, minimum=1, maximum=10**6
                )
                or not _market_memory_bounded_int(
                    max_variants, minimum=1, maximum=max_trials
                )
                or not _market_memory_bounded_int(
                    already, minimum=0, maximum=max_trials - 1
                )
            ):
                errs.append(f"{mm_label}: trial-budget read-back is out of bounds")
        implementation = _market_memory_object(
            read_back.get("implementation"),
            frozenset({"model_sha256", "code_sha256", "config_sha256"}),
            errs=errs,
            label=f"{mm_label}.implementation",
        )
        if implementation is not None:
            for field in ("model_sha256", "code_sha256", "config_sha256"):
                value = implementation.get(field)
                if type(value) is not str or not _MARKET_MEMORY_SHA256_RE.fullmatch(
                    value
                ):
                    errs.append(f"{mm_label}: implementation {field} is malformed")

    spec_body = _market_memory_canonical_bytes(spec)
    if spec_body is not None and type(spec_ref) is str:
        expected_spec_ref = "mmrfspec_" + hashlib.sha256(spec_body).hexdigest()
        if spec_ref != expected_spec_ref:
            errs.append(f"{mm_label}: spec_ref does not bind the structural spec")
    if body is not None and type(candidate_id) is str:
        semantic = dict(row)
        semantic.pop("candidate_id", None)
        semantic.pop("created_at", None)
        semantic_body = _market_memory_canonical_bytes(semantic)
        if semantic_body is not None:
            expected_candidate_id = (
                "rf-market-memory-" + hashlib.sha256(semantic_body).hexdigest()
            )
            if candidate_id != expected_candidate_id:
                errs.append(
                    f"{mm_label}: candidate_id does not bind the structural candidate"
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

    _validate_market_memory_candidate_structure(row, errs, label)

    return errs


# ---------------------------------------------------------------------------
# Validator: transition.v1 (§5.2)
# ---------------------------------------------------------------------------

# Actor enum — mirrors state.py ALL_ACTORS (RF-5/RF-5b RUL-SUCC-7).
# "opus" is a model adjudicator; packet_ref enforcement lives in state.py.
ACTORS = frozenset({"script", "codex", "sonnet", "fable", "operator", "opus"})
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
