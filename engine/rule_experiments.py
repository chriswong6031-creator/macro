"""engine/rule_experiments.py — R1 rule-experiment registry management.

Per §3.3 of NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md.

The registry is an append-only JSONL at ``data/rule_experiments/registry.jsonl``.
It is git-committed with a single writer (scripts/register_rule_experiment.py).

Every experiment registration calls
    TrialLedger.log_declared_budget(grid_size, family='replay')
using the FLAT pooled family — the docket-mandated single family so cumulative
trials accumulate across ALL experiments (sub-families are prohibited; they
create isolated multiple-testing islands, violating the flat pooling contract).

The runner (scripts/run_rule_replay.py) calls ``load_experiment`` and compares
every spec hash via ``verify_spec_hashes`` before accepting a run.

Lifecycle: registered → executed → reported
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.trial_ledger import TrialLedger

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REGISTRY_FAMILY = "replay"  # THE single pooled family — never sub-scoped (§3.3)
REGISTRY_FILENAME = "data/rule_experiments/registry.jsonl"
DEFAULT_N_FLOOR = 300       # minimum verdict-grade fires per cell (§3.3)

VALID_STATUSES = frozenset({"registered", "executed", "reported"})

# Repo root resolution (two levels above engine/)
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _default_registry_path() -> Path:
    return _REPO_ROOT / REGISTRY_FILENAME


def _default_ledger_path() -> Path:
    return _REPO_ROOT / "data" / "trial_ledger.jsonl"


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------
def _load_registry_raw(registry_path: Path) -> list[dict]:
    """Load all records from the JSONL file."""
    if not registry_path.exists():
        return []
    records = []
    with registry_path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                log.error("registry.jsonl line %d is corrupt: %s", lineno, exc)
    return records


def load_experiment(exp_id: str, registry_path: Path | None = None) -> dict:
    """Load a single experiment entry by exp_id, merging fields across all records.

    Lifecycle updates (update_experiment_status) append records that only contain
    the updated fields (e.g. status, status_updated_at) without repeating fields
    like spec_hashes.  A naïve "return the latest record" approach would lose
    spec_hashes after the first status update, causing verify_spec_hashes to raise
    GovernorRefusal every time after register → executed.

    This function merges ALL records for the exp_id in JSONL order (earliest first)
    so later records overwrite earlier ones on a per-field basis, but fields absent
    in a later record are NOT erased by it.  The result is the union of all fields
    with latest-wins semantics for fields that appear in multiple records.

    Raises KeyError if not found.
    """
    rp = registry_path or _default_registry_path()
    records = _load_registry_raw(rp)
    matches = [r for r in records if r.get("exp_id") == exp_id]
    if not matches:
        raise KeyError(
            f"Experiment {exp_id!r} not found in registry at {rp}. "
            "Register it via scripts/register_rule_experiment.py before running."
        )
    # Sort by registered_at (earliest first), then merge fields: later records
    # overwrite earlier ones per field, absent fields do NOT erase earlier values.
    sorted_matches = sorted(matches, key=lambda r: r.get("registered_at", ""))
    merged: dict = {}
    for record in sorted_matches:
        for k, v in record.items():
            # Only overwrite if the new record actually carries this key
            merged[k] = v
    return merged


def list_experiments(registry_path: Path | None = None) -> list[dict]:
    """Return deduplicated list of latest-entry-per-exp_id."""
    rp = registry_path or _default_registry_path()
    records = _load_registry_raw(rp)
    latest: dict[str, dict] = {}
    for r in records:
        eid = r.get("exp_id", "")
        if not eid:
            continue
        if eid not in latest or r.get("registered_at", "") > latest[eid].get("registered_at", ""):
            latest[eid] = r
    return list(latest.values())


# ---------------------------------------------------------------------------
# Spec hash verification (governor layer)
# ---------------------------------------------------------------------------
def verify_spec_hashes(
    exp_entry: dict,
    specs: list,  # list[RuleSpec]
) -> None:
    """Hard-fail if any spec hash doesn't match the registry entry.

    Parameters
    ----------
    exp_entry : dict from load_experiment()
    specs     : list of RuleSpec instances that the runner constructed

    Raises
    ------
    GovernorRefusal — on any hash mismatch or unregistered hash
    """
    from engine.rule_replay import GovernorRefusal

    registered_hashes: set[str] = set(exp_entry.get("spec_hashes", []))
    runner_hashes = {s.content_hash() for s in specs}

    extra = runner_hashes - registered_hashes
    missing = registered_hashes - runner_hashes

    messages = []
    if extra:
        messages.append(
            f"Runner constructed specs with unregistered hashes: {sorted(extra)}. "
            "These specs were not in the registry when the experiment was declared."
        )
    if missing:
        messages.append(
            f"Runner is missing specs that were declared in the registry: {sorted(missing)}. "
            "All declared spec hashes must be recomputed by the runner — no partial runs."
        )
    if messages:
        raise GovernorRefusal(
            f"Governor refusal for experiment {exp_entry.get('exp_id')!r}:\n"
            + "\n".join(messages)
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def register_experiment(
    exp_id: str,
    question: str,
    spec_hashes: list[str],
    declared_budget: int,
    verdict_criteria: str,
    *,
    n_floor: int = DEFAULT_N_FLOOR,
    derived_from_surface: str | None = None,
    needed_merge_columns: list[str] | None = None,
    base_cohort_predicates: list[list] | None = None,
    registry_path: Path | None = None,
    ledger_path: Path | None = None,
) -> dict:
    """Register a new rule experiment.

    Parameters
    ----------
    exp_id            : unique kebab-slug identifier
    question          : one-sentence question + grid-granularity justification
    spec_hashes       : list of sha256 content hashes for every RuleSpec in the grid
    declared_budget   : grid size (number of cells = len(spec_hashes))
    verdict_criteria  : frozen text or the literal "descriptive-only"
    n_floor           : minimum verdict-grade fires per cell (default 300)
    derived_from_surface : null or the exp_id of a previously seen descriptive
                        surface (RUL-P3 mandatory honesty stamp)
    needed_merge_columns : list of column names the runner must merge into fires_df
                        before CohortFilter applies (e.g. PIT regime columns for
                        DISP-GATE-1).  Empty list means no merge needed (default).
                        Other experiments are untouched when this is empty.
    base_cohort_predicates : list of (op, col, val) triples for the common
                        pre-filter applied to fires_full before per-spec cohort
                        filtering.  When set, the runner uses this instead of
                        specs[0].cohort for the initial fires_df subset.  Needed
                        for experiments where each spec has a different per-cell
                        predicate (e.g. regime state filter in DISP-GATE-1).
    registry_path     : override registry file path (default: data/rule_experiments/registry.jsonl)
    ledger_path       : override trial ledger path

    Returns
    -------
    dict — the registry entry that was appended

    Side-effects
    ------------
    1. Calls TrialLedger.log_declared_budget(declared_budget, family='replay')
    2. Appends one record to registry.jsonl
    """
    # Validation
    if not re.match(r"^[a-z0-9][a-z0-9_\-/]*$", exp_id):
        raise ValueError(
            f"exp_id must be a kebab/snake slug (a-z, 0-9, -, /, _), got {exp_id!r}"
        )
    if len(spec_hashes) == 0:
        raise ValueError("spec_hashes must be non-empty — the registry needs the full grid")
    if declared_budget != len(spec_hashes):
        raise ValueError(
            f"declared_budget ({declared_budget}) must equal len(spec_hashes) ({len(spec_hashes)}). "
            "The declared budget IS the full enumerated grid size."
        )
    if not question.strip():
        raise ValueError("question must be a non-empty string")

    rp = registry_path or _default_registry_path()
    lp = ledger_path or _default_ledger_path()

    # Check for duplicate exp_id (re-registration is allowed; just appends)
    existing = [r for r in _load_registry_raw(rp) if r.get("exp_id") == exp_id]
    if existing:
        log.warning(
            "Experiment %r already exists in registry (%d prior entries). "
            "Appending new registration (lifecycle update).",
            exp_id, len(existing)
        )

    # --- FDR accounting: log declared budget to the flat pooled family ---
    # This MUST happen before the run (§3.3).
    rp.parent.mkdir(parents=True, exist_ok=True)
    led = TrialLedger(lp, family=REGISTRY_FAMILY)
    led.log_declared_budget(
        declared_budget,
        family=REGISTRY_FAMILY,
        reason=f"exp_id={exp_id}; question={question[:80]!r}",
    )

    # --- Build registry entry ---
    entry: dict[str, Any] = {
        "exp_id": exp_id,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "spec_hashes": sorted(spec_hashes),
        "n_floor": n_floor,
        "declared_budget": declared_budget,
        "verdict_criteria": verdict_criteria,
        "derived_from_surface": derived_from_surface,
        "needed_merge_columns": needed_merge_columns or [],
        "base_cohort_predicates": base_cohort_predicates or [],
        "status": "registered",
    }

    with rp.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")

    log.info(
        "Registered experiment %r: budget=%d, family='%s'",
        exp_id, declared_budget, REGISTRY_FAMILY,
    )
    return entry


def update_experiment_status(
    exp_id: str,
    new_status: str,
    *,
    registry_path: Path | None = None,
    extra_fields: dict | None = None,
) -> dict:
    """Append a lifecycle update entry for an experiment.

    Idempotent: if the experiment is already at ``new_status``, appends anyway
    (for timestamped re-runs — §3.3 permits idempotent regrade with new executed event).
    """
    if new_status not in VALID_STATUSES:
        raise ValueError(
            f"status {new_status!r} is not in {sorted(VALID_STATUSES)}"
        )
    rp = registry_path or _default_registry_path()
    original = load_experiment(exp_id, rp)  # raises KeyError if not found

    update: dict[str, Any] = {
        "exp_id": exp_id,
        "registered_at": original["registered_at"],  # preserve original registration ts
        "status_updated_at": datetime.now(timezone.utc).isoformat(),
        "status": new_status,
    }
    if extra_fields:
        update.update(extra_fields)

    with rp.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(update) + "\n")

    log.info("Updated experiment %r → status=%r", exp_id, new_status)
    return update


# ---------------------------------------------------------------------------
# Cumulative pooled trial count summary helper
# ---------------------------------------------------------------------------
def pooled_replay_trial_count(registry_path: Path | None = None) -> int:
    """Return the cumulative pooled replay trial count across all registered experiments.

    This is the SUM of declared_budget over all registered experiments in the
    registry — the docket's "force the number to be stated" requirement. Every
    results summary MUST include this number (§3.3).

    The registry is the source of truth for cumulative replay trials. Using the
    TrialLedger's effective_n() would be WRONG because the ledger uses max()
    semantics for declared budgets (anti-gaming: largest budget wins), so
    budgets of 15, 8, 4 would report 15, not 27. The honest cumulative count
    is the SUM of declared budgets across distinct experiments.
    """
    rp = registry_path or _default_registry_path()
    records = _load_registry_raw(rp)
    # Sum declared_budget across all registered experiments.
    # Each registration record has a declared_budget; status-update records do not.
    # De-duplicate by exp_id: use the latest (highest registered_at) entry that
    # carries a declared_budget, so re-registrations are counted once at their
    # latest declared budget.
    latest: dict[str, tuple[str, int]] = {}  # eid -> (registered_at, budget)
    for r in records:
        eid = r.get("exp_id", "")
        budget = r.get("declared_budget")
        if not eid or budget is None:
            continue
        ts = r.get("registered_at", "")
        if eid not in latest or ts >= latest[eid][0]:
            latest[eid] = (ts, int(budget))
    return sum(v[1] for v in latest.values())


def results_summary_header(registry_path: Path | None = None) -> str:
    """One-line header string for inclusion in every results summary."""
    n = pooled_replay_trial_count(registry_path)
    return (
        f"Cumulative pooled replay trial count: {n} cells declared. "
        "Any promotion prereg on this tape must account for this full N."
    )
