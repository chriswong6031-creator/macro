"""engine.research_factory.adapter_cycle_pattern — Cycle-Pattern (CPI) domain adapter.

ROUTES and RECORDS — never re-implements an evaluator (domain-seam contract,
identical to adapter_oracle / adapter_cortex / adapter_alpha_grammar).
``route_all()`` returns a list of routing dicts; it NEVER runs a scan, refits a
model, or advances any lifecycle.  The CPI discovery engine (the lattice / FT
harness, source ``cycle_pattern_scan``) is the authority that writes the
candidate source-of-truth; this adapter only projects its statuses onto factory
states and passes artifact evidence through.

Candidate source-of-truth (RF-2, projection law)
-------------------------------------------------
    data/cycle_pattern/pattern_candidates.jsonl

Absent-file-safe: if the file does not exist yet (it does NOT exist on this
branch — no candidate has been scanned this wave), ``route_all()`` returns [].
Each line matches the schema constant ``CYCLE_PATTERN_CANDIDATE_SCHEMA``
(``research_factory.candidate.v1`` with ``domain='cycle_pattern'``,
``source='cycle_pattern_scan'``, ``candidate_type='cycle_pattern_rule'``).

Fixed status projection (RF-2 — domain status → factory state)
--------------------------------------------------------------
CPI candidate statuses project onto factory states via this FIXED mapping.
The projection is re-read at call time and NEVER persisted as a factory status
field (RF-2 — on conflict the CPI source wins):

    candidate         → proposed
    registered        → registered
    screened          → screened
    numeric_rejected  → numeric_rejected   (kill_evidence populated, RF-10)

Any unknown domain status falls back to ``proposed`` (the entry state).

Kill evidence (RF-10)
---------------------
``numeric_rejected`` routes carry a ``kill_evidence`` dict sourced from the
candidate's own ``kill`` block (n_at_kill / kill_class / gate artifact), so a
CPI rejection reaching the factory is never laundered into a bare 'falsified'.

Trial accounting (RF-6)
-----------------------
mode = ``'rf_family'`` — each candidate declares its FT/lattice trial family as
``family = 'rf.cycle_pattern.<trial_family>'`` (the ``trial_family`` field on
the candidate row supplies ``<trial_family>``; when absent, the family is left
None and the caller/screened-gate will refuse the screened transition).

Trial-family declaration — NOT done here (P3 prereg boundary)
-------------------------------------------------------------
This adapter does NOT declare ``rf.cycle_pattern.*`` in
``data/trial_ledger.jsonl``.  Per the masterplan §6/§8 and RF-6, that
declaration belongs to the P3 prereg commit (prereg-then-run discipline).
RF-6's screened gate fires only when a candidate reaches ``screened``; no CPI
candidate reaches ``screened`` this wave (the candidate file is absent), so no
declaration is required here.  Declaring the family early would spend budget
before a trial exists.  The adapter emits the intended family *name* on every
route so the P3 prereg commit and the screened-gate agree on the string.

Truth-guard (masterplan §2 truth layer / §6 Truth-Guard reasoning lines)
------------------------------------------------------------------------
``truth_guard(candidates)`` cross-checks each candidate statement against the
``promoted_null`` truths in ``data/cycle_pattern/truths.jsonl`` (via
``engine.cycle_pattern.truths.active_truths``) and FLAGS — never auto-rejects —
any candidate whose (target, scope.families) collides with a promoted null.
Dead-stays-dead (§8 truth-layer law) is enforced by the downstream
dedup/challenge layer that consumes the flag, not by this adapter.

Pure stdlib: no pandas, no yaml, no heavy imports at module level.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Candidate source-of-truth schema (documented constant)
# ---------------------------------------------------------------------------

#: Documented schema for one line of data/cycle_pattern/pattern_candidates.jsonl.
#: Matches research_factory.candidate.v1 with the CPI domain fields fixed.
#: This is a *documentation* constant (the shape the CPI scan must emit); the
#: adapter reads defensively and never requires every key to be present.
CYCLE_PATTERN_CANDIDATE_SCHEMA: dict[str, Any] = {
    "schema": "research_factory.candidate.v1",
    "authority": "display_only",
    "domain": "cycle_pattern",
    "source": "cycle_pattern_scan",
    "candidate_type": "cycle_pattern_rule",
    # CPI-specific fields the scan supplies:
    "candidate_id": "<str: rf-YYYYMMDD-cycle_pattern-...>",
    "created_at": "<iso8601 str>",
    # NOTE: 'status' here is the CPI DOMAIN status (candidate|registered|
    # screened|numeric_rejected) — the projection *input*.  It is NOT a factory
    # STATES value and is deliberately re-read + projected at call time (RF-2),
    # never persisted into a factory candidate row's 'status' field.  The factory
    # ingest writes the PROJECTED state (project_cycle_pattern_status(...)) into
    # the factory row it validates; the CPI file keeps the domain vocabulary.
    "status": "candidate|registered|screened|numeric_rejected",
    "hypothesis": "<str: falsifiable statement>",
    "mechanism": "<str: why it might persist>",
    "statement": "<str: the graded claim (used by truth_guard target match)>",
    "target": "<str: the prediction target, matched against truths.target>",
    "scope": {"families": ["<str>"], "regions": ["<str>"], "sample": "<str>"},
    "trial_family": "<str: bare family suffix; becomes rf.cycle_pattern.<trial_family>>",
    "kill": {                # present only when status == numeric_rejected
        "n_at_kill": "<int>",
        "kill_class": "<str: falsified|underpowered_accruing|...>",
        "gate_ref": "<str: data/...*.json gate artifact path>",
    },
    "artifacts": {},         # arbitrary evidence dict, passed through verbatim
}

# ---------------------------------------------------------------------------
# Fixed CPI status → factory state projection (RF-2, canonical)
# ---------------------------------------------------------------------------

#: Fixed mapping: CPI candidate status → research_factory state.
#: On conflict, the CPI candidate source wins (RF-2).
CYCLE_PATTERN_STATUS_TO_FACTORY_STATE: dict[str, str] = {
    "candidate":        "proposed",
    "registered":       "registered",
    "screened":         "screened",
    "numeric_rejected": "numeric_rejected",
}

#: Fallback for any unknown domain status: the factory entry state.
_FALLBACK_FACTORY_STATE = "proposed"

#: rf.* trial-family prefix for the cycle_pattern domain.
_RF_FAMILY_PREFIX = "rf.cycle_pattern."


def project_cycle_pattern_status(domain_status: str) -> str:
    """Project a CPI candidate status to a factory state (RF-2).

    Unknown statuses fall back to 'proposed' (the factory entry state).
    """
    return CYCLE_PATTERN_STATUS_TO_FACTORY_STATE.get(
        domain_status, _FALLBACK_FACTORY_STATE
    )


# ---------------------------------------------------------------------------
# Candidate loader (absent-file-safe, pure stdlib)
# ---------------------------------------------------------------------------

def load_candidates(data_dir: Path | None = None) -> list[dict]:
    """Load data/cycle_pattern/pattern_candidates.jsonl absent-safely.

    Returns [] when the file does not exist or cannot be parsed.
    Pure stdlib — no pandas.
    """
    _dir = Path(data_dir) if data_dir else Path("data")
    path = _dir / "cycle_pattern" / "pattern_candidates.jsonl"
    if not path.exists():
        log.debug(
            "pattern_candidates.jsonl not found at %s — cycle_pattern adapter returning []",
            path,
        )
        return []
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except OSError as exc:
        log.warning("load_candidates: read failed: %s", exc)
    return rows


# ---------------------------------------------------------------------------
# Trial-family name builder (RF-6)
# ---------------------------------------------------------------------------

def _trial_family_name(candidate: dict) -> str | None:
    """Build the rf.cycle_pattern.<trial_family> name from a candidate row.

    Returns None when the candidate does not declare a trial_family (the
    screened gate then refuses the transition — RF-6).  The suffix is used
    verbatim (the CPI scan owns valid suffixes); no invention here.
    """
    suffix = candidate.get("trial_family")
    if not suffix or not isinstance(suffix, str):
        return None
    return f"{_RF_FAMILY_PREFIX}{suffix}"


# ---------------------------------------------------------------------------
# Kill-evidence builder (RF-10)
# ---------------------------------------------------------------------------

def _kill_evidence(candidate: dict) -> dict:
    """Build a kill_evidence dict from the candidate's own 'kill' block (RF-10).

    Sources n_at_kill / kill_class / gate ref from the candidate so a CPI
    numeric_rejected is not laundered into a bare 'falsified'.
    """
    kill = candidate.get("kill") or {}
    return {
        "n_at_kill": kill.get("n_at_kill", 0),
        "kill_class": kill.get("kill_class", "falsified"),
        "mde_at_n": kill.get("mde_at_n"),      # challenger fills if absent
        "gate_ref": kill.get("gate_ref"),
        "source": "cycle_pattern_candidate_kill_block",
    }


# ---------------------------------------------------------------------------
# Single-candidate router
# ---------------------------------------------------------------------------

def route_candidate(candidate: dict, *, data_dir: Path | None = None) -> dict:
    """Route a single CPI candidate through the factory adapter.

    Returns a routing dict (NEVER evaluates).  Keys:
      candidate_id     : str — CPI candidate id
      spec_ref         : str — same as candidate_id (CPI scan is the authority)
      domain_status    : str — raw CPI status from the candidate row
      projected_state  : str — factory state projected via RF-2 mapping
      trial_accounting : dict — mode='rf_family', family=rf.cycle_pattern.<...>
      artifact         : dict — the candidate's evidence dict (pass-through)
      kill_evidence    : dict | None — populated when projected_state==numeric_rejected
      note             : str — declaration boundary reminder (P3)
    """
    cand_id = candidate.get("candidate_id", "?")
    domain_status = candidate.get("status", "candidate")
    projected_state = project_cycle_pattern_status(domain_status)
    family = _trial_family_name(candidate)

    kill_evidence: dict | None = None
    if projected_state == "numeric_rejected":
        kill_evidence = _kill_evidence(candidate)

    return {
        "candidate_id": cand_id,
        "spec_ref": cand_id,   # CPI scan-issued id is the authority ref
        "domain_status": domain_status,
        "projected_state": projected_state,
        "trial_accounting": {
            "mode": "rf_family",
            "family": family,
            "declared_at": None,   # declared by the P3 prereg commit, not here
        },
        # Artifact evidence dict pass-through (RF-13-style evidence capture)
        "artifact": candidate.get("artifacts") or {},
        "kill_evidence": kill_evidence,
        "note": (
            "rf.cycle_pattern.* trial family is declared by the P3 prereg "
            "commit in data/trial_ledger.jsonl, NOT by this adapter (RF-6 "
            "screened gate fires only at 'screened'; none this wave)."
        ),
    }


# ---------------------------------------------------------------------------
# Batch adapter (public API)
# ---------------------------------------------------------------------------

def route_all(data_dir: Path | None = None) -> list[dict]:
    """Load all CPI candidates and route them (absent-file-safe).

    Returns [] when data/cycle_pattern/pattern_candidates.jsonl is absent.
    NEVER evaluates — projection + evidence pass-through only.
    """
    rows = load_candidates(data_dir)
    if not rows:
        log.debug("route_all: pattern_candidates absent or empty — returning []")
        return []

    results: list[dict] = []
    for cand in rows:
        try:
            results.append(route_candidate(cand, data_dir=data_dir))
        except Exception as exc:  # noqa: BLE001
            log.error(
                "route_all: route_candidate failed for %s: %s",
                cand.get("candidate_id", "?"), exc,
            )
    return results


# ---------------------------------------------------------------------------
# Truth-guard (masterplan §2 truth layer / §6 Truth-Guard reasoning)
# ---------------------------------------------------------------------------

def _families_of(obj: dict) -> frozenset[str]:
    """Extract scope.families as a frozenset (empty when absent/malformed)."""
    scope = obj.get("scope") or {}
    fams = scope.get("families")
    if not isinstance(fams, list):
        return frozenset()
    return frozenset(str(f) for f in fams)


def _norm_target(target: Any) -> str:
    """Normalise a target string for collision comparison (case/space-insensitive)."""
    if not isinstance(target, str):
        return ""
    return " ".join(target.lower().split())


def truth_guard(
    candidates: list[dict],
    *,
    truths_path: Path | None = None,
) -> list[dict]:
    """Flag candidates that collide with a promoted_null truth (flag-only).

    Cross-checks each candidate's (target, scope.families) against the active
    ``promoted_null`` truths in data/cycle_pattern/truths.jsonl (via
    ``engine.cycle_pattern.truths.active_truths``).  A candidate collides when
    its normalised target equals a promoted-null target AND its scope.families
    intersect that truth's scope.families.

    Returns a list of flag dicts (one per colliding candidate); NEVER mutates
    the candidate and NEVER auto-rejects (§8 truth-layer law: dead stays dead
    is enforced downstream by the dedup/challenge layer that consumes the flag).

    Each flag dict:
      candidate_id      : str
      flag              : 'promoted_null_collision'
      colliding_truth_id: str — the promoted_null truth_id it collides with
      target            : str — the candidate target that matched
      shared_families   : sorted list[str] — the intersecting families
      reason            : str — human-readable Truth-Guard reasoning line
    """
    from engine.cycle_pattern.truths import active_truths

    active = active_truths(truths_path)
    nulls = [t for t in active if t.get("status") == "promoted_null"]

    flags: list[dict] = []
    for cand in candidates:
        cand_target = _norm_target(cand.get("target"))
        if not cand_target:
            continue
        cand_families = _families_of(cand)
        for truth in nulls:
            if _norm_target(truth.get("target")) != cand_target:
                continue
            truth_families = _families_of(truth)
            shared = cand_families & truth_families
            if not shared:
                continue
            flags.append({
                "candidate_id": cand.get("candidate_id", "?"),
                "flag": "promoted_null_collision",
                "colliding_truth_id": truth.get("truth_id"),
                "target": cand.get("target"),
                "shared_families": sorted(shared),
                "reason": (
                    f"candidate {cand.get('candidate_id', '?')!r} target/scope "
                    f"collides with promoted_null truth "
                    f"{truth.get('truth_id')!r} (shared families "
                    f"{sorted(shared)}) — dead stays dead unless a new "
                    f"preregistered trial names this null (masterplan §8); "
                    f"FLAG only, dedup/challenge layer adjudicates."
                ),
            })

    return flags
