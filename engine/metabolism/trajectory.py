"""engine.metabolism.trajectory — Whole-organism trajectory + traffic light (V2-A §5).

Appends to data/metabolism/trajectory.jsonl and computes a site-wide
GREEN/AMBER/RED roll-up field with a one-line human reason.

GATE CONDITIONS (prevents noise + regime-change from reading as decay):
    Emit AMBER/RED only when ALL of the following are true:
      1. At least K_WEEKS weeks of history exist (K_WEEKS from config, default 4).
      2. The magnitude of the shift is >= MIN_MAGNITUDE (default 0.05).
      3. A regime_tag is available from organism_state (not null).
    Else: emit GREEN with reason 'accruing' — no premature alarms.

DATA-ONLY in V2-A: the front-page fragment (traffic light widget) ships in V2-D
behind the UX gate.  This module writes the jsonl + a site projection file in
data/metabolism/ (not site/) so nothing bypasses the V2-D UX gate.

SCHEMA (one row appended per run):
{
  "schema":          "metabolism.trajectory.v1",
  "ts":              ISO-8601,
  "cycle_id":        str | null,
  "overall_signal":  "GREEN" | "AMBER" | "RED",
  "reason":          str,        # one-line human reason
  "regime_tag":      str | null,
  "fitness_delta":   float | null,
  "n_lobes":         int,
  "n_mature_lobes":  int,
  "label_counts":    dict,
  "gate_passed":     bool,
  "gate_reason":     str,
  "authority": { "is_context_only": true, ... }
}

NEVER-RAISE CONTRACT.
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.trajectory.v1"
TRAJECTORY_PATH = Path("data") / "metabolism" / "trajectory.jsonl"

# Gate thresholds
_K_WEEKS_DEFAULT = 4          # minimum weeks of history
_MIN_MAGNITUDE_DEFAULT = 0.05 # minimum fitness delta magnitude to emit AMBER/RED
_N_OBS_PER_WEEK = 5           # approximate observations per week (daily-engine cadence)

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


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _load_trajectory_history(root: Path, K_weeks: int) -> list[dict]:
    """Load the last K_weeks worth of trajectory rows."""
    p = root / TRAJECTORY_PATH
    if not p.exists():
        return []
    n_target = K_weeks * _N_OBS_PER_WEEK  # approximate
    rows: list[dict] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rows.insert(0, json.loads(line))
            except Exception:  # noqa: BLE001
                continue
            if len(rows) >= n_target:
                break
    except Exception as exc:  # noqa: BLE001
        log.warning("trajectory: cannot read history — %s", exc)
    return rows


def _extract_regime_tag(organism_state: dict) -> str | None:
    """Extract regime tag from organism_state (via cortex_memo or governance)."""
    # Try cortex memo
    cortex = organism_state.get("cortex_memo") or {}
    if isinstance(cortex, dict):
        # Common field names
        for key in ("regime_tag", "regime", "quad", "cycle_tag"):
            v = cortex.get(key)
            if v:
                return str(v)
    return None


def _compute_fitness_delta(history_rows: list[dict]) -> float | None:
    """Compute mean fitness delta between last and first quartile of history."""
    if len(history_rows) < 4:
        return None
    try:
        # Extract fitness values from rows
        values: list[float] = []
        for row in history_rows:
            lc = row.get("label_counts") or {}
            n_total = sum(lc.values()) if lc else 0
            if n_total > 0:
                n_compound = lc.get("compounding") or 0
                n_degrade = lc.get("degrading") or 0
                # Score: fraction compounding minus fraction degrading
                score = (n_compound - n_degrade) / n_total
                values.append(score)

        if len(values) < 4:
            return None

        k = max(1, len(values) // 4)
        early_mean = statistics.mean(values[:k])
        late_mean = statistics.mean(values[-k:])
        return late_mean - early_mean
    except Exception as exc:  # noqa: BLE001
        log.warning("trajectory._compute_fitness_delta: %s", exc)
        return None


def build_trajectory_row(
    organism_state: dict,
    cycle_id: str | None = None,
    root: Path | None = None,
    K_weeks: int = _K_WEEKS_DEFAULT,
    min_magnitude: float = _MIN_MAGNITUDE_DEFAULT,
) -> dict[str, Any]:
    """Build one trajectory row.

    NEVER raises.  Gate logic: AMBER/RED only when K_WEEKS of history exist
    + magnitude >= min_magnitude + regime_tag is available.
    """
    try:
        repo = _repo_root(root)
        ts = _now_ts()

        # Extract from organism_state
        whole_org = organism_state.get("whole_organism") or {}
        n_lobes = whole_org.get("n_lobes") or 0
        label_counts = whole_org.get("label_counts") or {}
        regime_tag = _extract_regime_tag(organism_state)

        # Count mature lobes (trajectory.maturity == 'ready')
        lobes = organism_state.get("lobes") or {}
        n_mature = sum(
            1 for l in lobes.values()
            if isinstance(l, dict) and (l.get("trajectory") or {}).get("maturity") == "ready"
        )

        # Load history for gate check
        history_rows = _load_trajectory_history(repo, K_weeks)
        n_history = len(history_rows)
        n_required = K_weeks * _N_OBS_PER_WEEK

        # Compute fitness delta
        fitness_delta = _compute_fitness_delta(history_rows)

        # Gate evaluation
        gate_passed = (
            n_history >= n_required
            and fitness_delta is not None
            and abs(fitness_delta) >= min_magnitude
            and regime_tag is not None
        )

        if not gate_passed:
            # Explain why gate did not pass
            gate_parts = []
            if n_history < n_required:
                gate_parts.append(f"history {n_history}/{n_required} obs")
            if fitness_delta is None or abs(fitness_delta or 0) < min_magnitude:
                gate_parts.append(f"magnitude {fitness_delta:.4f}" if fitness_delta is not None else "no delta")
            if regime_tag is None:
                gate_parts.append("no regime_tag")
            gate_reason = "accruing: " + "; ".join(gate_parts) if gate_parts else "accruing"
            overall_signal = "GREEN"
            reason = "accruing — insufficient history for AMBER/RED signal"
        else:
            gate_reason = "gate passed"
            # Determine signal based on fitness delta and label counts
            n_degrading = label_counts.get("degrading") or 0
            n_compounding = label_counts.get("compounding") or 0
            n_stagnating = label_counts.get("stagnating") or 0

            if fitness_delta < -min_magnitude or n_degrading > max(1, n_mature // 3):
                overall_signal = "RED"
                reason = (
                    f"Organism degrading: delta={fitness_delta:.3f}, "
                    f"{n_degrading} lobes degrading, {n_compounding} compounding "
                    f"(regime={regime_tag})"
                )
            elif fitness_delta < 0 or n_stagnating > n_compounding:
                overall_signal = "AMBER"
                reason = (
                    f"Organism stagnating: delta={fitness_delta:.3f}, "
                    f"{n_stagnating} lobes stagnating, {n_compounding} compounding "
                    f"(regime={regime_tag})"
                )
            else:
                overall_signal = "GREEN"
                reason = (
                    f"Organism healthy: delta={fitness_delta:.3f}, "
                    f"{n_compounding} lobes compounding "
                    f"(regime={regime_tag})"
                )

        return {
            "schema": SCHEMA,
            "ts": ts,
            "cycle_id": cycle_id,
            "overall_signal": overall_signal,
            "reason": reason,
            "regime_tag": regime_tag,
            "fitness_delta": fitness_delta,
            "n_lobes": n_lobes,
            "n_mature_lobes": n_mature,
            "label_counts": label_counts,
            "gate_passed": gate_passed,
            "gate_reason": gate_reason,
            "authority": AUTHORITY_BLOCK,
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("trajectory.build_trajectory_row: %s", exc)
        return {
            "schema": SCHEMA,
            "ts": _now_ts(),
            "cycle_id": cycle_id,
            "overall_signal": "GREEN",
            "reason": f"accruing (error: {exc})",
            "regime_tag": None,
            "fitness_delta": None,
            "n_lobes": 0,
            "n_mature_lobes": 0,
            "label_counts": {},
            "gate_passed": False,
            "gate_reason": f"error: {exc}",
            "authority": AUTHORITY_BLOCK,
        }


def append_trajectory_row(row: dict, root: Path | None = None) -> bool:
    """Append one row to the trajectory.jsonl.  Returns True on success.  NEVER-RAISE."""
    try:
        repo = _repo_root(root)
        p = repo / TRAJECTORY_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("trajectory.append_trajectory_row: %s", exc)
        return False


def run_trajectory(
    organism_state: dict | None = None,
    cycle_id: str | None = None,
    root: Path | None = None,
    lobe_id: str | None = None,
) -> dict[str, Any]:
    """Build and append a trajectory row.

    If organism_state is not provided, reads data/metabolism/organism_state.json.

    Parameters
    ----------
    lobe_id : str | None
        When provided, annotates the emitted row with a ``lobe_id`` field so
        that per-lobe callers can tag their contribution to the organism-wide
        trajectory.jsonl.  The strategic.build_trajectory_block consumer uses
        this field to filter rows to a specific lobe when present.

    NEVER-RAISE.  Returns the row.
    """
    try:
        repo = _repo_root(root)
        if organism_state is None:
            os_path = repo / "data" / "metabolism" / "organism_state.json"
            organism_state = _read_json(os_path) or {}

        row = build_trajectory_row(organism_state=organism_state, cycle_id=cycle_id, root=repo)

        # Annotate with lobe_id when provided (per-lobe capability).
        # strategic.build_trajectory_block already filters trajectory.jsonl by
        # a lobe field when present, so this annotation is consumed correctly.
        if lobe_id is not None:
            row["lobe_id"] = str(lobe_id)

        append_trajectory_row(row, root=repo)
        return row
    except Exception as exc:  # noqa: BLE001
        log.warning("trajectory.run_trajectory: %s", exc)
        return {}
