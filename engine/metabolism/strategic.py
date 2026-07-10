"""engine.metabolism.strategic — Trajectory block + strategic gap (V3 W2, R-V3-4).

Two public functions for the autonomous Metabolism loops:

  build_trajectory_block(lobe, *, root, byte_cap)
      Compact markdown block: latest fitness-delta, slope over recent history,
      regime tag, and a plain-language classification.

  build_strategic_gap(organism_state, *, root, byte_cap)
      Cross-lobe ranked markdown block naming the single biggest strategic gap.

Both are:
  - Deterministic — no LLM, no network.
  - NEVER-RAISE — every path returns a safe string or dict fallback.
  - Display / context tier only — may NOT gate, rank, or size.

Classification thresholds (per organism_state.py convention):
  slope >  0.02  → compounding
  slope < -0.02  → declining
  -0.02 ≤ slope ≤ 0.02 → stagnating
  n < N_MIN      → accruing (insufficient-n)

N_MIN_TRAJECTORY = 3   (matches organism_state._N_MIN_TRAJECTORY)
K_RECENT         = 10  (last K rows for slope window; configurable per call)
"""
from __future__ import annotations

import json
import logging
import statistics
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

N_MIN_TRAJECTORY = 3   # minimum observations before we report a slope
K_RECENT_DEFAULT = 10  # default sliding window for slope
SLOPE_POS_THRESH = 0.02
SLOPE_NEG_THRESH = -0.02

TRAJECTORY_JSONL = ("data", "metabolism", "trajectory.jsonl")
ORGANISM_STATE_PATH = ("data", "metabolism", "organism_state.json")


# ── Repo root ──────────────────────────────────────────────────────────────────

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


# ── Internal loaders ───────────────────────────────────────────────────────────

def _load_trajectory_rows(root: Path, lobe: str | None = None) -> list[dict[str, Any]]:
    """Load trajectory.jsonl rows, optionally filtered to a lobe.

    Returns a list ordered oldest-first.  NEVER raises.
    """
    try:
        p = root.joinpath(*TRAJECTORY_JSONL)
        if not p.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if lobe is not None:
                    # trajectory.jsonl is organism-wide; if a lobe field exists, filter
                    row_lobe = row.get("lobe") or row.get("lobe_id")
                    if row_lobe is not None and row_lobe != lobe:
                        continue
                rows.append(row)
            except Exception:  # noqa: BLE001
                continue
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("strategic._load_trajectory_rows: %s", exc)
        return []


def _load_organism_state(root: Path) -> dict[str, Any]:
    """Load data/metabolism/organism_state.json.  Returns {} on any error."""
    try:
        p = root.joinpath(*ORGANISM_STATE_PATH)
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("strategic._load_organism_state: %s", exc)
        return {}


# ── Slope computation ──────────────────────────────────────────────────────────

def _classify_slope(
    slope: float | None,
    n: int,
    n_min: int = N_MIN_TRAJECTORY,
) -> str:
    """Map slope + n to a plain-language label."""
    if n < n_min:
        return f"accruing(insufficient-n: {n}/{n_min})"
    if slope is None:
        return "accruing(insufficient-n: no slope)"
    if slope > SLOPE_POS_THRESH:
        return "compounding"
    if slope < SLOPE_NEG_THRESH:
        return "declining"
    return "stagnating"


def _compute_slope_from_deltas(
    rows: list[dict[str, Any]],
    k: int = K_RECENT_DEFAULT,
) -> tuple[float | None, int]:
    """Compute slope as (mean of last-third fitness_delta) - (mean of first-third).

    Uses the `fitness_delta` field from trajectory rows.
    Returns (slope, n_used) where n_used is the number of rows with a valid delta.
    NEVER raises.
    """
    try:
        deltas: list[float] = []
        for row in rows[-k:]:
            v = row.get("fitness_delta")
            if v is not None:
                try:
                    deltas.append(float(v))
                except Exception:  # noqa: BLE001
                    continue
        n = len(deltas)
        if n < N_MIN_TRAJECTORY:
            return None, n
        kk = max(1, n // 3)
        early = statistics.mean(deltas[:kk])
        late = statistics.mean(deltas[-kk:])
        return late - early, n
    except Exception as exc:  # noqa: BLE001
        log.warning("strategic._compute_slope_from_deltas: %s", exc)
        return None, 0


# ── Public API ─────────────────────────────────────────────────────────────────

def build_trajectory_block(
    lobe: str,
    *,
    root: Path | None = None,
    byte_cap: int = 1500,
    k: int = K_RECENT_DEFAULT,
) -> str:
    """Build a compact markdown trajectory block for one lobe.

    Parameters
    ----------
    lobe:
        Lobe identifier (e.g. ``"til"``).  Used to filter trajectory rows if a
        per-row lobe field exists; falls back to the organism-wide trajectory.jsonl.
    root:
        Repo root override for testing.
    byte_cap:
        Hard cap on returned string length (bytes, UTF-8).
    k:
        Window size for slope computation.

    Returns
    -------
    str — markdown block, always non-empty.  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        rows = _load_trajectory_rows(repo, lobe=lobe)

        # Also try lobe-specific fitness history if trajectory rows are sparse
        if not rows:
            rows = _load_trajectory_rows(repo, lobe=None)

        n_rows = len(rows)
        slope, n_used = _compute_slope_from_deltas(rows, k=k)
        classification = _classify_slope(slope, n_used)

        # Latest row for regime tag and latest delta
        latest = rows[-1] if rows else {}
        latest_delta = latest.get("fitness_delta")
        regime_tag = latest.get("regime_tag") or "—"
        latest_signal = latest.get("overall_signal") or "—"
        gate_reason = latest.get("gate_reason") or "—"

        slope_str = f"{slope:+.4f}" if slope is not None else "null"
        delta_str = f"{latest_delta:+.4f}" if latest_delta is not None else "null"

        lines = [
            f"## Trajectory — lobe: `{lobe}`",
            f"- **Classification:** {classification}",
            f"- **Slope** (Δ mean-last-third − mean-first-third, n={n_used}): {slope_str}",
            f"- **Latest fitness_delta:** {delta_str}",
            f"- **Regime tag:** {regime_tag}",
            f"- **Traffic light:** {latest_signal}",
            f"- **Gate reason:** {gate_reason}",
            f"- **History rows loaded:** {n_rows}",
        ]

        if n_used < N_MIN_TRAJECTORY:
            lines.append(
                f"\n> Accruing — {n_used} point(s) with valid fitness_delta; "
                f"need {N_MIN_TRAJECTORY} to classify trend. No trend inferred from sparse data."
            )

        text = "\n".join(lines)
        encoded = text.encode("utf-8")
        if len(encoded) > byte_cap:
            text = encoded[:byte_cap].decode("utf-8", errors="ignore") + "\n...(truncated)"
        return text

    except Exception as exc:  # noqa: BLE001
        log.warning("strategic.build_trajectory_block: %s", exc)
        return f"## Trajectory — lobe: `{lobe}`\n(unavailable: {exc})"


def build_strategic_gap(
    organism_state: dict[str, Any] | None = None,
    *,
    root: Path | None = None,
    byte_cap: int = 1500,
) -> str:
    """Build a compact markdown strategic-gap block across all lobes.

    Classifies each lobe compounding-vs-stagnating-vs-declining, then names
    the single biggest strategic gap (worst sustained slope lobe).

    Closes R-V2-1: "compounding vs stagnating lobes, trajectory slope, biggest
    strategic gap."

    Parameters
    ----------
    organism_state:
        Pre-loaded organism_state dict.  If None, loads from disk.
    root:
        Repo root override for testing.
    byte_cap:
        Hard cap on returned string length.

    Returns
    -------
    str — markdown block.  NEVER raises.
    """
    try:
        repo = _repo_root(root)

        if organism_state is None:
            organism_state = _load_organism_state(repo)

        if not organism_state:
            return (
                "## Strategic Gap\n"
                "(honest null — organism_state absent or empty; accruing)"
            )

        lobes: dict[str, Any] = organism_state.get("lobes") or {}
        if not lobes:
            return (
                "## Strategic Gap\n"
                "(honest null — no lobes in organism_state; accruing)"
            )

        # Build per-lobe summary rows
        rows: list[dict[str, Any]] = []
        for lobe_id, lrec in lobes.items():
            if not isinstance(lrec, dict):
                continue
            traj = lrec.get("trajectory") or {}
            slope = traj.get("slope")
            label = traj.get("label", "accruing")
            maturity = traj.get("maturity", "accruing")
            n_obs = traj.get("n_obs", 0)
            rows.append({
                "lobe_id": lobe_id,
                "slope": slope,
                "label": label,
                "maturity": maturity,
                "n_obs": n_obs,
            })

        if not rows:
            return (
                "## Strategic Gap\n"
                "(honest null — no composable lobe records; accruing)"
            )

        # Sort: degrading < stagnating < compounding < accruing, then by slope asc
        def _sort_key(r: dict) -> tuple:
            label = r.get("label", "accruing")
            slope = r.get("slope") or 0.0
            order = {
                "degrading": 0,
                "stagnating": 1,
                "compounding": 2,
                "accruing": 3,
            }
            return (order.get(label, 3), slope)

        rows_sorted = sorted(rows, key=_sort_key)

        # Biggest gap = the worst (first after sort, only if maturity=ready)
        mature_rows = [r for r in rows_sorted if r.get("maturity") == "ready"]
        biggest_gap: str
        if mature_rows:
            biggest_gap = mature_rows[0]["lobe_id"]
        else:
            biggest_gap = "insufficient data (all lobes accruing)"

        # Label counts
        label_counts: dict[str, int] = {}
        for r in rows:
            label_counts[r["label"]] = label_counts.get(r["label"], 0) + 1

        # Render ranked table
        table_lines = [
            "## Strategic Gap",
            f"- **Biggest gap:** `{biggest_gap}`",
            "- **Label counts:** "
            + ", ".join(f"{k}={v}" for k, v in sorted(label_counts.items())),
            "",
            "### Lobe rankings (worst first)",
            "| lobe | label | slope | n_obs | maturity |",
            "|------|-------|-------|-------|----------|",
        ]
        for r in rows_sorted:
            slope_str = f"{r['slope']:+.4f}" if r["slope"] is not None else "null"
            table_lines.append(
                f"| {r['lobe_id']} | {r['label']} | {slope_str} | {r['n_obs']} | {r['maturity']} |"
            )

        text = "\n".join(table_lines)
        encoded = text.encode("utf-8")
        if len(encoded) > byte_cap:
            text = encoded[:byte_cap].decode("utf-8", errors="ignore") + "\n...(truncated)"
        return text

    except Exception as exc:  # noqa: BLE001
        log.warning("strategic.build_strategic_gap: %s", exc)
        return f"## Strategic Gap\n(unavailable: {exc})"
