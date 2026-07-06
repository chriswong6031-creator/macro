"""engine.research_factory.monitor — Paper monitor logic (W6, RF-8/RF-9/RF-10).

Builds research_factory.paper_monitor.v1 rows for every candidate in status
'paper', plus come_back_on checks for 'awaiting_data' and 'deferred'.

Design rules (binding):
  RF-5   — monitor RECOMMENDS ONLY; it may emit a paper→human_review mechanical
            transition when action != continue; it NEVER retires (human-only).
  RF-8   — forward-ledger law; called only from scripts/research_factory_monitor.py
            which enforces --dry-run default / --write-only nightly.
  RF-9   — regime-aware: launched_hot flag on decay suppresses retire_recommended;
            emits 'launched_hot_context' companion flag instead.
  RF-10  — decay flag signals; requeue pointer written by the CLI layer.

Absent-file-safety: every file access is guarded; absent oracle ledger / track
file / challenge file all produce valid rows with sentinel values
('not_applicable' / 'ungradable').

One-night cortex lag: engine job reads prior night's cortex commit — accepted
and documented here (no machine_registry rows today anyway).

Pure stdlib: no pandas, no yaml, no third-party imports.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("research_factory.monitor")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum matured observations before 'warmup' ends.
# Per §5.4: warmup while observed n < a small floor.
WARMUP_FLOOR = 10

# Decay fraction: if observed metric < expected * (1 - DECAY_THRESHOLD), flag.
DECAY_THRESHOLD = 0.15  # 15% below expected triggers decay flag

# Fire-rate not-applicable sentinel (§5.4)
NOT_APPLICABLE = "not_applicable"

# Falsifier verdict when grading is impossible (absent/incompatible spec)
UNGRADABLE = "ungradable"


# ---------------------------------------------------------------------------
# File helpers (all absent-safe)
# ---------------------------------------------------------------------------


def _load_json_file(path: Path) -> dict | None:
    """Load a JSON file absent-safely.  Returns None on missing or parse error."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Failed to parse %s: %s", path, exc)
        return None


def _load_jsonl_file(path: Path) -> list[dict]:
    """Load a JSONL file absent-safely.  Returns [] on missing or error."""
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except OSError:
        pass
    return rows


def _today_iso() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Candidate state resolver
# ---------------------------------------------------------------------------


def _resolve_current_status(candidate_id: str, transitions: list[dict]) -> str | None:
    """Resolve the current status of a candidate from its transitions log.

    Returns the last 'to' state, or None if no transitions exist.
    """
    last: str | None = None
    for t in transitions:
        if t.get("candidate_id") == candidate_id:
            last = t.get("to", last)
    return last


def _load_all_candidates(rf_dir: Path) -> list[dict]:
    """Load candidates.jsonl and override status from transitions.jsonl."""
    candidates = _load_jsonl_file(rf_dir / "candidates.jsonl")
    transitions = _load_jsonl_file(rf_dir / "transitions.jsonl")

    # Build latest-to per candidate from transitions
    last_to: dict[str, str] = {}
    for t in transitions:
        cid = t.get("candidate_id")
        if cid:
            last_to[cid] = t.get("to", last_to.get(cid, ""))

    # Apply override
    seen: set[str] = set()
    result: list[dict] = []
    for c in candidates:
        cid = c.get("candidate_id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        c = dict(c)
        if cid in last_to:
            c["status"] = last_to[cid]
        result.append(c)
    return result


# ---------------------------------------------------------------------------
# Track file helpers
# ---------------------------------------------------------------------------


def _load_track(rf_dir: Path, candidate_id: str) -> dict | None:
    """Load data/research_factory/track/<candidate_id>.json absent-safely."""
    return _load_json_file(rf_dir / "track" / f"{candidate_id}.json")


def _extract_observed_metric(
    track: dict | None,
    candidate: dict,
) -> dict:
    """Extract the observed metric from the track file.

    Returns a dict with 'name', 'value', 'n'.
    Falls back to not_applicable sentinels when track is absent.
    """
    ep = candidate.get("evaluation_plan") or {}
    metric_name = ep.get("primary_metric") or "primary_metric"

    if track is None:
        return {"name": metric_name, "value": None, "n": 0}

    # Look for horizons block (as written by research_factory_decide.py)
    horizons = track.get("horizons") or {}
    n_matured = 0
    metric_value = None

    if horizons:
        # Sum n_matured across all horizons; pick metric from the declared horizon
        horizon_d = str(ep.get("horizon_d") or 21)
        horizon_data = horizons.get(horizon_d) or next(iter(horizons.values()), {})
        n_matured = horizon_data.get("n_matured") or 0
        metric_value = horizon_data.get("metric_value")

    # Also check top-level observed fields written by nightly updates
    if track.get("n_matured") is not None:
        n_matured = track["n_matured"]
    if track.get("observed_metric_value") is not None:
        metric_value = track["observed_metric_value"]

    return {"name": metric_name, "value": metric_value, "n": n_matured}


def _extract_expected_metric(candidate: dict) -> dict:
    """Extract expected metric from the candidate's frozen evaluation_plan.

    Per §5.4: source must be 'domain_gate' — never authored.
    """
    ep = candidate.get("evaluation_plan") or {}
    metric_name = ep.get("primary_metric") or "primary_metric"
    # The expected value may be stored as 'expected_metric_value' or within
    # the evaluation_plan; if absent, leave as None (display-only — not an error).
    expected_value = ep.get("expected_metric_value") or ep.get("gate_threshold")
    return {
        "name": metric_name,
        "value": expected_value,
        "source": "domain_gate",
    }


# ---------------------------------------------------------------------------
# Regime-at-entry extraction
# ---------------------------------------------------------------------------


def _extract_regime_at_entry(candidate: dict, transitions: list[dict]) -> dict:
    """Extract regime_at_entry from the paper transition or candidate artifacts.

    Returns a dict with at least 'launched_hot' key (defaults to False).
    """
    # Try to find regime_at_entry from the paper transition
    for t in transitions:
        if (
            t.get("candidate_id") == candidate.get("candidate_id")
            and t.get("to") == "paper"
        ):
            rae = t.get("regime_at_entry")
            if isinstance(rae, dict):
                return rae

    # Fallback: candidate artifacts
    arts = candidate.get("artifacts") or {}
    if isinstance(arts, dict) and "regime_at_entry" in arts:
        return arts["regime_at_entry"]

    # No regime info available
    return {"regime": "unknown", "launched_hot": False}


# ---------------------------------------------------------------------------
# Oracle live-ledger helpers
# ---------------------------------------------------------------------------


def _get_oracle_n_fires(
    compound_id: str | None,
    oracle_live_ledger: list[dict],
) -> int:
    """Count fires for a compound_id from oracle live_ledger.jsonl.

    Counts rows where outcome_mature=True (matured observations).
    """
    if not compound_id:
        return 0
    return sum(
        1
        for row in oracle_live_ledger
        if row.get("compound_id") == compound_id and row.get("outcome_mature") is True
    )


def _get_oracle_metric(
    compound_id: str | None,
    oracle_live_ledger: list[dict],
    metric_name: str,
) -> float | None:
    """Compute the observed metric for an oracle compound from the live ledger.

    For oracle reversion candidates, the primary metric is WR (win rate).
    Computes from excess_21d sign: positive excess = win.
    """
    if not compound_id:
        return None

    matured = [
        row
        for row in oracle_live_ledger
        if row.get("compound_id") == compound_id and row.get("outcome_mature") is True
    ]
    if not matured:
        return None

    # Primary metric heuristic based on name
    lname = metric_name.lower()
    if "wr" in lname or "win" in lname:
        # Win rate from 21d reversion (positive excess = win for reversion signals)
        wins = [
            r for r in matured
            if r.get("excess_21d") is not None and float(r["excess_21d"]) > 0
        ]
        return round(len(wins) / len(matured), 4)
    elif "excess_21d" in lname or "excess21" in lname:
        vals = [r["excess_21d"] for r in matured if r.get("excess_21d") is not None]
        return round(sum(vals) / len(vals), 4) if vals else None
    elif "excess_63d" in lname or "excess63" in lname:
        vals = [r["excess_63d"] for r in matured if r.get("excess_63d") is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    # Fallback: return None — no assertion on unknown metrics
    return None


# ---------------------------------------------------------------------------
# Decay detection
# ---------------------------------------------------------------------------


def _detect_decay(
    expected_value: float | None,
    observed_value: float | None,
    n: int,
    decay_conditions: list,
    launched_hot: bool,
    expected_half_life_d: int | None,
) -> tuple[list[str], list[str]]:
    """Detect decay and return (decay_flags, data_health_flags).

    RF-9 regime-aware: if launched_hot, append 'launched_hot_context' alongside
    any decay flag instead of escalating to retire_recommended.

    Returns:
        decay_flags     — list of flag strings (may include 'launched_hot_context')
        data_health_flags — list of data quality flag strings
    """
    decay_flags: list[str] = []
    data_health_flags: list[str] = []

    if n < WARMUP_FLOOR:
        # Not enough data to make decay calls; just flag data state
        data_health_flags.append(f"warmup_n={n}_below_floor_{WARMUP_FLOOR}")
        return decay_flags, data_health_flags

    # Metric drift check
    if expected_value is not None and observed_value is not None:
        try:
            exp_f = float(expected_value)
            obs_f = float(observed_value)
            # Only flag decay when expected_value is positive (e.g. WR > 0.5)
            if exp_f > 0:
                relative_miss = (exp_f - obs_f) / exp_f
                if relative_miss > DECAY_THRESHOLD:
                    decay_flags.append(
                        f"metric_below_expected: obs={obs_f:.4f} exp={exp_f:.4f} "
                        f"miss={relative_miss:.1%}"
                    )
        except (TypeError, ValueError, ZeroDivisionError):
            data_health_flags.append("metric_type_error")

    # Check explicit decay_conditions from the candidate spec
    for cond in (decay_conditions or []):
        if not isinstance(cond, str):
            continue
        # Parse simple "metric < threshold" or "metric > threshold" conditions
        # (best-effort; just log unresolvable conditions as data_health_flags)
        for op in ("<", ">"):
            if op in cond:
                parts = cond.split(op, 1)
                if len(parts) == 2:
                    try:
                        threshold = float(parts[1].strip())
                        if op == "<" and observed_value is not None:
                            if float(observed_value) < threshold:
                                decay_flags.append(f"decay_condition_triggered: {cond}")
                        elif op == ">" and observed_value is not None:
                            if float(observed_value) > threshold:
                                decay_flags.append(f"decay_condition_triggered: {cond}")
                    except (ValueError, TypeError):
                        data_health_flags.append(f"unparseable_decay_condition: {cond}")
                break

    # RF-9: if launched_hot, companion flag rather than direct retire_recommended escalation
    if decay_flags and launched_hot:
        decay_flags.append("launched_hot_context")

    return decay_flags, data_health_flags


# ---------------------------------------------------------------------------
# Falsifier grading
# ---------------------------------------------------------------------------


def _grade_falsifier(
    challenge_path: Path | None,
    candidate: dict,
) -> tuple[str | None, str]:
    """Grade the falsifier spec from the challenge file if compatible.

    Returns (falsifier_ref, falsifier_verdict).
    falsifier_verdict is one of: 'ungradable', 'not_triggered', 'triggered', 'data_missing'
    """
    if challenge_path is None or not challenge_path.exists():
        return None, UNGRADABLE

    challenge = _load_json_file(challenge_path)
    if not challenge:
        return None, UNGRADABLE

    reviewer = challenge.get("reviewer") or {}
    falsifier_spec = reviewer.get("falsifier_spec")
    falsifier_ref = reviewer.get("falsifier_ref")

    if not falsifier_spec and not falsifier_ref:
        return None, UNGRADABLE

    ref = falsifier_ref or f"challenge/{candidate.get('candidate_id', '?')}"

    # Attempt grading via engine/falsifier_tripwires.py if the spec is
    # compatible (has cycle-falsifier DSL format with 'id' and 'legs').
    # Research-factory falsifier specs are generally free-form text from
    # the reviewer — they do not have compiled DSL legs unless explicitly
    # structured.  Absent/incompatible → ungradable, loud in the row.
    if isinstance(falsifier_spec, dict) and falsifier_spec.get("legs"):
        try:
            # Attempt DSL evaluation (cycle falsifier API)
            from engine.falsifier_tripwires import evaluate_all  # lazy import
            results = evaluate_all()
            spec_id = falsifier_spec.get("id")
            if spec_id:
                for r in results:
                    if r.id == spec_id:
                        verdict = "triggered" if r.state == "FIRED" else "not_triggered"
                        return ref, verdict
            log.info("Falsifier spec id=%s not found in evaluate_all results", spec_id)
            return ref, UNGRADABLE
        except Exception as exc:
            log.warning(
                "Falsifier grading failed for %s: %s — marking ungradable",
                ref, exc,
            )
            return ref, UNGRADABLE
    else:
        # Free-form text spec — not compilable; ungradable with a loud note
        log.info(
            "Falsifier spec for %s is not a compilable DSL (no 'legs') — ungradable",
            candidate.get("candidate_id", "?"),
        )
        return ref, UNGRADABLE


# ---------------------------------------------------------------------------
# Paper status + action derivation
# ---------------------------------------------------------------------------


def _derive_paper_status_and_action(
    n: int,
    decay_flags: list[str],
    launched_hot: bool,
    is_come_back_due: bool,
) -> tuple[str, str]:
    """Derive paper_status and action from observation state.

    Returns (paper_status, action).

    paper_status: 'warmup' | 'operating' | 'review' | 'retire_recommended'
    action:       'continue' | 'review' | 'retire_recommended'

    RF-9: launched_hot decay → 'launched_hot_context' companion flag, not
    retire_recommended escalation — we stay at 'review'.
    """
    # Warmup phase
    if n < WARMUP_FLOOR:
        return "warmup", "continue"

    # No decay flags → operating, continue
    if not decay_flags:
        if is_come_back_due:
            return "review", "review"
        return "operating", "continue"

    # Has decay flags (excluding the companion flag)
    real_decay = [f for f in decay_flags if f != "launched_hot_context"]

    if not real_decay:
        # Only companion flag — should not happen but guard it
        if is_come_back_due:
            return "review", "review"
        return "operating", "continue"

    # Real decay present
    if launched_hot:
        # RF-9: regime-aware damping — do not escalate to retire_recommended
        return "review", "review"

    # Non-hot decay → retire_recommended
    return "retire_recommended", "retire_recommended"


# ---------------------------------------------------------------------------
# Core monitor row builder
# ---------------------------------------------------------------------------


def _build_monitor_row(
    candidate: dict,
    transitions: list[dict],
    oracle_live_ledger: list[dict],
    rf_dir: Path,
    as_of: str,
) -> dict:
    """Build a research_factory.paper_monitor.v1 row for a single candidate.

    Called for candidates in 'paper' status.
    All upstream file reads are absent-safe; missing data → sentinel values.
    """
    cid = candidate.get("candidate_id", "?")
    ep = candidate.get("evaluation_plan") or {}
    decay_conditions = candidate.get("decay_conditions") or []
    spec_ref = candidate.get("spec_ref")

    # Regime-at-entry
    rae = _extract_regime_at_entry(candidate, transitions)
    launched_hot: bool = bool(rae.get("launched_hot", False))

    # expected_half_life_d (for RF-9 come_back_on context)
    expected_half_life_d = ep.get("expected_half_life_d")

    # Expected metric from frozen evaluation_plan
    expected_metric = _extract_expected_metric(candidate)

    # Load track file
    track = _load_track(rf_dir, cid)

    # Observed metric: try track file first, then oracle live ledger for oracle compounds
    observed_metric = _extract_observed_metric(track, candidate)

    # If oracle compound, supplement from live_ledger
    domain = candidate.get("domain")
    candidate_type = candidate.get("candidate_type")
    if domain == "oracle" and candidate_type == "oracle_compound" and spec_ref:
        oracle_n = _get_oracle_n_fires(spec_ref, oracle_live_ledger)
        oracle_val = _get_oracle_metric(
            spec_ref, oracle_live_ledger, expected_metric.get("name", "")
        )
        # Prefer oracle-derived n if track has no matured obs yet
        if observed_metric["n"] == 0 and oracle_n > 0:
            observed_metric["n"] = oracle_n
        if observed_metric["value"] is None and oracle_val is not None:
            observed_metric["value"] = oracle_val

    n = observed_metric.get("n") or 0

    # Decay detection
    decay_flags, data_health_flags = _detect_decay(
        expected_value=expected_metric.get("value"),
        observed_value=observed_metric.get("value"),
        n=n,
        decay_conditions=decay_conditions,
        launched_hot=launched_hot,
        expected_half_life_d=expected_half_life_d,
    )

    # come_back_on check (is it due?)
    come_back_on = None
    is_come_back_due = False
    for t in transitions:
        if t.get("candidate_id") == cid and t.get("to") == "paper":
            come_back_on = t.get("come_back_on") or ep.get("come_back_on")
            break
    # Also check latest deferred transition
    if not come_back_on:
        for t in transitions:
            if t.get("candidate_id") == cid and t.get("to") in ("deferred", "awaiting_data"):
                cb = t.get("come_back_on")
                if cb:
                    come_back_on = cb
    if come_back_on:
        try:
            cb_date = date.fromisoformat(str(come_back_on)[:10])
            is_come_back_due = cb_date <= date.today()
        except (ValueError, TypeError):
            pass

    # Paper status + action
    paper_status, action = _derive_paper_status_and_action(
        n=n,
        decay_flags=decay_flags,
        launched_hot=launched_hot,
        is_come_back_due=is_come_back_due,
    )

    # Falsifier grading
    challenge_path = rf_dir / "challenges" / f"{cid}.json"
    falsifier_ref, falsifier_verdict = _grade_falsifier(challenge_path, candidate)

    row: dict = {
        "schema": "research_factory.paper_monitor.v1",
        "authority": "display_only",
        "candidate_id": cid,
        "as_of": as_of,
        "paper_status": paper_status,
        "expected_metric": expected_metric,
        "observed_metric": observed_metric,
        "expected_fire_rate_pm": NOT_APPLICABLE,
        "observed_fire_rate_pm": None,
        "regime_at_entry": rae,
        "falsifier_ref": falsifier_ref,
        "falsifier_verdict": falsifier_verdict,
        "data_health_flags": data_health_flags,
        "decay_flags": decay_flags,
        "action": action,
        "note": "display-only; no scored-path authority",
    }
    return row


# ---------------------------------------------------------------------------
# Clock check: awaiting_data / deferred come_back_on
# ---------------------------------------------------------------------------


def _build_clock_row(
    candidate: dict,
    transitions: list[dict],
    as_of: str,
) -> dict | None:
    """Build a monitor row for awaiting_data / deferred candidates whose
    come_back_on <= today.

    Returns a paper_monitor-compatible row with action='review' (and for
    deferred, a 'deferred_come_back_due' decay_flag), or None if not yet due.
    """
    cid = candidate.get("candidate_id", "?")
    status = candidate.get("status", "")

    # Find the last come_back_on from transitions
    come_back_on = None
    for t in reversed(transitions):
        if t.get("candidate_id") == cid and t.get("to") == status:
            cb = t.get("come_back_on")
            if cb:
                come_back_on = cb
                break

    if not come_back_on:
        # Check evaluation_plan
        ep = candidate.get("evaluation_plan") or {}
        come_back_on = ep.get("come_back_on")

    if not come_back_on:
        return None

    try:
        cb_date = date.fromisoformat(str(come_back_on)[:10])
    except (ValueError, TypeError):
        return None

    if cb_date > date.today():
        return None  # not yet due

    # Due — emit a review row
    rae = _extract_regime_at_entry(candidate, transitions)
    ep = candidate.get("evaluation_plan") or {}
    expected_metric = _extract_expected_metric(candidate)

    decay_flags = [f"{status}_come_back_due: {come_back_on}"]
    data_health_flags: list[str] = []

    # Map status → paper_status label
    paper_status = "review"
    action = "review"

    row: dict = {
        "schema": "research_factory.paper_monitor.v1",
        "authority": "display_only",
        "candidate_id": cid,
        "as_of": as_of,
        "paper_status": paper_status,
        "expected_metric": expected_metric,
        "observed_metric": {"name": expected_metric.get("name", ""), "value": None, "n": 0},
        "expected_fire_rate_pm": NOT_APPLICABLE,
        "observed_fire_rate_pm": None,
        "regime_at_entry": rae,
        "falsifier_ref": None,
        "falsifier_verdict": UNGRADABLE,
        "data_health_flags": data_health_flags,
        "decay_flags": decay_flags,
        "action": action,
        "note": f"display-only; {status} come_back_on={come_back_on} is due",
    }
    return row


# ---------------------------------------------------------------------------
# Mechanical paper→human_review transition
# ---------------------------------------------------------------------------


def _make_paper_human_review_transition(
    candidate_id: str,
    reason: str,
    as_of: str,
) -> dict:
    """Build a paper→human_review transition row (mechanical A2, RF-5).

    The monitor MAY emit this transition when action != continue.
    It NEVER transitions to retired — that is human-only.
    """
    return {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "from": "paper",
        "to": "human_review",
        "reason_code": "monitor_decay_flag",
        "reason_text": reason,
        "actor": "script",
        "actor_ref": "research_factory_monitor/nightly",
        "as_of": as_of,
        "artifact_refs": ["data/research_factory/paper_monitor.jsonl"],
        "kill_evidence": None,
    }


def _make_deferred_human_review_transition(
    candidate_id: str,
    come_back_on: str,
    as_of: str,
) -> dict:
    """Build a deferred→human_review transition (mechanical clock resurfacing, RF-5).

    Clock resurfacing (deferred→human_review) is mechanical A2 attention-routing per RF-5.
    """
    return {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "from": "deferred",
        "to": "human_review",
        "reason_code": "come_back_on_due",
        "reason_text": f"Deferred come_back_on={come_back_on} is past due; routing to human_review",
        "actor": "script",
        "actor_ref": "research_factory_monitor/nightly",
        "as_of": as_of,
        "artifact_refs": ["data/research_factory/paper_monitor.jsonl"],
        "kill_evidence": None,
        "review_packet_ref": "monitor/come_back_on_clock",
    }


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------


def run_monitor(
    rf_dir: Path,
    oracle_live_ledger_path: Path | None = None,
    as_of: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Run the paper monitor over all paper/awaiting_data/deferred candidates.

    Parameters
    ----------
    rf_dir                  : data/research_factory/ directory (absolute path)
    oracle_live_ledger_path : path to data/oracle/compounds/live_ledger.jsonl
                              (absent-safe — defaults to standard location)
    as_of                   : ISO date string (defaults to today)

    Returns
    -------
    (monitor_rows, transition_rows)
        monitor_rows    — list of research_factory.paper_monitor.v1 rows
        transition_rows — list of research_factory.transition.v1 rows that
                          the CLI layer should write to transitions.jsonl
                          (paper→human_review when action != continue, and
                          deferred→human_review when come_back_on is due).
                          The monitor NEVER emits retired transitions.
    """
    if as_of is None:
        as_of = _today_iso()

    # Load oracle live ledger (absent-safe)
    if oracle_live_ledger_path is None:
        oracle_live_ledger_path = rf_dir.parent.parent / "data" / "oracle" / "compounds" / "live_ledger.jsonl"
    oracle_live_ledger = _load_jsonl_file(oracle_live_ledger_path)

    # Load all candidates with status override from transitions
    all_candidates = _load_all_candidates(rf_dir)
    transitions = _load_jsonl_file(rf_dir / "transitions.jsonl")

    monitor_rows: list[dict] = []
    transition_rows: list[dict] = []

    for candidate in all_candidates:
        cid = candidate.get("candidate_id", "?")
        status = candidate.get("status", "")

        if status == "paper":
            try:
                row = _build_monitor_row(
                    candidate=candidate,
                    transitions=transitions,
                    oracle_live_ledger=oracle_live_ledger,
                    rf_dir=rf_dir,
                    as_of=as_of,
                )
                monitor_rows.append(row)

                # Mechanical paper→human_review transition when action != continue (RF-5)
                if row.get("action") in ("review", "retire_recommended"):
                    decay_summary = "; ".join(row.get("decay_flags") or ["decay_flagged"])
                    t_row = _make_paper_human_review_transition(
                        candidate_id=cid,
                        reason=f"Monitor action={row['action']}: {decay_summary[:200]}",
                        as_of=as_of,
                    )
                    transition_rows.append(t_row)
                    log.info(
                        "Monitor: paper→human_review queued for %s (action=%s)",
                        cid, row["action"],
                    )

            except Exception as exc:
                log.error("Monitor failed for candidate %s: %s", cid, exc, exc_info=True)
                # Emit a minimal error row (non-fatal — RF-8 exit 0 requirement)
                monitor_rows.append({
                    "schema": "research_factory.paper_monitor.v1",
                    "authority": "display_only",
                    "candidate_id": cid,
                    "as_of": as_of,
                    "paper_status": "review",
                    "expected_metric": {"name": "unknown", "value": None, "source": "domain_gate"},
                    "observed_metric": {"name": "unknown", "value": None, "n": 0},
                    "expected_fire_rate_pm": NOT_APPLICABLE,
                    "observed_fire_rate_pm": None,
                    "regime_at_entry": {"launched_hot": False},
                    "falsifier_ref": None,
                    "falsifier_verdict": UNGRADABLE,
                    "data_health_flags": [f"monitor_error: {exc}"],
                    "decay_flags": [],
                    "action": "review",
                    "note": "display-only; monitor error — routing to review",
                })

        elif status in ("awaiting_data", "deferred"):
            try:
                clock_row = _build_clock_row(
                    candidate=candidate,
                    transitions=transitions,
                    as_of=as_of,
                )
                if clock_row is not None:
                    monitor_rows.append(clock_row)

                    # Deferred come_back_on due → mechanical deferred→human_review (RF-5)
                    if status == "deferred":
                        # Find the come_back_on value
                        cbo = None
                        for t in reversed(transitions):
                            if t.get("candidate_id") == cid and t.get("to") == "deferred":
                                cbo = t.get("come_back_on")
                                break
                        if cbo:
                            t_row = _make_deferred_human_review_transition(
                                candidate_id=cid,
                                come_back_on=str(cbo),
                                as_of=as_of,
                            )
                            transition_rows.append(t_row)
                            log.info(
                                "Monitor: deferred→human_review queued for %s (come_back_on=%s)",
                                cid, cbo,
                            )

            except Exception as exc:
                log.error(
                    "Monitor clock check failed for candidate %s: %s", cid, exc, exc_info=True
                )

    log.info(
        "Monitor complete: %d monitor rows, %d transition rows (as_of=%s)",
        len(monitor_rows), len(transition_rows), as_of,
    )
    return monitor_rows, transition_rows
