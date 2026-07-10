"""engine.metabolism.organism_state — Whole-organism holistic sensor (V2-A §1).

MIRRORS world_state.py's fail-open composition pattern.  Reads every available
lobe fitness card, health.json, the cortex memo, governance grant/deny rates, and
trial-ledger realized deltas.  Produces ONE stamped JSON that gives any consumer
a single canonical entry point for the organism's current vitality.

AUTHORITY BLOCK (mandatory on all organism_state artifacts):
    is_context_only = True     — never gates, never ranks, never scores
    display_only    = True
    may_rank / may_gate / may_size / may_escalate = False

FAIL-OPEN CONTRACT (mirrors world_state.py):
    Every sub-block read is fail-open.  A missing, corrupt, or unreadable source
    yields null for that block plus an entry in top-level 'gaps'.  build_organism_state()
    NEVER raises; it always returns a partial artifact.

TRAJECTORY SLOPE HONESTY RULE:
    Per-lobe trajectory slope = fitness delta over last K observations from
    fitness_history.jsonl (or til.json history key if present).
    When n < n_min_trajectory observations are available, value is None and
    maturity is 'accruing' — NEVER a fabricated number.

SCHEMA: metabolism.organism_state.v1
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.organism_state.v1"

# Minimum observations for a slope to be considered meaningful
_N_MIN_TRAJECTORY = 3

# Labels for per-lobe trajectory label
_LABEL_COMPOUNDING = "compounding"
_LABEL_STAGNATING = "stagnating"
_LABEL_DEGRADING = "degrading"
_LABEL_ACCRUING = "accruing"

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "shadow",
    "forbidden_uses": [
        "ranking", "sizing", "alert_escalation", "board_ordering",
        "mastermind_arming", "scored_path",
    ],
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("organism_state: unreadable json %s — %s", p, exc)
        return None


def _clean(v: Any) -> Any:
    """Coerce to JSON-safe type (mirrors world_state._clean)."""
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    type_name = type(v).__name__
    module_name = getattr(type(v), "__module__", "") or ""
    if "numpy" in module_name:
        if type_name.startswith(("int", "uint")):
            return int(v)
        if type_name.startswith("float"):
            fv = float(v)
            return None if (math.isnan(fv) or math.isinf(fv)) else fv
        if type_name.startswith("bool"):
            return bool(v)
        return str(v)
    return v


# ── Fitness card discovery ─────────────────────────────────────────────────────

def _discover_fitness_cards(root: Path) -> dict[str, Path]:
    """Discover all fitness card JSON files under data/metabolism/fitness/.

    Returns a dict of {lobe_id: path} for all *.json files found.
    Gracefully handles absent directory.
    """
    fitness_dir = root / "data" / "metabolism" / "fitness"
    result: dict[str, Path] = {}
    if not fitness_dir.exists():
        log.info("organism_state: fitness dir absent (%s)", fitness_dir)
        return result
    for p in sorted(fitness_dir.glob("*.json")):
        lobe_id = p.stem  # e.g. "til" from "til.json"
        result[lobe_id] = p
    return result


# ── Per-lobe trajectory slope ──────────────────────────────────────────────────

def _load_fitness_history(root: Path, lobe_id: str) -> list[dict]:
    """Load fitness_history.jsonl entries for a lobe.

    Returns list of dicts in chronological order (oldest first).
    """
    hist_path = root / "data" / "metabolism" / "fitness_history" / f"{lobe_id}.jsonl"
    if not hist_path.exists():
        return []
    rows: list[dict] = []
    try:
        for line in hist_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("organism_state: cannot read fitness_history %s — %s", hist_path, exc)
    return rows


def _extract_composite_fitness(card: dict) -> float | None:
    """Extract a single composite fitness value from a fitness card.

    Strategy: if the card has a top-level 'composite' or 'fitness_score' key, use it.
    Otherwise average the non-null sensor values.  Returns None if no values available.
    """
    composite = card.get("composite") or card.get("fitness_score")
    if composite is not None:
        try:
            return float(composite)
        except Exception:  # noqa: BLE001
            pass

    # Average ready sensors
    sensors = card.get("sensors") or {}
    values: list[float] = []
    for s in sensors.values():
        if not isinstance(s, dict):
            continue
        if s.get("maturity") == "ready" and s.get("value") is not None:
            try:
                values.append(float(s["value"]))
            except Exception:  # noqa: BLE001
                continue
    if not values:
        return None
    return sum(values) / len(values)


def _compute_trajectory(root: Path, lobe_id: str, card: dict) -> dict[str, Any]:
    """Compute trajectory slope and label for a lobe.

    Returns:
        slope:    float | None  — recent fitness delta (positive = improving)
        label:    str           — compounding|stagnating|degrading|accruing
        n_obs:    int           — number of observations used
        maturity: str           — 'ready' | 'accruing'
    """
    # Try fitness_history.jsonl first
    hist_rows = _load_fitness_history(root, lobe_id)

    # Fall back to history embedded in the card itself (til_fitness.v1 may not have it yet)
    if len(hist_rows) < _N_MIN_TRAJECTORY:
        card_hist = card.get("history") or []
        if isinstance(card_hist, list) and len(card_hist) >= _N_MIN_TRAJECTORY:
            hist_rows = card_hist

    n = len(hist_rows)
    if n < _N_MIN_TRAJECTORY:
        return {
            "slope": None,
            "label": _LABEL_ACCRUING,
            "n_obs": n,
            "maturity": "accruing",
            "note": f"accruing: {n}/{_N_MIN_TRAJECTORY} observations (need {_N_MIN_TRAJECTORY})",
        }

    # Extract fitness values in order
    values: list[float] = []
    for row in hist_rows:
        # Row may be the card dict itself (embedded history) or a jsonl row
        if isinstance(row, dict):
            v = _extract_composite_fitness(row)
            if v is None:
                # Try direct 'value' key (jsonl row format)
                raw = row.get("value") or row.get("fitness_score") or row.get("composite")
                if raw is not None:
                    try:
                        v = float(raw)
                    except Exception:  # noqa: BLE001
                        v = None
        else:
            v = None
        if v is not None:
            values.append(v)

    if len(values) < _N_MIN_TRAJECTORY:
        return {
            "slope": None,
            "label": _LABEL_ACCRUING,
            "n_obs": len(values),
            "maturity": "accruing",
            "note": (
                f"accruing: {len(values)}/{_N_MIN_TRAJECTORY} non-null fitness values "
                f"(need {_N_MIN_TRAJECTORY})"
            ),
        }

    # Slope = difference between the mean of the last third and the mean of the first third
    k = max(1, len(values) // 3)
    early_mean = statistics.mean(values[:k])
    late_mean = statistics.mean(values[-k:])
    slope = _clean(late_mean - early_mean)

    # Label
    if slope is None:
        label = _LABEL_ACCRUING
    elif slope > 0.02:
        label = _LABEL_COMPOUNDING
    elif slope < -0.02:
        label = _LABEL_DEGRADING
    else:
        label = _LABEL_STAGNATING

    return {
        "slope": slope,
        "label": label,
        "n_obs": len(values),
        "maturity": "ready",
        "note": None,
    }


# ── Per-lobe health status ─────────────────────────────────────────────────────

def _read_health(root: Path) -> dict[str, Any]:
    """Read health.json and return the lobes dict keyed by lobe id."""
    p = root / "data" / "neuralweb" / "health.json"
    raw = _read_json(p)
    if raw is None:
        return {}
    lobes_raw = raw.get("lobes") or {}
    # health.json lobes is a dict: {lobe_id: record}
    if isinstance(lobes_raw, dict):
        return lobes_raw
    # Some versions may be a list
    if isinstance(lobes_raw, list):
        return {r.get("id", f"unknown_{i}"): r for i, r in enumerate(lobes_raw)}
    return {}


# ── Cortex memo ───────────────────────────────────────────────────────────────

def _read_cortex_memo(root: Path) -> dict | None:
    p = root / "data" / "neuralweb" / "cortex" / "memo.json"
    raw = _read_json(p)
    if not isinstance(raw, dict):
        return None
    return {
        "as_of": raw.get("as_of") or raw.get("produced_at"),
        "status": raw.get("status"),
        "n_lobes_assessed": raw.get("n_lobes_assessed"),
        "overall_health": raw.get("overall_health"),
        "source": "data/neuralweb/cortex/memo.json",
    }


# ── Governance rates ──────────────────────────────────────────────────────────

def _read_governance_rates(root: Path) -> dict[str, Any]:
    """Compute grant/deny rates from governance.jsonl (metabolism events only)."""
    p = root / "data" / "neuralweb" / "governance.jsonl"
    if not p.exists():
        return {"grant_rate": None, "deny_rate": None, "n_events": 0,
                "source": str(p), "note": "governance.jsonl absent"}
    n_grant = 0
    n_deny = 0
    n_total = 0
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            et = row.get("event_type", "")
            if "metabolism" not in (row.get("target", "") + row.get("authored_by", "")).lower():
                continue
            n_total += 1
            if et == "metabolism_adjudication":
                outcome = (row.get("after") or {}).get("outcome", "")
                if outcome == "grant":
                    n_grant += 1
                elif outcome == "deny":
                    n_deny += 1
    except Exception as exc:  # noqa: BLE001
        log.warning("organism_state: governance.jsonl read failed — %s", exc)
        return {"grant_rate": None, "deny_rate": None, "n_events": 0, "note": str(exc)}

    return {
        "n_events": n_total,
        "n_grant": n_grant,
        "n_deny": n_deny,
        "grant_rate": _clean(n_grant / n_total) if n_total > 0 else None,
        "deny_rate": _clean(n_deny / n_total) if n_total > 0 else None,
        "source": "data/neuralweb/governance.jsonl",
    }


# ── Trial ledger realized deltas ──────────────────────────────────────────────

def _read_trial_ledger(root: Path) -> dict[str, Any]:
    """Summarize realized deltas from data/trial_ledger.jsonl."""
    p = root / "data" / "trial_ledger.jsonl"
    if not p.exists():
        return {"n_trials": 0, "n_confirmed": 0, "n_tripped": 0,
                "confirmed_rate": None, "source": str(p), "note": "absent"}
    n_total = 0
    n_confirmed = 0
    n_tripped = 0
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            # Only metabolism family
            if "metabolism" not in row.get("fdr_family", "").lower():
                continue
            n_total += 1
            outcome = row.get("realized_outcome") or row.get("outcome") or ""
            if outcome == "CONFIRMED":
                n_confirmed += 1
            elif outcome == "FALSIFIER_TRIPPED":
                n_tripped += 1
    except Exception as exc:  # noqa: BLE001
        log.warning("organism_state: trial_ledger read failed — %s", exc)
        return {"n_trials": 0, "n_confirmed": 0, "n_tripped": 0, "note": str(exc)}

    return {
        "n_trials": n_total,
        "n_confirmed": n_confirmed,
        "n_tripped": n_tripped,
        "confirmed_rate": _clean(n_confirmed / n_total) if n_total > 0 else None,
        "source": "data/trial_ledger.jsonl",
    }


# ── Per-lobe composer ─────────────────────────────────────────────────────────

def _compose_lobe(
    lobe_id: str,
    card: dict,
    health_rec: dict | None,
    root: Path,
) -> dict[str, Any]:
    """Build the per-lobe organism record.

    Includes:
    - fitness sensor values from the card
    - trajectory slope + label
    - health status
    - stale_legs: names any missing inputs
    """
    sensors = card.get("sensors") or {}
    trajectory = _compute_trajectory(root, lobe_id, card)

    # Identify stale legs (sensors with maturity='accruing' and value=None)
    stale_legs: list[str] = []
    for sensor_name, sensor_rec in sensors.items():
        if isinstance(sensor_rec, dict):
            if sensor_rec.get("maturity") == "accruing" and sensor_rec.get("value") is None:
                stale_legs.append(sensor_name)
            elif sensor_rec.get("note") and "absent" in str(sensor_rec.get("note", "")).lower():
                if sensor_name not in stale_legs:
                    stale_legs.append(sensor_name)

    health_status = None
    health_age_hours = None
    if isinstance(health_rec, dict):
        health_status = health_rec.get("status")
        health_age_hours = health_rec.get("age_hours")

    return {
        "lobe_id": lobe_id,
        "fitness_card_as_of": card.get("as_of"),
        "fitness_maturity": card.get("maturity"),
        "sensors": {
            name: {
                "value": _clean(s.get("value")),
                "n": s.get("n"),
                "maturity": s.get("maturity"),
                "note": s.get("note"),
            }
            for name, s in sensors.items()
            if isinstance(s, dict)
        },
        "composite_fitness": _clean(_extract_composite_fitness(card)),
        "trajectory": trajectory,
        "health_status": health_status,
        "health_age_hours": health_age_hours,
        "stale_legs": stale_legs,
    }


# ── Biggest-gap selector ──────────────────────────────────────────────────────

def _select_biggest_gap(lobes: list[dict]) -> str:
    """Deterministic pick: the lobe with the worst trajectory that has matured data.

    'Worst' = degrading > stagnating, breaking ties by steepest negative slope.
    If no lobe has matured trajectory data, returns 'insufficient data'.
    This is NOT an LLM judgment — purely deterministic.
    """
    mature_lobes = [
        l for l in lobes
        if l.get("trajectory", {}).get("maturity") == "ready"
    ]
    if not mature_lobes:
        return "insufficient data"

    # Sort: degrading first, then stagnating, then by slope ascending (worst = most negative)
    def _sort_key(l: dict) -> tuple:
        traj = l.get("trajectory", {})
        label = traj.get("label", "")
        slope = traj.get("slope") or 0.0
        label_rank = 0 if label == _LABEL_DEGRADING else (1 if label == _LABEL_STAGNATING else 2)
        return (label_rank, slope)

    sorted_lobes = sorted(mature_lobes, key=_sort_key)
    worst = sorted_lobes[0]
    return worst.get("lobe_id", "unknown")


# ── Main builder ──────────────────────────────────────────────────────────────

def build_organism_state(root: Path | None = None) -> dict[str, Any]:
    """Build the whole-organism state rollup.

    Fail-open: always returns a partial artifact, never raises.

    Parameters
    ----------
    root : Path | None
        Repo root override for testing.

    Returns
    -------
    dict — organism_state (schema metabolism.organism_state.v1).
    """
    try:
        return _build_organism_state_inner(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("organism_state.build_organism_state: fatal error — %s", exc)
        return {
            "schema": SCHEMA,
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "produced_at": datetime.now(timezone.utc).isoformat(),
            "lobes": {},
            "whole_organism": {
                "n_lobes": 0,
                "label_counts": {},
                "biggest_gap": "insufficient data",
            },
            "cortex_memo": None,
            "governance": None,
            "trial_ledger": None,
            "gaps": [f"fatal error in build_organism_state: {exc}"],
            "authority": AUTHORITY_BLOCK,
        }


def _build_organism_state_inner(root: Path | None) -> dict[str, Any]:
    """Inner builder — allowed to raise; wrapped by build_organism_state."""
    repo = _repo_root(root)
    gaps: list[str] = []

    # 1. Discover all fitness cards
    fitness_cards = _discover_fitness_cards(repo)
    if not fitness_cards:
        gaps.append("no fitness cards found in data/metabolism/fitness/")

    # 2. Read health.json lobe roster
    try:
        health_lobes = _read_health(repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("organism_state: health read failed — %s", exc)
        health_lobes = {}
        gaps.append(f"health.json unreadable: {exc}")

    # 3. Read cortex memo
    try:
        cortex_memo = _read_cortex_memo(repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("organism_state: cortex memo read failed — %s", exc)
        cortex_memo = None
        gaps.append(f"cortex/memo.json unreadable: {exc}")

    # 4. Governance rates
    try:
        governance = _read_governance_rates(repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("organism_state: governance read failed — %s", exc)
        governance = None
        gaps.append(f"governance.jsonl unreadable: {exc}")

    # 5. Trial ledger
    try:
        trial_ledger = _read_trial_ledger(repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("organism_state: trial_ledger read failed — %s", exc)
        trial_ledger = None
        gaps.append(f"trial_ledger.jsonl unreadable: {exc}")

    # 6. Compose per-lobe records
    all_lobe_ids = set(fitness_cards.keys()) | set(health_lobes.keys())
    lobes: dict[str, Any] = {}

    for lobe_id in sorted(all_lobe_ids):
        try:
            card_path = fitness_cards.get(lobe_id)
            card = _read_json(card_path) if card_path else None
            if card is None:
                # No fitness card — stub with honest null
                card = {
                    "as_of": None,
                    "maturity": "accruing",
                    "sensors": {},
                    "notes": "no fitness card yet",
                }
                gaps.append(f"lobe {lobe_id}: fitness card absent — honest null")

            health_rec = health_lobes.get(lobe_id)
            lobes[lobe_id] = _compose_lobe(lobe_id, card, health_rec, repo)

        except Exception as exc:  # noqa: BLE001
            log.warning("organism_state: lobe %s compose failed — %s", lobe_id, exc)
            lobes[lobe_id] = {
                "lobe_id": lobe_id,
                "error": str(exc),
                "trajectory": {"slope": None, "label": _LABEL_ACCRUING, "maturity": "accruing"},
            }
            gaps.append(f"lobe {lobe_id}: compose error: {exc}")

    # 7. Whole-organism block
    lobe_list = list(lobes.values())
    label_counts: dict[str, int] = {}
    for l in lobe_list:
        traj = l.get("trajectory") or {}
        label = traj.get("label", _LABEL_ACCRUING)
        label_counts[label] = label_counts.get(label, 0) + 1

    biggest_gap = _select_biggest_gap(lobe_list)

    whole_organism = {
        "n_lobes": len(lobes),
        "label_counts": label_counts,
        "biggest_gap": biggest_gap,
        "note": "biggest_gap = deterministic pick (worst trajectory with matured data); not LLM judgment",
    }

    return {
        "schema": SCHEMA,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "lobes": lobes,
        "whole_organism": whole_organism,
        "cortex_memo": cortex_memo,
        "governance": governance,
        "trial_ledger": trial_ledger,
        "gaps": gaps,
        "authority": AUTHORITY_BLOCK,
    }
