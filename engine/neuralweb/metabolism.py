"""engine.neuralweb.metabolism — Machine registration for cortex-proposed hypotheses.

ANTI-MINING LAW (masterplan §5 W7b + §7)
-----------------------------------------
* registered_at is ALWAYS server-side (set here, never accepted from the cortex).
* Every grade is computed ONLY on data strictly after registered_at.
* Proposal budget: max 3 registrations per calendar week.  Beyond that →
  retire-one-to-file-one (an explicit retire() call required first).
* fdr_family is hard-wired to 'cortex' — the cortex cannot override it.
* All cortex hypotheses share one FDR family so their volume never raises
  the discovery bar for human programs.

TAMPER-SURFACE HONESTY
-----------------------
The governance log (data/neuralweb/governance.jsonl) records a6_llm_proposed
events at registration time, including the full pre_committed_gate and
spine_query.  A post-hoc edit to machine_registry.jsonl that changes the gate
or query is detectable by comparing the registry row against the governance
event for the same hypothesis id.

Ledger-evidence tamper detection rests on git history: machine_registry.jsonl
and governance.jsonl are both git-tracked files.  Event ids (claim_id) are
content-derived hashes (sha256 of date:hypothesis), not a cryptographic hash
chain.  Any replay protection beyond git-history auditing requires additional
infrastructure outside this module.

REGISTRATION SCHEMA (neuralweb.machine_registry.v1)
-----------------------------------------------------
Required:
  id            str   "cortex-<YYYY-MM-DD>-<slug>"
  kind          str   "cortex_hypothesis"
  registered_at str   ISO-8601 UTC (server-side — this module)
  registered_by str   "cortex" or "cortex:<run_id>"
  fdr_family    str   "cortex" (hard-wired)
  claim_shape   str   one of CLAIM_SHAPES
  hypothesis    str   natural-language claim
  spine_query   dict  machine-readable claim spec
  pre_committed_gate dict {metric, threshold, min_n, horizon_d}
  horizon_d     int   trading-day evaluation horizon
  come_back     str   ISO-8601 date (registered_at + horizon_d + 7 buffer)

Optional:
  status        str   registered | budget-rejected | invalid | passed | failed |
                      insufficient-n | retired | invalid-self-reference |
                      unresolvable-query | invalid-gate | uncomputable-metric |
                      expired-insufficient-n
  notes         str

Written by record_evaluation() on every evaluation (W6 repair — the audit found
status was the ONLY field a verdict wrote):
  evaluated_at        str    ISO-8601 UTC of the evaluation
  metric_value        float  the graded metric (None when not computable)
  evaluation_n        int    post-registration n the verdict rests on
  evaluation_attempts int    how many times this hypothesis has been evaluated
  supersedes_status   str    the status this row replaces
  evaluation_detail   dict   the evaluator's result_detail

APPEND-ONLY, LAST-WRITE-WINS
-----------------------------
A status transition APPENDS a superseding row carrying the same id; rows are
never mutated in place.  The last row for an id is its current state.  Every
reader collapses with _latest_by_id() first — see the note there for the
double-counting and un-retiring bugs that raw scanning caused.

BUDGET ENFORCEMENT (server-side)
---------------------------------
_count_week_registrations() counts rows with kind='cortex_hypothesis' AND
registered_at within the current calendar week (Mon-Sun).  BUDGET_PER_WEEK=3.
When exhausted, register_hypothesis() returns a budget-rejected row WITHOUT
writing to the registry.  retire() is required first.

TRIAL LEDGER WIRING
-------------------
On each accepted registration: log_declared_budget(1, family='cortex') is called
on the shared TrialLedger so the overfit_guard DSR haircut stays honest as
cortex volume grows.

GOVERNANCE EVENTS
-----------------
Every accepted registration appends an a6_llm_proposed event to governance.jsonl
(per the A6 Lane-(ii) doctrine in constitution.py).
Every retire() appends a tier_demotion event.
These are the only governance writes; evaluation results are written by the
evaluator, not here.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = "neuralweb.machine_registry.v1"
_REGISTRY_FILE = Path("data") / "neuralweb" / "machine_registry.jsonl"
_BUDGET_PER_WEEK = 3

CLAIM_SHAPES = frozenset({
    "lead_lag",
    "conditional_regime",
    "entry_quality",
    "sector_conditional",
})

# ---------------------------------------------------------------------------
# Status vocabulary — W6 repair (2026-08-26 experiments audit §3)
# ---------------------------------------------------------------------------
# The registry is APPEND-ONLY, LAST-WRITE-WINS: a status transition appends a
# superseding row carrying the same id, never mutates the row in place.  Every
# reader must therefore collapse by id first (_latest_by_id) — a reader that
# scans raw rows sees BOTH the superseded and the superseding state.
#
# TERMINAL — the hypothesis is concluded and must never be re-evaluated.
# come_back is cleared (None) so load_due can never pick it up again.
TERMINAL_STATUSES: frozenset[str] = frozenset({
    "passed",
    "failed",
    "retired",
    "budget-rejected",
    "invalid",
    "invalid-self-reference",
    # W2/W3 repair verdicts — the instrument refused to grade.  Terminal for the
    # registration as minted; a corrected query/gate requires a NEW registration
    # (the evaluator may never rewrite a pre-committed gate — that would be
    # origination, forbidden by Article 7).
    "unresolvable-query",
    "invalid-gate",
    "uncomputable-metric",
    # Re-arm budget exhausted (see MAX_EVALUATION_ATTEMPTS).
    "expired-insufficient-n",
})

# RE-ARMABLE — evidence has not accrued yet.  come_back is ADVANCED by one
# horizon so the hypothesis returns instead of dying silently.  Before this
# repair, come_back was written once at registration and load_due selected only
# status=='registered', so the FIRST insufficient-n verdict was terminal in
# fact while presenting as forever-accruing (audit §0.3, §3 W6).
REARMABLE_STATUSES: frozenset[str] = frozenset({"insufficient-n"})

# Statuses load_due will consider (subject to come_back <= today).
DUE_STATUSES: frozenset[str] = frozenset({"registered"}) | REARMABLE_STATUSES

# A re-arm is not unlimited: after this many evaluation attempts a hypothesis
# that still cannot reach min_n is concluded 'expired-insufficient-n' (terminal)
# rather than accruing forever.  4 attempts ≈ 4 horizons of accrual.
MAX_EVALUATION_ATTEMPTS: int = 4

# ---------------------------------------------------------------------------
# Gate metric vocabulary — the REGISTRATION contract (W3 repair)
# ---------------------------------------------------------------------------
# register_hypothesis' own comment said "metric: fixed-enum enforced by the
# evaluator", but no enum was enforced anywhere: an unrecognised metric name
# fell through to a silent hit_rate substitution.  Every hypothesis registered
# between 07-30 and 08-26 duly minted a bespoke metric name —
# q2_persistence_rate_difference, breadth_deterioration_21d_auc,
# median_credit_sensitive_lead_days — that no code computes, and each would
# have produced a verdict about a metric nobody measured.
#
# Enforcing the enum HERE is what stops the defect recurring: an ungradeable
# gate is rejected at registration instead of accruing for a horizon and then
# reporting an artifact.  The evaluator pins its computation table against this
# set (tests/test_cortex_evaluator_repairs.py).
#
# 'difference'/'ratio' metrics are measured TREATMENT vs CONTROL and require the
# spine_query to resolve a control group.
SUPPORTED_GATE_METRICS: frozenset[str] = frozenset({
    "hit_rate",
    "excess_mean",
    "hit_rate_difference",
    "excess_mean_difference",
    "hit_rate_ratio",
    "stop_out_rate",
    "stop_out_rate_difference",
})

#: Attainable range per metric — a threshold outside it is structurally
#: unpassable (H2's hit_rate <= -0.05; H3's hit_rate >= 1.01).
METRIC_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "hit_rate":                 (0.0, 1.0),
    "excess_mean":              (None, None),
    "hit_rate_difference":      (-1.0, 1.0),
    "excess_mean_difference":   (None, None),
    "hit_rate_ratio":           (0.0, None),
    "stop_out_rate":            (0.0, 1.0),
    "stop_out_rate_difference": (-1.0, 1.0),
}

_WRITE_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _registry_path(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root) / "data" / "neuralweb" / "machine_registry.jsonl"
    try:
        from lib import config as _cfg  # type: ignore[import]
        return Path(_cfg.data_dir()) / "neuralweb" / "machine_registry.jsonl"
    except Exception:  # noqa: BLE001
        return _REGISTRY_FILE


def _ledger_path(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root) / "data" / "trial_ledger.jsonl"
    try:
        from engine.trial_ledger import DEFAULT_PATH  # type: ignore[import]
        return DEFAULT_PATH
    except Exception:  # noqa: BLE001
        return Path("data") / "trial_ledger.jsonl"


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------

def _load_registry(root: Path | str | None) -> list[dict]:
    p = _registry_path(root)
    if not p.exists():
        return []
    rows = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism: could not load registry (%s)", exc)
    return rows


def _append_registry(row: dict, root: Path | str | None) -> bool:
    p = _registry_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK:
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism: append_registry failed (%s)", exc)
        return False


def _latest_by_id(rows: list[dict]) -> dict[str, dict]:
    """Collapse an append-only registry to its last-write-wins state, keyed by id.

    W6 repair.  The registry may carry several rows per id (the 2026-08-26 audit
    appended superseding 'retired' rows; every evaluation now appends one too).
    File order is write order, so the LAST row for an id is its current state.

    Every reader MUST go through this.  Scanning raw rows double-counts a
    hypothesis against the weekly budget and the open-hypothesis cap, and — the
    live bug this fixes — counted H1/H4/Q1 as OPEN ('insufficient-n' on their
    original rows) after the audit had retired them on appended rows.
    """
    latest: dict[str, dict] = {}
    for row in rows:
        rid = row.get("id")
        if rid:
            latest[str(rid)] = row
    return latest


def _cortex_rows_latest(root: Path | str | None) -> list[dict]:
    """Last-write-wins cortex_hypothesis rows, in first-registration order."""
    return [
        r for r in _latest_by_id(_load_registry(root)).values()
        if r.get("kind") == "cortex_hypothesis"
    ]


def record_evaluation(
    row_id: str,
    new_status: str,
    root: Path | str | None,
    *,
    metric_value: float | None = None,
    n: int | None = None,
    detail: dict | None = None,
    evaluated_at: str | None = None,
    today: date | None = None,
) -> bool:
    """Append a superseding registry row recording an evaluation outcome.

    W6 repair.  The previous ``_update_row_status`` wrote ONLY ``status``, and
    did so by rewriting the file in place — with no ``break``, so it stamped the
    new status onto EVERY row sharing the id.  Against the audit's appended
    retirement rows that would have silently un-retired H1/H4/Q1 on the next
    nightly.  This appends instead, which is both the declared contract
    (append-only, last-write-wins) and immune to that class of bug.

    Also writes the evaluation provenance the audit found missing:
    ``evaluated_at``, ``metric_value``, ``n``, ``evaluation_attempts``.

    come_back handling (the silent-terminal fix):
      * TERMINAL status      → come_back = None (never returns)
      * RE-ARMABLE status    → come_back advanced by horizon_d + 7 so the
                               hypothesis is re-evaluated once more evidence has
                               accrued, until MAX_EVALUATION_ATTEMPTS is spent,
                               at which point it concludes 'expired-insufficient-n'.

    Returns True if a superseding row was appended, False if the id is unknown.
    """
    prior = load_by_id(row_id, root)
    if prior is None:
        log.warning("metabolism: record_evaluation — id %r not found in registry", row_id)
        return False

    if today is None:
        today = datetime.now(timezone.utc).date()
    stamped = evaluated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    attempts = int(prior.get("evaluation_attempts") or 0) + 1

    status = new_status
    if status in REARMABLE_STATUSES and attempts >= MAX_EVALUATION_ATTEMPTS:
        log.info(
            "metabolism: %s exhausted its re-arm budget (%d attempts) — "
            "concluding 'expired-insufficient-n'",
            row_id, attempts,
        )
        status = "expired-insufficient-n"

    row = dict(prior)
    row["status"] = status
    row["evaluated_at"] = stamped
    row["metric_value"] = metric_value
    row["evaluation_n"] = n
    row["evaluation_attempts"] = attempts
    row["supersedes_status"] = prior.get("status")
    if detail is not None:
        row["evaluation_detail"] = detail

    if status in REARMABLE_STATUSES:
        horizon_d = int(row.get("horizon_d") or 21)
        row["come_back"] = (today + timedelta(days=horizon_d + 7)).isoformat()
    else:
        # Terminal — nothing may bring it back.
        row["come_back"] = None

    ok = _append_registry(row, root)
    if ok:
        log.info(
            "metabolism: %s → %s (attempt %d, come_back=%s)",
            row_id, status, attempts, row["come_back"],
        )
    return ok


def _update_row_status(row_id: str, new_status: str, root: Path | str | None) -> bool:
    """Back-compatible status transition.  Delegates to record_evaluation().

    Retained because retire() and older callers use this two-positional-arg
    shape.  Callers that HAVE a metric/n should call record_evaluation directly
    so the provenance is not lost.
    """
    return record_evaluation(row_id, new_status, root)


# ---------------------------------------------------------------------------
# Budget enforcement (server-side)
# ---------------------------------------------------------------------------

def _iso_week_key(dt: datetime) -> str:
    """Return 'YYYY-WNN' ISO week key for dt."""
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def _count_week_registrations(root: Path | str | None, now: datetime) -> int:
    """Count accepted registrations in the current calendar week."""
    week_key = _iso_week_key(now)
    count = 0
    # W6: collapse last-write-wins first.  A hypothesis registered this week now
    # gains a superseding row on every evaluation; counting raw rows would let
    # re-evaluations eat the 3-per-week registration budget.
    for row in _cortex_rows_latest(root):
        if row.get("status") in ("budget-rejected", "invalid", "retired"):
            continue
        rat = row.get("registered_at")
        if not rat:
            continue
        try:
            dt = datetime.fromisoformat(str(rat))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if _iso_week_key(dt) == week_key:
                count += 1
        except Exception:  # noqa: BLE001
            pass
    return count


def _count_open_hypotheses(root: Path | str | None) -> int:
    """Count hypotheses whose CURRENT status is open (not terminal).

    W6: last-write-wins collapse.  Counting raw rows treated H1/H4/Q1 as open on
    their original 'insufficient-n' rows even though the 2026-08-26 audit had
    appended 'retired' rows for all three.
    """
    open_statuses = {"registered", "accruing", "insufficient-n"}
    return sum(
        1 for r in _cortex_rows_latest(root)
        if r.get("status") in open_statuses
    )


# ---------------------------------------------------------------------------
# ID / slug helpers
# ---------------------------------------------------------------------------

def _make_id(hypothesis: str, now: datetime) -> str:
    """Generate a stable cortex-<date>-<slug> id."""
    today = now.strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", hypothesis.lower()[:40]).strip("-")
    h = hashlib.sha256(f"{today}:{hypothesis}".encode()).hexdigest()[:6]
    return f"cortex-{today}-{slug}-{h}"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

_REQUIRED_GATE_KEYS = {"metric", "threshold", "min_n", "horizon_d"}

# Server-side floor for pre_committed_gate.min_n.
# The cortex cannot submit a min_n below this value.  Any submitted value is
# silently clamped upward to this floor before writing to the registry.  The
# clamped_from field is added to pre_committed_gate when clamping occurs so
# the audit trail is honest.
_HOUSE_MIN_N: int = 25

# Self-referencing spine_query values — defense in depth (see Article 1).
# Registration is rejected if spine_query.family, .engine, or .ledger
# references cortex_attention.  The evaluator enforces the same rule at
# grading time for any pre-existing rows that bypassed this check.
_SELF_REF_FORBIDDEN: frozenset[str] = frozenset({
    "cortex_attention",
    "reflex.cortex_attention",
})


def _validate_hypothesis(h: dict) -> list[str]:
    """Return list of validation errors (empty = valid).

    Defense-in-depth checks enforced here:
    * Article 1 — spine_query must not reference cortex_attention in any
      field (family, engine, ledger).  The cortex may never be its own
      evidence.  The evaluator enforces the same rule at grading time for
      pre-existing registry rows that bypassed this check.
    * min_n floor — checked for type only; the _HOUSE_MIN_N clamp is applied
      in register_hypothesis AFTER validation so the registry always stores
      the clamped value.
    """
    errors: list[str] = []

    if not h.get("hypothesis"):
        errors.append("hypothesis: missing or empty")

    cs = h.get("claim_shape")
    if cs not in CLAIM_SHAPES:
        errors.append(f"claim_shape: must be one of {sorted(CLAIM_SHAPES)}, got {cs!r}")

    gate = h.get("pre_committed_gate")
    if not gate or not isinstance(gate, dict):
        errors.append("pre_committed_gate: missing or not a dict")
    else:
        missing = _REQUIRED_GATE_KEYS - set(gate.keys())
        if missing:
            errors.append(f"pre_committed_gate: missing required keys {sorted(missing)}")
        try:
            int(gate.get("min_n", 0))
        except (TypeError, ValueError):
            errors.append("pre_committed_gate.min_n: must be an integer")
        try:
            int(gate.get("horizon_d", 0))
        except (TypeError, ValueError):
            errors.append("pre_committed_gate.horizon_d: must be an integer")

        # W3 — the metric enum this module always claimed was enforced.
        metric = str(gate.get("metric", "") or "")
        if metric not in SUPPORTED_GATE_METRICS:
            errors.append(
                f"pre_committed_gate.metric: {metric!r} is not gradeable; "
                f"must be one of {sorted(SUPPORTED_GATE_METRICS)}"
            )
        else:
            # A threshold outside the metric's attainable range is structurally
            # unpassable — reject it at registration rather than letting it
            # accrue for a horizon and report 'failed' about the instrument.
            lo, hi = METRIC_BOUNDS[metric]
            try:
                threshold = float(gate.get("threshold"))
            except (TypeError, ValueError):
                errors.append("pre_committed_gate.threshold: must be numeric")
            else:
                if (lo is not None and threshold < lo) or (hi is not None and threshold > hi):
                    errors.append(
                        f"pre_committed_gate.threshold: {threshold} is outside "
                        f"the attainable range of {metric} [{lo}, {hi}] — "
                        f"structurally unpassable.  A threshold minted as a "
                        f"difference or ratio needs a contrast metric."
                    )

    sq = h.get("spine_query")
    if not sq or not isinstance(sq, dict):
        errors.append("spine_query: missing or not a dict")
    else:
        # Article 1 — self-reference guard.  spine_query must not reference
        # cortex_attention in any field so the cortex cannot grade itself.
        _sq_values = {
            str(sq.get("family", "")),
            str(sq.get("engine", "")),
            str(sq.get("ledger", "")),
        }
        _self_family = str(sq.get("family", "")).startswith("reflex.cortex_attention")
        if _sq_values & _SELF_REF_FORBIDDEN or _self_family:
            errors.append(
                "spine_query: references cortex_attention — Article 1 forbids "
                "self-grading (the cortex may never be its own evidence)"
            )

    hd = h.get("horizon_d")
    try:
        if hd is None or int(hd) <= 0:
            errors.append("horizon_d: must be a positive integer")
    except (TypeError, ValueError):
        errors.append("horizon_d: must be an integer")

    return errors


# ---------------------------------------------------------------------------
# Trial ledger wiring
# ---------------------------------------------------------------------------

def _log_to_trial_ledger(row_id: str, root: Path | str | None) -> None:
    """Log one declared trial to the trial ledger for the 'cortex' family."""
    try:
        from engine.trial_ledger import TrialLedger  # type: ignore[import]
        led = TrialLedger(path=_ledger_path(root))
        led.log_declared_budget(1, family="cortex",
                                reason=f"cortex hypothesis registration: {row_id}")
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism: trial ledger update failed for %s (%s)", row_id, exc)


# ---------------------------------------------------------------------------
# Governance event wiring
# ---------------------------------------------------------------------------

def _emit_governance(
    event_type: str,
    row_id: str,
    note: str,
    root: Path | str | None,
    evidence: dict | None = None,
) -> None:
    """Append a governance event.  Fail-open."""
    try:
        from engine.neuralweb.governance import append_event  # type: ignore[import]
        append_event(
            event_type,
            target=f"cortex_hypothesis:{row_id}",
            article=6,
            authored_by="metabolism",
            note=note,
            evidence=evidence,
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism: governance event failed for %s (%s)", row_id, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_hypothesis(
    h: dict[str, Any],
    root: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Consume an inbox row and register it in the machine registry.

    Parameters
    ----------
    h : dict
        Must carry: hypothesis (str), claim_shape, spine_query, pre_committed_gate,
        horizon_d, and optionally registered_by.
        Must NOT carry registered_at — this is set server-side here.

    Returns
    -------
    dict with keys: id, status, registered_at (or budget_state), reason.
    Status values:
      "registered"       — accepted and written
      "budget-rejected"  — weekly budget exhausted (retire first)
      "invalid"          — schema validation failed
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Step 1: schema validation
    errors = _validate_hypothesis(h)
    if errors:
        row_id = _make_id(h.get("hypothesis", "unknown"), now)
        log.warning("metabolism: register_hypothesis invalid (%s): %s", row_id, errors)
        invalid_row: dict[str, Any] = {
            "schema": _SCHEMA,
            "id": row_id,
            "kind": "cortex_hypothesis",
            "status": "invalid",
            "registered_at": None,
            "registered_by": h.get("registered_by", "cortex"),
            "fdr_family": "cortex",
            "claim_shape": h.get("claim_shape"),
            "hypothesis": h.get("hypothesis", ""),
            "spine_query": h.get("spine_query"),
            "pre_committed_gate": h.get("pre_committed_gate"),
            "horizon_d": h.get("horizon_d"),
            "come_back": None,
            "reason": "; ".join(errors),
        }
        _append_registry(invalid_row, root)
        return {"id": row_id, "status": "invalid", "reason": "; ".join(errors)}

    row_id = _make_id(h["hypothesis"], now)

    # Step 2: budget enforcement (server-side)
    week_count = _count_week_registrations(root, now)
    if week_count >= _BUDGET_PER_WEEK:
        log.warning(
            "metabolism: BUDGET EXHAUSTED for week %s (%d/%d) — retire first",
            _iso_week_key(now), week_count, _BUDGET_PER_WEEK,
        )
        budget_row: dict[str, Any] = {
            "schema": _SCHEMA,
            "id": row_id,
            "kind": "cortex_hypothesis",
            "status": "budget-rejected",
            "registered_at": None,
            "registered_by": h.get("registered_by", "cortex"),
            "fdr_family": "cortex",
            "claim_shape": h.get("claim_shape"),
            "hypothesis": h.get("hypothesis", ""),
            "spine_query": h.get("spine_query"),
            "pre_committed_gate": h.get("pre_committed_gate"),
            "horizon_d": h.get("horizon_d"),
            "come_back": None,
            "reason": (
                f"budget-rejected: week {_iso_week_key(now)} already has "
                f"{week_count}/{_BUDGET_PER_WEEK} registrations. "
                "Call retire() on an existing hypothesis first."
            ),
            "budget_state": {
                "week": _iso_week_key(now),
                "used": week_count,
                "limit": _BUDGET_PER_WEEK,
            },
        }
        _append_registry(budget_row, root)
        return {
            "id": row_id,
            "status": "budget-rejected",
            "reason": budget_row["reason"],
            "budget_state": budget_row["budget_state"],
        }

    # Step 3: build the registration row
    registered_at = now.isoformat(timespec="seconds")
    horizon_d = int(h["horizon_d"])
    come_back_dt = now.date() + timedelta(days=horizon_d + 7)

    # Server-side min_n clamp — the cortex cannot set min_n below _HOUSE_MIN_N=25.
    # Any submitted value is clamped upward; the clamped_from field records the
    # original submission for auditability.  Other gate knobs:
    #   - threshold: direction-agnostic numeric; no clamp (either direction is valid).
    #   - horizon_d: validated as positive int; no additional clamp needed.
    #   - direction_expected: ±1 or absent; not clampable (semantic, not leniency).
    #   - metric: fixed-enum enforced by the evaluator; not clampable here.
    gate = dict(h["pre_committed_gate"])  # copy so we don't mutate caller's dict
    submitted_min_n = int(gate.get("min_n", 0))
    if submitted_min_n < _HOUSE_MIN_N:
        gate["min_n"] = _HOUSE_MIN_N
        gate["clamped_from"] = submitted_min_n
        log.info(
            "metabolism: min_n clamped from %d → %d (house floor) for %s",
            submitted_min_n, _HOUSE_MIN_N, row_id,
        )

    reg_row: dict[str, Any] = {
        "schema": _SCHEMA,
        "id": row_id,
        "kind": "cortex_hypothesis",
        "status": "registered",
        "registered_at": registered_at,      # SERVER-SIDE: never accepted from cortex
        "registered_by": h.get("registered_by", "cortex"),
        "fdr_family": "cortex",              # HARD-WIRED
        "claim_shape": h["claim_shape"],
        "hypothesis": h["hypothesis"],
        "spine_query": h["spine_query"],
        "pre_committed_gate": gate,
        "horizon_d": horizon_d,
        "come_back": come_back_dt.isoformat(),
        "is_context_only": True,
    }

    # Step 4: write to registry
    written = _append_registry(reg_row, root)
    if not written:
        return {
            "id": row_id,
            "status": "invalid",
            "reason": "registry write failed",
        }

    # Step 5: declare in trial ledger
    _log_to_trial_ledger(row_id, root)

    # Step 6: governance event (A6 lane-ii — LLM-proposed).
    # Record the pre-committed gate, spine_query, claim_shape, and horizon_d
    # as evidence so that any post-hoc edit to machine_registry.jsonl is
    # detectable against this ledger entry.  Exploitation still requires
    # filesystem write access to machine_registry.jsonl (which is git-tracked),
    # but this closes the "visible in the ledger" gap named in the spec.
    _emit_governance(
        "a6_llm_proposed",
        row_id,
        f"cortex hypothesis registered: {h['hypothesis'][:120]}",
        root,
        evidence={
            "pre_committed_gate": gate,   # clamped gate (honest audit trail)
            "spine_query": h["spine_query"],
            "claim_shape": h["claim_shape"],
            "horizon_d": horizon_d,
        },
    )

    log.info(
        "metabolism: registered %s (shape=%s, horizon=%dd, come_back=%s)",
        row_id, h["claim_shape"], horizon_d, come_back_dt,
    )
    return {
        "id": row_id,
        "status": "registered",
        "registered_at": registered_at,
        "come_back": come_back_dt.isoformat(),
    }


def retire(
    hypothesis_id: str,
    reason: str,
    root: Path | str | None = None,
) -> bool:
    """Retire an existing hypothesis (required for retire-one-to-file-one).

    Updates status to 'retired' in the registry and appends a governance event.
    Returns True on success, False if not found.
    """
    ok = _update_row_status(hypothesis_id, "retired", root)
    if ok:
        _emit_governance(
            "tier_demotion",
            hypothesis_id,
            f"retired: {reason[:200]}",
            root,
        )
        log.info("metabolism: retired %s (%s)", hypothesis_id, reason[:80])
    else:
        log.warning("metabolism: retire — id %r not found in registry", hypothesis_id)
    return ok


def load_due(
    root: Path | str | None = None,
    today: date | None = None,
) -> list[dict]:
    """Return hypotheses whose come_back date <= today and whose CURRENT status is due.

    W6 repair, two parts:

    * Rows are collapsed last-write-wins first.  Scanning raw rows returned
      superseded states — after the 2026-08-26 audit appended 'retired' rows for
      H1/H4/Q1, their original rows were still present and still matched.
    * DUE_STATUSES includes 'insufficient-n', not just 'registered'.  Previously
      an insufficient-n verdict was terminal in fact (come_back never advanced,
      load_due never selected it) while the panel presented it as accruing.
      record_evaluation() advances come_back on those rows; this selects them.
    """
    if today is None:
        today = datetime.now(timezone.utc).date()
    due = []
    for row in _cortex_rows_latest(root):
        if row.get("status") not in DUE_STATUSES:
            continue
        cb = row.get("come_back")
        if not cb:
            continue
        try:
            cb_date = date.fromisoformat(str(cb)[:10])
            if cb_date <= today:
                due.append(row)
        except Exception:  # noqa: BLE001
            pass
    return due


def load_by_id(
    hypothesis_id: str,
    root: Path | str | None = None,
) -> dict | None:
    """Return the most recent registry row for hypothesis_id, or None (last-write-wins)."""
    return _latest_by_id(_load_registry(root)).get(str(hypothesis_id))


def inbox_to_registered(
    inbox_path: Path,
    root: Path | str | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Read hypothesis_inbox.jsonl and register all inbox-not-registered rows.

    Updates inbox rows with status transitions inline (status field).
    Returns list of registration results.
    """
    if not inbox_path.exists():
        return []

    results = []
    raw_lines = inbox_path.read_text(encoding="utf-8").splitlines()
    updated_lines = []

    for line in raw_lines:
        line_stripped = line.strip()
        if not line_stripped:
            updated_lines.append(line)
            continue
        try:
            row = json.loads(line_stripped)
        except Exception:  # noqa: BLE001
            updated_lines.append(line)
            continue

        if row.get("status") != "inbox-not-registered":
            updated_lines.append(line)
            continue

        # Attempt registration
        result = register_hypothesis(row, root=root, now=now)
        new_status = result.get("status", "invalid")
        row["status"] = new_status
        row["registration_result"] = result
        updated_lines.append(json.dumps(row, default=str))
        results.append(result)

    # Rewrite inbox with status updates (audit trail)
    try:
        inbox_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism: could not rewrite inbox (%s)", exc)

    return results
