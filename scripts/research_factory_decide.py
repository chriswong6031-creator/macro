"""scripts/research_factory_decide.py — Human decision recorder (W5, RF-5/RF-9/RF-10/RF-12).

The ONLY path into human-gate states (paper, deferred, rejected, scoped_build).

Enforces, in order:
  (a) state.py transition with human actor (actor law, mandatory fields)
  (b) governance event research_factory_gate with article:null via
      governance.append_event (RF-12)
  (c) for paper/deferred: experiments-seed entry appended to
      data/experiments/registry_seed.json + track skeleton at
      data/research_factory/track/<candidate_id>.json (RF-9)
  (d) candidate status update via ledger helpers

Refuses:
  - Double decisions (candidate already in terminal state or already paper)
  - Actor law violations (script actors into human-gate states)
  - Missing required per-decision args

Usage
-----
  python scripts/research_factory_decide.py \\
    --candidate rf-20260706-oracle-washout_flow-001 \\
    --decision paper \\
    --actor fable \\
    --actor-ref "session-20260706" \\
    --expected-half-life-d 250

  python scripts/research_factory_decide.py \\
    --candidate rf-20260706-oracle-001 \\
    --decision deferred \\
    --actor operator \\
    --actor-ref "PR-1234" \\
    --come-back-on 2027-01-01

  python scripts/research_factory_decide.py \\
    --candidate rf-20260706-oracle-001 \\
    --decision rejected \\
    --actor fable \\
    --actor-ref "session-20260706" \\
    --kill-class underpowered_accruing \\
    --n-at-kill 12

  python scripts/research_factory_decide.py \\
    --candidate rf-20260706-oracle-001 \\
    --decision scoped_build \\
    --actor fable \\
    --actor-ref "session-20260706" \\
    --program-doc research/ORACLE_REVERSION_BY_FABLE.md

Charter: research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md §6 W5,
rulings RF-5, RF-9, RF-10, RF-12.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.research_factory import ledger as rf_ledger
from engine.research_factory.state import (
    transition as state_transition,
    IllegalTransition,
    HUMAN_ACTORS,
    SCRIPT_ACTORS,
)
from engine.research_factory.schema import validate_transition

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_RF_DIR = ROOT / "data" / "research_factory"
DEFAULT_EXPERIMENTS_SEED = ROOT / "data" / "experiments" / "registry_seed.json"
DEFAULT_REQUEUE_PATH = ROOT / "data" / "research_factory" / "requeue.jsonl"
DEFAULT_REGIME_PATH = ROOT / "data" / "regime" / "latest.json"

# RF-9: per-domain expected_half_life_d default prior
_DOMAIN_HALF_LIFE_DEFAULTS: dict[str, int] = {
    "oracle": 250,
    "neuralweb": 250,
    "entry": 250,
    "factor": 250,
    "macro": 250,
    "options": 250,
    "china": 250,
    "us_stocks": 250,
}
_DEFAULT_HALF_LIFE = 250  # fallback for any domain

# RF-10: valid kill classes
VALID_KILL_CLASSES = frozenset({
    "falsified",
    "underpowered_accruing",
    "regime_change_suspect",
    "duplicate",
    "decayed",
    "budget_withdrawn",
})

# States that are already terminal (refuse double-decisions)
_TERMINAL_STATES = frozenset({
    "schema_rejected", "deduped", "numeric_rejected",
    "scoped_build", "rejected", "retired",
})
# paper is not terminal in the state machine (can go to promote_eligible/human_review/retired)
# but we refuse a second paper decision for a currently-paper candidate coming from human_review
_ALREADY_DECIDED_STATES = _TERMINAL_STATES | frozenset({"paper"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict | None:
    """Load a JSON file absent-safely."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_candidates(rf_dir: Path) -> list[dict]:
    return rf_ledger.load_jsonl(rf_dir / "candidates.jsonl")


def _load_transitions(rf_dir: Path) -> list[dict]:
    return rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")


def _resolve_candidate_status(
    candidate_id: str,
    candidates: list[dict],
    transitions: list[dict],
) -> tuple[dict | None, str | None]:
    """Return (candidate_dict, current_status).

    Status is the last transition destination (ground truth).
    Returns (None, None) if candidate_id is not found.
    """
    # Find the candidate row
    cand: dict | None = None
    for row in candidates:
        if row.get("candidate_id") == candidate_id:
            cand = dict(row)
            break
    if cand is None:
        return None, None

    # Override status from transitions (ground truth)
    last_to: str | None = cand.get("status")
    for t in transitions:
        if t.get("candidate_id") == candidate_id:
            last_to = t.get("to", last_to)

    return cand, last_to


def _load_regime_stamp(regime_path: Path) -> dict:
    """Load regime/latest.json absent-safely for regime-at-entry stamp (RF-9)."""
    data = _load_json(regime_path)
    if not data or not isinstance(data, dict):
        return {"regime": "unknown", "source": "absent"}

    # Extract relevant fields
    stamp: dict[str, Any] = {}
    stamp["regime"] = data.get("label") or data.get("quad") or "unknown"
    stamp["quad"] = data.get("quad")
    stamp["asof"] = data.get("asof") or data.get("date")
    # VIX percentile if present (from screen artifacts or regime)
    vix_pctile = data.get("vix_pctile")
    if vix_pctile is not None:
        stamp["vix_pctile"] = vix_pctile
    stamp["source"] = "data/regime/latest.json"
    return stamp


def _load_screen_regime_tags(candidate: dict) -> dict:
    """Try to extract regime tags from the candidate's screen artifact."""
    arts = candidate.get("artifacts") or {}
    if not isinstance(arts, dict):
        return {}
    tags: dict[str, Any] = {}
    for key in ("risk_on", "risk_off", "vix_pctile", "regime", "launched_hot"):
        v = arts.get(key)
        if v is not None:
            tags[key] = v
    # Check nested reversion artifact
    nested = arts.get("artifact") or {}
    if isinstance(nested, dict):
        for key in ("risk_on", "risk_off", "vix_pctile"):
            v = nested.get(key)
            if v is not None:
                tags[key] = v
    return tags


def _build_regime_at_entry(candidate: dict, regime_path: Path) -> dict:
    """Build regime_at_entry stamp for paper transitions (RF-9)."""
    base = _load_regime_stamp(regime_path)
    # Merge in per-candidate screen artifact regime tags
    screen_tags = _load_screen_regime_tags(candidate)
    base.update(screen_tags)
    return base


# ---------------------------------------------------------------------------
# Experiments seed helpers (RF-9)
# ---------------------------------------------------------------------------


def _load_seed(seed_path: Path) -> dict:
    """Load registry_seed.json absent-safely."""
    if not seed_path.exists():
        return {"schema": "experiments_registry_seed.v1", "experiments": []}
    try:
        return json.loads(seed_path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": "experiments_registry_seed.v1", "experiments": []}


def _write_seed(seed_path: Path, seed: dict) -> None:
    """Write registry_seed.json atomically-ish."""
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_text(
        json.dumps(seed, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def _make_seed_entry(
    candidate: dict,
    decision: str,
    expected_half_life_d: int,
    defaulted_half_life: bool,
    come_back_on: str | None,
    regime_at_entry: dict,
) -> dict:
    """Build a registry_seed.json experiment entry for paper/deferred.

    Matches the real registry_seed.json key set (studied from live entries).
    RF-9: kind='track_record' for paper, appropriate kind for deferred.
    hook='track_record' for paper (admin overlay reads the track_json).
    track_json points at data/research_factory/track/<candidate_id>.json.
    """
    cid = candidate.get("candidate_id", "?")
    domain = candidate.get("domain") or "?"
    ctype = candidate.get("candidate_type") or "?"
    hyp = (candidate.get("hypothesis") or "")[:120]
    mech = (candidate.get("mechanism") or "")[:200]
    created_at = (candidate.get("created_at") or "")[:10]

    # RF-9: kind
    if decision == "paper":
        kind = "track_record"
        hook = "track_record"
    else:
        # deferred: appropriate kind based on domain/type
        kind = "data_collection"
        hook = "track_record"

    track_json_rel = f"data/research_factory/track/{cid}.json"
    storage_rel = f"data/research_factory/candidates.jsonl"

    # Maturation text
    ep = candidate.get("evaluation_plan") or {}
    primary_metric = ep.get("primary_metric") or "domain gate metric"
    horizon_d = ep.get("horizon_d") or 21
    min_n = ep.get("min_n") or 25
    maturation = (
        f"n>={min_n} matured obs at {horizon_d}d horizon; "
        f"primary_metric={primary_metric}; "
        f"expected_half_life_d={expected_half_life_d} "
        f"({'domain prior' if defaulted_half_life else 'operator-set'})"
    )

    # Next step
    if decision == "paper":
        next_step = (
            f"Monitor {primary_metric} against domain gate; "
            f"regime_at_entry={regime_at_entry.get('regime', 'unknown')}; "
            f"return at come_back_on for decay review."
        )
        status = "accruing"
    else:
        next_step = (
            f"Data collection accrual; revisit on {come_back_on} for "
            f"re-registration decision."
        )
        status = "collecting"

    half_life_str = (
        f"expected_half_life_d={expected_half_life_d} "
        f"({'domain default prior' if defaulted_half_life else 'operator-declared'})"
    )

    entry: dict = {
        "id": f"rf-{cid}",
        "name": f"Research Factory: {ctype}/{domain} — {hyp[:60]}",
        "kind": kind,
        "priority": "medium",
        "cadence": "nightly",
        "what": (
            f"[Research Factory paper accrual] {hyp}. "
            f"Mechanism: {mech}. "
            f"{half_life_str}. "
            f"regime_at_entry={json.dumps(regime_at_entry)}."
        ),
        "source": f"research_factory/{ctype}/{domain}",
        "storage": storage_rel,
        "track_json": track_json_rel,
        "hook": hook,
        "started": created_at,
        "come_back_on": come_back_on,
        "come_back_note": (
            f"RF-9 paper accrual clock; "
            f"expected_half_life_d={expected_half_life_d}; "
            f"regime_at_entry={regime_at_entry.get('regime','unknown')}"
        ),
        "maturation": maturation,
        "status": status,
        "state": f"paper accrual started; regime_at_entry={regime_at_entry.get('regime','unknown')}",
        "next_step": next_step,
        "phase_hint": f"research-factory · {domain} · {ctype}",
        # RF-9 extra fields
        "rf_candidate_id": cid,
        "rf_decision": decision,
        "rf_expected_half_life_d": expected_half_life_d,
        "rf_defaulted_half_life": defaulted_half_life,
        "rf_regime_at_entry": regime_at_entry,
    }
    return entry


def _make_track_skeleton(
    candidate: dict,
    decision: str,
    expected_half_life_d: int,
    regime_at_entry: dict,
) -> dict:
    """Build the per-candidate track skeleton at data/research_factory/track/<id>.json.

    Structure matches what _refresh_track_record() in experiments_registry.py
    expects to read (verdict + horizons).
    """
    cid = candidate.get("candidate_id", "?")
    ep = candidate.get("evaluation_plan") or {}
    horizon_d = ep.get("horizon_d") or 21

    return {
        "schema": "research_factory.track.v1",
        "authority": "display_only",
        "candidate_id": cid,
        "decision": decision,
        "expected_half_life_d": expected_half_life_d,
        "regime_at_entry": regime_at_entry,
        "verdict": "accruing",
        "horizons": {
            str(horizon_d): {
                "n_matured": 0,
                "metric_value": None,
                "gate_threshold": None,
                "gate_pass": None,
                "note": "accruing — no matured observations yet",
            }
        },
        "created_at": _now_iso(),
        "note": "display-only accrual skeleton; updated by the paper monitor (W6)",
    }


def _append_seed_entry(
    seed_path: Path,
    entry: dict,
    dry_run: bool = False,
) -> None:
    """Append an experiment seed entry (or log in dry-run)."""
    if dry_run:
        print(f"  [DRY-RUN] Would append seed entry id={entry.get('id')}")
        return

    seed = _load_seed(seed_path)
    experiments = seed.get("experiments") or []

    # Idempotency: skip if id already present
    existing_ids = {e.get("id") for e in experiments}
    eid = entry.get("id")
    if eid in existing_ids:
        print(f"  [SKIP] Seed entry id={eid} already present — not duplicating")
        return

    experiments.append(entry)
    seed["experiments"] = experiments
    _write_seed(seed_path, seed)
    print(f"  Appended seed entry id={eid} to {seed_path}")


def _write_track_file(
    rf_dir: Path,
    candidate_id: str,
    skeleton: dict,
    dry_run: bool = False,
) -> str:
    """Write the track skeleton JSON, return the relative path."""
    track_dir = rf_dir / "track"
    track_path = track_dir / f"{candidate_id}.json"
    rel_path = f"data/research_factory/track/{candidate_id}.json"

    if dry_run:
        print(f"  [DRY-RUN] Would write track skeleton to {track_path}")
        return rel_path

    track_dir.mkdir(parents=True, exist_ok=True)
    track_path.write_text(
        json.dumps(skeleton, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"  Wrote track skeleton: {track_path}")
    return rel_path


# ---------------------------------------------------------------------------
# Requeue pointer (RF-10)
# ---------------------------------------------------------------------------


def _write_requeue_pointer(
    requeue_path: Path,
    candidate: dict,
    kill_class: str,
    n_at_kill: int,
    dry_run: bool = False,
) -> None:
    """Write a requeue pointer for underpowered_accruing / regime_change_suspect kills.

    Mirrors data/oracle/reversion_kill_requeue.jsonl pattern (RF-10).
    Requeue at 2× n_at_kill.
    """
    cid = candidate.get("candidate_id", "?")
    requeue_n = max(n_at_kill * 2, 1)
    row: dict = {
        "authority": "display_only",
        "schema": "research_factory.requeue.v1",
        "candidate_id": cid,
        "candidate_type": candidate.get("candidate_type"),
        "domain": candidate.get("domain"),
        "kill_class": kill_class,
        "n_at_kill": n_at_kill,
        "requeue_at_n": requeue_n,
        "created_at": _now_iso(),
        "note": (
            f"RF-10 requeue pointer: re-arm is an explicit human decision "
            f"(never automatic); each re-screen is a new counted trial. "
            f"Suggested requeue at n>={requeue_n} (2x n_at_kill={n_at_kill})."
        ),
    }

    if dry_run:
        print(f"  [DRY-RUN] Would write requeue pointer for {cid} to {requeue_path}")
        return

    requeue_path.parent.mkdir(parents=True, exist_ok=True)
    with requeue_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    print(f"  Wrote requeue pointer for {cid} (kill_class={kill_class}) to {requeue_path}")


# ---------------------------------------------------------------------------
# Governance event (RF-12)
# ---------------------------------------------------------------------------


def _append_governance_event(
    candidate_id: str,
    decision: str,
    actor: str,
    actor_ref: str,
    root: Path | None,
    dry_run: bool = False,
) -> None:
    """Append governance event with event_type=research_factory_gate, article=null (RF-12)."""
    if dry_run:
        print(f"  [DRY-RUN] Would append governance event research_factory_gate "
              f"for {candidate_id} decision={decision}")
        return

    try:
        from engine.neuralweb.governance import append_event
        ok = append_event(
            event_type="research_factory_gate",
            target=f"research_factory/{candidate_id}",
            article=None,   # RF-12: always null
            authored_by=f"{actor}/{actor_ref}",
            evidence={
                "candidate_id": candidate_id,
                "decision": decision,
                "actor": actor,
                "actor_ref": actor_ref,
            },
            note=f"RF-12 human gate: decision={decision} actor={actor} ref={actor_ref}",
            root=root,
        )
        if ok:
            print(f"  Appended governance event research_factory_gate for {candidate_id}")
        else:
            print(f"  [WARN] governance.append_event returned False for {candidate_id}")
    except Exception as exc:
        print(f"  [WARN] governance event failed (non-fatal): {exc}")


# ---------------------------------------------------------------------------
# Transition writer
# ---------------------------------------------------------------------------


def _write_transition(
    rf_dir: Path,
    candidate_id: str,
    from_state: str,
    to_state: str,
    actor: str,
    actor_ref: str,
    decision: str,
    extra_fields: dict,
    candidate: dict,
    dry_run: bool = False,
) -> dict:
    """Build, validate, and write a transition row.

    Returns the transition row dict.
    Raises IllegalTransition or ValueError on any violation.
    """
    as_of = _now_iso()
    transition_row: dict = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "from": from_state,
        "to": to_state,
        "reason_code": f"human_decision_{decision}",
        "reason_text": f"Human decision: {decision} by {actor} ({actor_ref})",
        "actor": actor,
        "actor_ref": actor_ref,
        "as_of": as_of,
        "artifact_refs": [],
        "kill_evidence": None,
    }
    transition_row.update(extra_fields)

    # state.py validation (raises IllegalTransition on violation)
    state_transition(
        from_state=from_state,
        to_state=to_state,
        actor=actor,
        transition_row=transition_row,
        candidate=candidate,
    )

    # schema validation (belt-and-suspenders)
    errs = validate_transition(transition_row)
    if errs:
        raise ValueError(f"Transition schema violations: {errs}")

    if dry_run:
        print(f"  [DRY-RUN] Would write transition {from_state} -> {to_state} for {candidate_id}")
        return transition_row

    rf_ledger.append_row(
        rf_dir / "transitions.jsonl",
        transition_row,
        validate_fn=validate_transition,
    )
    print(f"  Wrote transition {from_state} -> {to_state} for {candidate_id}")
    return transition_row


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--candidate", required=True,
        help="Candidate ID (e.g. rf-20260706-oracle-001)",
    )
    ap.add_argument(
        "--decision", required=True,
        choices=["paper", "deferred", "rejected", "scoped_build"],
        help="Human decision",
    )
    ap.add_argument(
        "--actor", required=True,
        choices=["fable", "operator"],
        help="Human actor class (RF-5: only fable|operator may make human-gate decisions)",
    )
    ap.add_argument(
        "--actor-ref", required=True,
        help="Session or PR reference (RF-5: required for human actors)",
    )

    # paper-specific
    ap.add_argument(
        "--expected-half-life-d", type=int, default=None,
        help=(
            "For paper: expected half-life in trading days. "
            f"Default prior: {_DEFAULT_HALF_LIFE}d (RF-9). "
            "If omitted, the domain prior is used and defaulted=true is recorded."
        ),
    )

    # deferred-specific
    ap.add_argument(
        "--come-back-on", default=None,
        help="For deferred: YYYY-MM-DD come-back date (required for deferred)",
    )

    # rejected/retired-specific
    ap.add_argument(
        "--kill-class", default=None,
        choices=sorted(VALID_KILL_CLASSES),
        help="For rejected/retired: kill class (RF-10)",
    )
    ap.add_argument(
        "--n-at-kill", type=int, default=0,
        help="For rejected/retired: n observations at kill (RF-10)",
    )
    ap.add_argument(
        "--mde-at-n", type=float, default=None,
        help="For rejected/retired: minimum detectable effect at n (RF-10, optional)",
    )

    # scoped_build-specific
    ap.add_argument(
        "--program-doc", default=None,
        help=(
            "For scoped_build: path to program doc "
            "(e.g. research/ORACLE_REVERSION_BY_FABLE.md). "
            "File must be provided (RF-4)."
        ),
    )

    # paths
    ap.add_argument(
        "--rf-dir", type=Path, default=None,
        help="Override data/research_factory/ dir",
    )
    ap.add_argument(
        "--experiments-seed", type=Path, default=None,
        help="Override data/experiments/registry_seed.json path",
    )
    ap.add_argument(
        "--regime-path", type=Path, default=None,
        help="Override data/regime/latest.json path",
    )
    ap.add_argument(
        "--requeue-path", type=Path, default=None,
        help="Override data/research_factory/requeue.jsonl path",
    )

    ap.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Validate and print without writing anything",
    )

    return ap


def main() -> int:  # noqa: C901 — complexity is inherent in a multi-path decision recorder
    ap = _build_parser()
    args = ap.parse_args()

    dry_run = args.dry_run
    rf_dir = args.rf_dir or DEFAULT_RF_DIR
    seed_path = args.experiments_seed or DEFAULT_EXPERIMENTS_SEED
    regime_path = args.regime_path or DEFAULT_REGIME_PATH
    requeue_path = args.requeue_path or DEFAULT_REQUEUE_PATH

    candidate_id = args.candidate
    decision = args.decision
    actor = args.actor
    actor_ref = args.actor_ref

    print(f"Research Factory decision recorder")
    print(f"  candidate:  {candidate_id}")
    print(f"  decision:   {decision}")
    print(f"  actor:      {actor} (ref: {actor_ref})")
    print(f"  dry_run:    {dry_run}")
    print()

    # --- Load current state ---
    candidates = _load_candidates(rf_dir)
    transitions_list = _load_transitions(rf_dir)
    candidate, current_status = _resolve_candidate_status(
        candidate_id, candidates, transitions_list
    )

    if candidate is None:
        print(
            f"[ERROR] Candidate {candidate_id!r} not found in "
            f"{rf_dir / 'candidates.jsonl'}",
            file=sys.stderr,
        )
        return 1

    print(f"Current status: {current_status}")

    # --- Refuse double-decisions ---
    if current_status in _TERMINAL_STATES:
        print(
            f"[ERROR] Candidate {candidate_id} is already in terminal state "
            f"{current_status!r} — cannot re-decide.",
            file=sys.stderr,
        )
        return 1

    # paper-on-paper: refuse if already paper and trying to re-paper from human_review
    # (paper is not terminal but a fresh 'paper' decision from human_review is only valid once)
    if current_status == "paper" and decision == "paper":
        # Only refuse if the transition would be human_review->paper AND candidate
        # is currently 'paper' (not coming from paper->human_review decay path).
        # We check the actual from_state to decide.
        # For a paper candidate that's been re-surfaced for decay review via
        # paper->human_review, current_status is actually 'human_review'.
        # If current_status is 'paper', we refuse.
        print(
            f"[ERROR] Candidate {candidate_id} is already in state 'paper' — "
            f"cannot decide 'paper' again. If decay review triggered human_review, "
            f"the current status should be 'human_review'.",
            file=sys.stderr,
        )
        return 1

    if current_status != "human_review":
        print(
            f"[ERROR] Candidate {candidate_id} is in state {current_status!r}, "
            f"not 'human_review'. Human decisions only apply to candidates in "
            f"human_review state.",
            file=sys.stderr,
        )
        return 1

    # --- Per-decision required args validation ---
    extra_fields: dict = {}

    if decision == "paper":
        # expected_half_life_d: use domain prior if not provided
        domain = candidate.get("domain") or "?"
        if args.expected_half_life_d is not None:
            expected_half_life_d = args.expected_half_life_d
            defaulted_half_life = False
        else:
            expected_half_life_d = _DOMAIN_HALF_LIFE_DEFAULTS.get(domain, _DEFAULT_HALF_LIFE)
            defaulted_half_life = True
            print(
                f"  [INFO] expected_half_life_d not specified — using domain prior "
                f"{expected_half_life_d}d for domain={domain!r} (RF-9, defaulted=true)"
            )

        # Regime at entry
        regime_at_entry = _build_regime_at_entry(candidate, regime_path)
        print(f"  regime_at_entry: {regime_at_entry}")

        # come_back_on: derive from half-life (RF-9 clock)
        # Use come_back_on if provided, else compute from today + half_life
        if args.come_back_on:
            come_back_on = args.come_back_on
        else:
            from datetime import date, timedelta
            come_back_on = (date.today() + timedelta(days=expected_half_life_d)).isoformat()
            print(
                f"  [INFO] come_back_on derived from expected_half_life_d={expected_half_life_d}d: "
                f"{come_back_on}"
            )

        # Build track skeleton
        track_skeleton = _make_track_skeleton(
            candidate, decision, expected_half_life_d, regime_at_entry
        )
        track_rel_path = _write_track_file(rf_dir, candidate_id, track_skeleton, dry_run=dry_run)

        # Build seed entry (RF-9)
        seed_entry = _make_seed_entry(
            candidate=candidate,
            decision=decision,
            expected_half_life_d=expected_half_life_d,
            defaulted_half_life=defaulted_half_life,
            come_back_on=come_back_on,
            regime_at_entry=regime_at_entry,
        )

        # Transition mandatory fields for 'paper'
        extra_fields = {
            "seed_entry_ref": seed_entry.get("id"),
            "regime_at_entry": regime_at_entry,
            "expected_half_life_d": expected_half_life_d,
        }

    elif decision == "deferred":
        if not args.come_back_on:
            print(
                "[ERROR] --come-back-on YYYY-MM-DD is required for deferred decision",
                file=sys.stderr,
            )
            return 1
        come_back_on = args.come_back_on
        expected_half_life_d = args.expected_half_life_d
        defaulted_half_life = expected_half_life_d is None
        if defaulted_half_life:
            domain = candidate.get("domain") or "?"
            expected_half_life_d = _DOMAIN_HALF_LIFE_DEFAULTS.get(domain, _DEFAULT_HALF_LIFE)

        regime_at_entry = _build_regime_at_entry(candidate, regime_path)

        # Build track skeleton (for deferred accrual tracking)
        track_skeleton = _make_track_skeleton(
            candidate, decision, expected_half_life_d, regime_at_entry
        )
        track_rel_path = _write_track_file(rf_dir, candidate_id, track_skeleton, dry_run=dry_run)

        # Build seed entry (RF-9)
        seed_entry = _make_seed_entry(
            candidate=candidate,
            decision=decision,
            expected_half_life_d=expected_half_life_d,
            defaulted_half_life=defaulted_half_life,
            come_back_on=come_back_on,
            regime_at_entry=regime_at_entry,
        )

        extra_fields = {
            "come_back_on": come_back_on,
            "seed_entry_ref": seed_entry.get("id"),
        }

    elif decision in ("rejected", "retired"):
        if not args.kill_class:
            print(
                f"[ERROR] --kill-class is required for {decision} decision (RF-10)",
                file=sys.stderr,
            )
            return 1
        kill_class = args.kill_class
        n_at_kill = args.n_at_kill or 0
        mde_at_n = args.mde_at_n

        kill_evidence: dict = {
            "n_at_kill": n_at_kill,
            "kill_class": kill_class,
            "mde_at_n": mde_at_n,
            "regime_split": None,  # operator may add separately
            "source": f"human_decision/{actor}",
        }
        extra_fields = {
            "kill_evidence": kill_evidence,
        }

        # RF-10: requeue pointer for underpowered_accruing / regime_change_suspect
        seed_entry = None
        track_skeleton = None

    elif decision == "scoped_build":
        if not args.program_doc:
            print(
                "[ERROR] --program-doc is required for scoped_build decision (RF-4)",
                file=sys.stderr,
            )
            return 1
        program_doc = args.program_doc
        # Validate: the file should exist (or warn)
        prog_path = ROOT / program_doc
        if not prog_path.exists():
            print(
                f"  [WARN] program_doc {program_doc!r} does not exist on disk "
                f"— proceeding anyway (it may be created in the same commit)"
            )

        extra_fields = {
            "program_doc_ref": program_doc,
        }
        seed_entry = None
        track_skeleton = None

    # --- Write transition (state.py enforces actor law) ---
    try:
        # Map decision to target state
        to_state = {
            "paper": "paper",
            "deferred": "deferred",
            "rejected": "rejected",
            "scoped_build": "scoped_build",
        }[decision]

        transition_row = _write_transition(
            rf_dir=rf_dir,
            candidate_id=candidate_id,
            from_state=current_status,
            to_state=to_state,
            actor=actor,
            actor_ref=actor_ref,
            decision=decision,
            extra_fields=extra_fields,
            candidate=candidate,
            dry_run=dry_run,
        )
    except IllegalTransition as exc:
        print(f"[ERROR] Illegal transition: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[ERROR] Transition validation failed: {exc}", file=sys.stderr)
        return 1

    # --- Governance event (RF-12) ---
    _append_governance_event(
        candidate_id=candidate_id,
        decision=decision,
        actor=actor,
        actor_ref=actor_ref,
        root=ROOT,
        dry_run=dry_run,
    )

    # --- Seed entry + track file (RF-9) for paper/deferred ---
    if decision in ("paper", "deferred") and seed_entry is not None:
        _append_seed_entry(seed_path, seed_entry, dry_run=dry_run)

    # --- Requeue pointer for kill classes that warrant it (RF-10) ---
    if decision in ("rejected", "retired") and args.kill_class in (
        "underpowered_accruing", "regime_change_suspect"
    ):
        _write_requeue_pointer(
            requeue_path=requeue_path,
            candidate=candidate,
            kill_class=args.kill_class,
            n_at_kill=args.n_at_kill or 0,
            dry_run=dry_run,
        )

    print()
    if dry_run:
        print(f"[DRY-RUN] Decision {decision} for {candidate_id} would succeed.")
    else:
        print(f"Decision {decision} recorded for {candidate_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
