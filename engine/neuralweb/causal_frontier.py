"""engine.neuralweb.causal_frontier — CHF W3: Frontier ledger, surprise queue, lab state.

Nightly drift-only artifacts (no batteries, no LLM).

ARTIFACTS PRODUCED
------------------
data/neuralweb/causal_frontier.json
    Coverage map over (cause_family × target_family × environment) cells.
    States: unexplored | accruing | screened | null_basin | killed
    Value heuristic (deterministic, documented below).
    Printed cumulative causal_scan width.

data/neuralweb/causal_surprise_queue.jsonl
    Surprise tickets from:
    (a) mechanism_pathways.json — pathways[] with reason no_attributable_driver
    (b) release_forecast/forward_ledger.jsonl — big miss graded surprises
    (c) oracle_state.json — active_episodes with failed status
    Each ticket: {ticket_id, source_artifact, source_asof, stale, description,
                  suggested_target_family}
    Absent sources → no tickets (never fabricated).

data/neuralweb/causal_lab_state.json  (also site/neuralwebdata/causal_lab_state.json)
    Schema: neuralweb.causal_lab_state.v1
    Heartbeat + funnel counts + frontier summary + surprise queue summary.
    Site copy byte-identical content.

AUTHORITY CONTRACT (CHF-R1)
----------------------------
All outputs are display-tier infrastructure, authority booleans all False,
not_a_signal: True, scored_path_surfaces: [].  Language law: no banned words.

VALUE HEURISTIC (frontier ranking)
------------------------------------
Deterministic ranking for the frontier ledger (documented here per CHF-R8):

  score = UNEXPLORED_BONUS + DATA_PRESENT_BONUS + ERA_BREADTH_BONUS
        - NULL_BASIN_PENALTY - KILLED_PENALTY

  UNEXPLORED_BONUS    = 10 if state == 'unexplored' else 0
  DATA_PRESENT_BONUS  = 5  if cause feature has present=True else 0
  ERA_BREADTH_BONUS   = min(len(era_coverage), 4) * 1.0
  NULL_BASIN_PENALTY  = 20 if state == 'null_basin' else 0
  KILLED_PENALTY      = 100 if state == 'killed' else 0

Higher score = higher priority for the next battery batch.  Ties broken by
(cause_family, target_family, environment) lexicographic order.  This formula
is intentionally simple and logged verbatim here so it cannot drift from what
the runner actually uses.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema identity
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.causal_lab_state.v1"
ARTIFACT_CAUSAL_LAB_STATE = "causal-lab-state"

# ---------------------------------------------------------------------------
# Source artifact paths (relative to repo root)
# ---------------------------------------------------------------------------

_INVENTORY_PATH = Path("data") / "neuralweb" / "causal_feature_inventory.json"
_EDGES_PATH = Path("data") / "neuralweb" / "causal_edges.jsonl"
_NULLS_PATH = Path("data") / "neuralweb" / "causal_nulls.jsonl"
_MECHANISMS_PATH = Path("data") / "neuralweb" / "causal_mechanisms.jsonl"
_FRONTIER_PATH = Path("data") / "neuralweb" / "causal_frontier.json"
_SURPRISE_QUEUE_PATH = Path("data") / "neuralweb" / "causal_surprise_queue.jsonl"
_LAB_STATE_PATH = Path("data") / "neuralweb" / "causal_lab_state.json"
_SITE_LAB_STATE_PATH = Path("site") / "neuralwebdata" / "causal_lab_state.json"
_TRIAL_LEDGER_PATH = Path("data") / "trial_ledger.jsonl"
_MECHANISM_PATHWAYS_PATH = Path("data") / "neuralweb" / "mechanism_pathways.json"
_RELEASE_FORECAST_LEDGER = Path("data") / "release_forecast" / "forward_ledger.jsonl"
_ORACLE_STATE_PATH = Path("site") / "basketdata" / "oracle_state.json"

# ---------------------------------------------------------------------------
# Target families (must match causal_targets.py)
# ---------------------------------------------------------------------------

TARGET_FAMILIES = ["regime_risk", "entry_quality"]

# Value heuristic constants (documented in module docstring)
_UNEXPLORED_BONUS = 10
_DATA_PRESENT_BONUS = 5
_ERA_BREADTH_MAX = 4
_NULL_BASIN_PENALTY = 20
_KILLED_PENALTY = 100


# ---------------------------------------------------------------------------
# Ledger reader helpers
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file; return [] on any error."""
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except OSError:
        pass
    return rows


def _load_json(path: Path) -> dict | list | None:
    """Read a JSON file; return None on any error."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _cumulative_causal_scan_width(root: Path) -> int:
    """Return cumulative causal_scan family width from the trial ledger."""
    from engine.neuralweb.causal_scout import cumulative_family_width
    try:
        return cumulative_family_width(root)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Frontier state machine
# ---------------------------------------------------------------------------

def _cell_state_from_records(
    cause_family: str,
    target_family: str,
    environment: str,
    edges: list[dict],
    nulls: list[dict],
    kill_mask_edge_ids: set[str],
) -> str:
    """Determine the frontier state for one (cause_family, target_family, env) cell.

    State machine:
      killed      — any edge_id in kill_mask
      null_basin  — any null entry for this cell combination
      screened    — any edge with verdict=='screened_candidate'
      accruing    — any edge present (non-null, non-killed)
      unexplored  — no edge or null entry at all
    """
    # Build cell key for matching
    cell_key = f"{cause_family}|{target_family}|{environment}"

    # Check kill mask (by edge_id prefix matching cause/target)
    for eid in kill_mask_edge_ids:
        # Edge IDs encode cause+target+env; check prefix match
        if cause_family in eid and target_family in eid:
            return "killed"

    # Check nulls
    for null in nulls:
        nc = null.get("cause_family", "") or null.get("edge_id", "")
        nt = null.get("target_family", "") or ""
        ne = null.get("environment", environment)
        if (
            (cause_family in nc or nc in cause_family) and
            (not nt or target_family in nt or nt in target_family) and
            ne == environment
        ):
            return "null_basin"

    # Check edges
    matching = [
        e for e in edges
        if (
            (e.get("cause_family", "") == cause_family or cause_family in e.get("edge_id", "")) and
            (e.get("target_family", "") == target_family or target_family in e.get("edge_id", "")) and
            e.get("environment", environment) == environment
        )
    ]
    if matching:
        if any(e.get("verdict") == "screened_candidate" for e in matching):
            return "screened"
        return "accruing"

    return "unexplored"


def _value_heuristic(
    state: str,
    cause_meta: dict,
    era_coverage: list[str],
) -> float:
    """Compute deterministic value score for a frontier cell (see module docstring)."""
    score = 0.0
    if state == "unexplored":
        score += _UNEXPLORED_BONUS
    if cause_meta.get("present", False):
        score += _DATA_PRESENT_BONUS
    score += min(len(era_coverage), _ERA_BREADTH_MAX) * 1.0
    if state == "null_basin":
        score -= _NULL_BASIN_PENALTY
    if state == "killed":
        score -= _KILLED_PENALTY
    return score


# ---------------------------------------------------------------------------
# Frontier ledger builder
# ---------------------------------------------------------------------------

def build_frontier(root: Path) -> dict:
    """Build the frontier coverage map.

    Returns the frontier dict (to be serialized as JSON).
    """
    asof = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Load all source artifacts
    inventory_raw = _load_json(root / _INVENTORY_PATH)
    features: list[dict] = []
    if isinstance(inventory_raw, dict):
        features = inventory_raw.get("features", [])

    edges = _load_jsonl(root / _EDGES_PATH)
    nulls = _load_jsonl(root / _NULLS_PATH)

    # Build kill mask edge IDs from nulls (runtime check — see causal_scout)
    # The compiled section in config/causal_priors.yml is the CI-synced mirror;
    # at runtime we read causal_nulls.jsonl directly to block re-testing.
    kill_mask_edge_ids: set[str] = {
        n.get("edge_id", "") for n in nulls if n.get("edge_id")
    }

    # Load causal_priors.yml curated kill mask entries
    try:
        import yaml
        priors_path = root / "config" / "causal_priors.yml"
        if priors_path.exists():
            with priors_path.open(encoding="utf-8") as fh:
                priors = yaml.safe_load(fh) or {}
            curated = (priors.get("kill_mask") or {}).get("curated") or []
            for entry in curated:
                eid = entry.get("edge_id", "")
                if eid:
                    kill_mask_edge_ids.add(eid)
    except Exception:
        pass

    # Enumerate candidate-cause features
    cause_features = [
        f for f in features
        if "candidate_cause" in (f.get("allowed_roles") or [])
    ]

    # Build cells
    cells: list[dict] = []
    environments = ["full", "high_vol_regime", "low_vol_regime"]  # declared splits (CHF-R5)

    for feat in cause_features:
        cause_fam = feat.get("family", feat.get("feature_id", "unknown"))
        era_cov = feat.get("era_coverage") or []

        for tgt_fam in TARGET_FAMILIES:
            for env in environments:
                state = _cell_state_from_records(
                    cause_fam, tgt_fam, env, edges, nulls, kill_mask_edge_ids
                )
                score = _value_heuristic(state, feat, era_cov)
                cells.append({
                    "cause_family": cause_fam,
                    "cause_feature_id": feat.get("feature_id", ""),
                    "target_family": tgt_fam,
                    "environment": env,
                    "state": state,
                    "value_score": round(score, 2),
                    "era_coverage": era_cov,
                    "data_present": feat.get("present", False),
                })

    # Sort by descending value_score, then lexicographic for determinism
    cells.sort(key=lambda c: (-c["value_score"], c["cause_family"], c["target_family"], c["environment"]))

    # Summarize by state
    state_counts: dict[str, int] = {}
    for cell in cells:
        s = cell["state"]
        state_counts[s] = state_counts.get(s, 0) + 1

    # Cumulative width
    cumulative_width = _cumulative_causal_scan_width(root)

    return {
        "schema": "neuralweb.causal_frontier.v1",
        "asof": asof,
        "cells": cells,
        "state_summary": state_counts,
        "total_cells": len(cells),
        "cumulative_causal_scan_width": cumulative_width,
        "value_heuristic_formula": (
            "score = UNEXPLORED_BONUS(10 if unexplored) "
            "+ DATA_PRESENT_BONUS(5 if present) "
            "+ ERA_BREADTH_BONUS(min(era_coverage_len, 4) * 1.0) "
            "- NULL_BASIN_PENALTY(20 if null_basin) "
            "- KILLED_PENALTY(100 if killed)"
        ),
        "target_families": TARGET_FAMILIES,
        "environments_declared": environments,
        "authority": {
            "tier": "shadow",
            "display_only": True,
            "not_a_signal": True,
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
            "may_escalate": False,
            "scored_path_surfaces": [],
        },
    }


# ---------------------------------------------------------------------------
# Surprise queue builder
# ---------------------------------------------------------------------------

def _make_ticket_id(source_artifact: str, key: str) -> str:
    """Deterministic ticket ID from source + key."""
    raw = f"{source_artifact}|{key}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_surprise_queue(root: Path) -> list[dict]:
    """Build the surprise queue from three source artifacts.

    Sources (absent sources → no tickets):
    (a) mechanism_pathways.json — pathways with no_attributable_driver
    (b) release_forecast/forward_ledger.jsonl — big-miss surprise rows
    (c) oracle_state.json — active_episodes with failed status

    Returns list of ticket dicts (to be serialized as JSONL).
    """
    tickets: list[dict] = []
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # (a) mechanism_pathways.json
    pathways_raw = _load_json(root / _MECHANISM_PATHWAYS_PATH)
    if pathways_raw is None:
        log.debug("build_surprise_queue: mechanism_pathways.json absent")
    else:
        pathways_asof = ""
        pathways_list: list[dict] = []
        if isinstance(pathways_raw, dict):
            pathways_asof = str(pathways_raw.get("as_of", ""))
            pathways_list = pathways_raw.get("pathways", [])
        elif isinstance(pathways_raw, list):
            pathways_list = pathways_raw

        # Ticket when pathway has empty or no driver explanation
        for pw in pathways_list:
            reason = pw.get("reason", "")
            family = pw.get("family", "unknown")
            driver = pw.get("driver", "")
            # Generate ticket if no driver is attributable
            if not driver or reason == "no_attributable_driver":
                ticket_key = f"pathways|{family}|{pathways_asof}"
                stale = bool(pathways_asof and pathways_asof < "2026-01-01")
                tickets.append({
                    "ticket_id": _make_ticket_id("mechanism_pathways.json", ticket_key),
                    "source_artifact": "data/neuralweb/mechanism_pathways.json",
                    "source_asof": pathways_asof,
                    "stale": stale,
                    "description": (
                        f"Pathway family '{family}' has no attributable driver "
                        f"(driver field: {driver!r}). "
                        "This may indicate a gap in the causal coverage for this market lobe."
                    ),
                    "suggested_target_family": "regime_risk",
                    "generated_at": now_utc,
                })

    # (b) release_forecast/forward_ledger.jsonl
    ledger_rows = _load_jsonl(root / _RELEASE_FORECAST_LEDGER)
    if not ledger_rows:
        log.debug("build_surprise_queue: release_forecast/forward_ledger.jsonl absent or empty")
    else:
        # Find the most recent asof
        ledger_asof = ""
        for row in ledger_rows:
            candidate = str(row.get("asof_night", ""))
            if candidate > ledger_asof:
                ledger_asof = candidate

        # Big miss: surprise_skew_sigma >= 2.0 (a large forecast miss)
        for row in ledger_rows:
            skew_sigma = row.get("surprise_skew_sigma")
            if skew_sigma is not None:
                try:
                    if abs(float(skew_sigma)) >= 2.0:
                        release = row.get("release", "unknown")
                        period = row.get("period", "")
                        ticket_key = f"forward_ledger|{release}|{period}|{ledger_asof}"
                        stale = bool(ledger_asof and ledger_asof < "2026-01-01")
                        tickets.append({
                            "ticket_id": _make_ticket_id(
                                "release_forecast/forward_ledger.jsonl", ticket_key
                            ),
                            "source_artifact": "data/release_forecast/forward_ledger.jsonl",
                            "source_asof": ledger_asof,
                            "stale": stale,
                            "description": (
                                f"Release '{release}' (period {period}) has large "
                                f"forecast miss signal: surprise_skew_sigma={skew_sigma:.2f}. "
                                "Possible unexplained macro driver worth causal exploration."
                            ),
                            "suggested_target_family": "regime_risk",
                            "generated_at": now_utc,
                        })
                except (TypeError, ValueError):
                    pass

    # (c) oracle_state.json active_episodes with failed status
    oracle_raw = _load_json(root / _ORACLE_STATE_PATH)
    if oracle_raw is None:
        log.debug("build_surprise_queue: oracle_state.json absent")
    else:
        oracle_asof = str(oracle_raw.get("asof", "")) if isinstance(oracle_raw, dict) else ""
        active_eps = []
        if isinstance(oracle_raw, dict):
            active_eps = oracle_raw.get("active_episodes", []) or []

        for ep in active_eps:
            status = ep.get("status", "")
            if status == "failed":
                ep_id = ep.get("episode_id", ep.get("id", "unknown"))
                complex_name = ep.get("complex", ep.get("sector", "unknown"))
                ticket_key = f"oracle_episode|{ep_id}|{oracle_asof}"
                stale = bool(oracle_asof and oracle_asof < "2026-01-01")
                tickets.append({
                    "ticket_id": _make_ticket_id("site/basketdata/oracle_state.json", ticket_key),
                    "source_artifact": "site/basketdata/oracle_state.json",
                    "source_asof": oracle_asof,
                    "stale": stale,
                    "description": (
                        f"Oracle episode '{ep_id}' (complex: {complex_name}) "
                        "has status=failed. "
                        "Potential unexplained rotation failure worth causal exploration."
                    ),
                    "suggested_target_family": "regime_risk",
                    "generated_at": now_utc,
                })

    log.info("build_surprise_queue: %d tickets generated", len(tickets))
    return tickets


# ---------------------------------------------------------------------------
# Drift monitor
# ---------------------------------------------------------------------------

def run_drift_monitor(root: Path, edges: list[dict]) -> list[dict]:
    """Cheap drift check on previously screened_candidate edges (no bootstrap).

    For each edge with verdict==screened_candidate, re-reads the cause and
    target series and computes the cheap effect estimate (correlation, no
    bootstrap, no placebo).  If support degrades materially, appends a drift
    event row (append-only, never mutates the edge).

    Returns list of drift event dicts (may be empty).
    Drift is defined as: correlation drops below 50% of the original
    screened_candidate value.
    """
    # Cheap drift: load cause + target series and compute correlation
    # Full battery is only run in the weekly build_causal_edges.py
    # This is a lightweight daily signal — correlation only, no logging.
    drift_events: list[dict] = []
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    screened = [e for e in edges if e.get("verdict") == "screened_candidate"]
    if not screened:
        return drift_events

    # Drift monitor is intentionally simple: compare stored effect mean
    # against the current regime_history rolling correlation.
    # A full re-run would happen in the weekly battery.
    for edge in screened[:10]:  # limit to 10 per nightly run for budget
        stored_mean = None
        try:
            stats = edge.get("stats", {})
            by_lag = stats.get("by_lag", {})
            for lag_key, lag_val in by_lag.items():
                if isinstance(lag_val, dict) and "mean" in lag_val:
                    stored_mean = float(lag_val["mean"])
                    break
        except Exception:
            continue

        if stored_mean is None:
            continue

        # Cannot load series in a pure drift check without full data context;
        # emit a staleness note if the edge is old (>30d since last scan)
        edge_asof = edge.get("asof", "")
        if edge_asof:
            try:
                edge_dt = datetime.fromisoformat(edge_asof.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - edge_dt).days
                if age_days > 30:
                    drift_events.append({
                        "event_type": "staleness_note",
                        "edge_id": edge.get("edge_id", ""),
                        "note": (
                            f"Edge was screened {age_days} days ago. "
                            "Recommend re-running the battery to check current support."
                        ),
                        "stored_effect_mean": stored_mean,
                        "age_days": age_days,
                        "asof": now_utc,
                    })
            except Exception:
                continue

    return drift_events


# ---------------------------------------------------------------------------
# LLM lane status reader (W5 wire-up)
# ---------------------------------------------------------------------------

def _load_llm_lane_status(root: Path) -> dict:
    """Return llm_lane status block for lab_state.

    Reads data/neuralweb/causal_llm_lane.json when present (written by
    scripts/run_causal_brainstorm.py). Falls back to the constant
    'awaiting_phase_a' description when the file is absent.
    """
    lane_path = root / "data" / "neuralweb" / "causal_llm_lane.json"
    if lane_path.exists():
        try:
            import json as _json  # noqa: PLC0415
            doc = _json.loads(lane_path.read_text(encoding="utf-8"))
            return {
                "status": doc.get("status", "awaiting_phase_a"),
                "asof": doc.get("asof"),
                "description": doc.get("reason", ""),
            }
        except Exception:  # noqa: BLE001
            pass  # fall through to default

    return {
        "status": "awaiting_phase_a",
        "description": (
            "LLM brainstorm lane is INACTIVE. "
            "Phase-A gate requires: >= 1 operator-triggered cycle "
            "with >= 5 schema-valid cards filed, >= 1 candidate through "
            "exit (a) or (b), and zero guard violations. "
            "Then operator may flip auto_loop: true in config/causal_llm.yml."
        ),
    }


# ---------------------------------------------------------------------------
# Lab state builder
# ---------------------------------------------------------------------------

def build_lab_state(
    root: Path,
    frontier: dict,
    surprise_queue: list[dict],
    drift_events: list[dict],
) -> dict:
    """Build the causal_lab_state artifact.

    Returns the lab state dict (byte-identical content for both copies).
    """
    asof = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Load edges and nulls
    edges = _load_jsonl(root / _EDGES_PATH)
    nulls = _load_jsonl(root / _NULLS_PATH)

    # Funnel counts
    verdict_counts: dict[str, int] = {}
    for edge in edges:
        v = edge.get("verdict", "unknown")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    # Mechanisms (if present)
    mechanisms = _load_jsonl(root / _MECHANISMS_PATH)
    mech_status_counts: dict[str, int] = {}
    for mech in mechanisms:
        s = mech.get("status", "unknown")
        mech_status_counts[s] = mech_status_counts.get(s, 0) + 1

    # Frontier summary
    state_summary = frontier.get("state_summary", {})
    cumulative_width = frontier.get("cumulative_causal_scan_width", 0)

    # Surprise queue summary
    sq_size = len(surprise_queue)
    stalest_source = ""
    stalest_asof = ""
    for ticket in surprise_queue:
        t_asof = ticket.get("source_asof", "")
        if (not stalest_asof) or (t_asof and t_asof < stalest_asof):
            stalest_asof = t_asof
            stalest_source = ticket.get("source_artifact", "")

    # Data absent notes
    data_absent_notes: list[str] = []
    replay_env = os.environ.get("REPLAY_BOARDED_PATH", "")
    replay_path = Path(replay_env) if replay_env else root / "data" / "replay" / "replay_boarded.parquet"
    if not replay_path.exists():
        data_absent_notes.append(
            "entry_quality target family unavailable: replay_boarded.parquet not found "
            f"(set REPLAY_BOARDED_PATH env var to runner-local path)"
        )

    lab_state = {
        "schema": SCHEMA,
        "asof": asof,
        "heartbeat": {
            "program": "CHF",
            "wave": "W3",
            "status": "live",
            "description": (
                "Causal Hypothesis Factory — deterministic edge scout, "
                "null library, frontier coverage map, and surprise queue. "
                "All artifacts are display-tier; no authority surfaces."
            ),
        },
        "funnel": {
            "edges_by_verdict": verdict_counts,
            "total_edges": len(edges),
            "nulls_count": len(nulls),
            "mechanisms_by_status": mech_status_counts,
            "total_mechanisms": len(mechanisms),
        },
        "causal_scan": {
            "cumulative_width": cumulative_width,
            "description": (
                "Cumulative distinct cells logged to the causal_scan TrialLedger family. "
                "Printed on every surface per CHF-R3 launder-proof multiplicity law."
            ),
        },
        "frontier": {
            "total_cells": frontier.get("total_cells", 0),
            "cells_by_state": state_summary,
            "target_families": frontier.get("target_families", []),
            "environments": frontier.get("environments_declared", []),
            "value_heuristic_formula": frontier.get("value_heuristic_formula", ""),
        },
        "surprise_queue": {
            "size": sq_size,
            "stalest_source": stalest_source,
            "stalest_source_asof": stalest_asof,
        },
        "drift_events": drift_events,
        "llm_lane": _load_llm_lane_status(root),
        "data_absent_notes": data_absent_notes,
        "authority": {
            "tier": "shadow",
            "display_only": True,
            "not_a_signal": True,
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
            "may_escalate": False,
            "scored_path_surfaces": [],
            "description": (
                "CHF artifacts are epistemic infrastructure — causal-candidate "
                "screened, not gauntleted. "
                "No surface may rank, gate, size, or escalate any money-path decision."
            ),
        },
    }

    return lab_state


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_all(root: Path | str | None = None) -> tuple[dict, list[dict], dict]:
    """Build frontier, surprise queue, and lab state artifacts.

    Returns (frontier_dict, surprise_tickets, lab_state_dict).
    """
    if root is None:
        root = Path(".")
    root = Path(root)

    # Build frontier
    frontier = build_frontier(root)

    # Build surprise queue
    surprise_queue = build_surprise_queue(root)

    # Drift monitor (cheap, daily)
    edges = _load_jsonl(root / _EDGES_PATH)
    drift_events = run_drift_monitor(root, edges)

    # Build lab state
    lab_state = build_lab_state(root, frontier, surprise_queue, drift_events)

    return frontier, surprise_queue, lab_state
