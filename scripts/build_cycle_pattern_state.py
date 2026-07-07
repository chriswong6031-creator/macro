"""Build the CPI→NW adapter artifact — data/neuralweb/cycle_pattern_state.json.

CPI P6 wave 1 (UI-HZ-1 / NW lobe). Promotion, not invention (the DT-NW-1 /
RUL-P5 pattern): compacts the already-computed cycle-pattern live state
(data/cycle_pattern/state_daily_live.parquet — latest row per entity, hazard
probabilities included), the W4.2 hazard gate ledger verdicts (read from the
model artifact via engine.hazard_score, never hardcoded), and the truth
registry summary (engine.cycle_pattern.truths.active_truths) into one small
committed JSON the Neural Web can cite as a governed display artifact.

DISPLAY-ONLY — authority ceiling (consumer_matrix.yml, lake_artifacts class):
the cortex may reference this artifact as turn-hazard CONTEXT; it may never
originate, score, or escalate from it. Forbidden consumers (board_rank,
oracle_escalation, sector_central_direction_score, position_sizing) are
untouched — this artifact must never feed them.

Fail-open: every input is guarded. A missing/unreadable input degrades to a
valid JSON with a note + empty lists, never a crash (CI runners have no
parquet lake). Deterministic ordering (sort by family, native_id) for stable
diffs.

Run:  python -m scripts.build_cycle_pattern_state
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

log = logging.getLogger("build_cycle_pattern_state")

SCHEMA = "neuralweb_cycle_pattern_state.v1"

# Output path relative to repo root (canonical; also declared in synapse.yml).
_OUT_PATH_REL = "data/neuralweb/cycle_pattern_state.json"

# Input paths relative to repo root.
_LIVE_PATH_REL = "data/cycle_pattern/state_daily_live.parquet"

# Repo root inferred from this file's location.
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Authority ceiling string — mirrored in the synapse notes + cortex tool description.
_CEILING_NOTE = (
    "DISPLAY-ONLY ceiling (CPI consumer matrix): turn-hazard probabilities and "
    "phase state are context for display surfaces and the NW cortex only. "
    "They may never originate, score, or escalate a signal, and must never "
    "feed board_rank, oracle_escalation, sector_central_direction_score, or "
    "position_sizing. Cells whose gate verdict is PRIOR carry the "
    "family-stratified KM base rate, not a validated model output."
)

_HORIZONS = ("1m", "3m", "6m")
_DIRECTIONS = ("up", "down")

_N_LATEST_TRUTHS = 5


def _fnum(v, ndigits: int = 4):
    """NaN/None-safe float rounding (parquet NaN must become JSON null)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, ndigits)


def _fstr(v):
    """NaN/None-safe string (pandas NaN → None)."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v)
    return s if s and s.lower() != "nan" else None


def _gate_status(notes: list[str]) -> tuple[dict, str | None]:
    """Read the W4.2 hazard gate verdicts from the model ledger artifact.

    Uses engine.hazard_score's epoch/path constants as the single source of
    truth (never a second hardcoded epoch). Returns ({direction: {h: verdict}},
    model_epoch) — empty dict + None when the artifact is absent/unreadable.
    """
    try:
        from engine.hazard_score import _MODEL_PATH  # noqa: PLC0415
        model_path = Path(_MODEL_PATH)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"engine.hazard_score unavailable ({exc}) — gate_status empty")
        return {}, None

    if not model_path.exists():
        notes.append(f"hazard model ledger absent ({model_path.name}) — gate_status empty")
        return {}, None

    try:
        model = json.loads(model_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        notes.append(f"hazard model ledger unreadable ({exc}) — gate_status empty")
        return {}, None

    ledger = model.get("ledger") or {}
    out: dict = {}
    for direction in _DIRECTIONS:
        cells = ledger.get(direction) or {}
        out[direction] = {}
        for h in _HORIZONS:
            cell = cells.get(h) or {}
            out[direction][h] = str(cell.get("verdict") or "PRIOR")
    epoch = _fstr(model.get("turn_def_version"))
    return out, epoch


def _entities(notes: list[str]) -> list[dict]:
    """Latest row per entity from state_daily_live.parquet (hazard columns kept).

    Deterministic ordering: (family, native_id). Unmapped rows are kept with
    entity_id=null (the live view's never-silently-dropped contract).
    """
    live_path = _REPO_ROOT / _LIVE_PATH_REL
    if not live_path.exists():
        notes.append(f"{_LIVE_PATH_REL} absent — entities empty")
        return []

    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(live_path)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"{_LIVE_PATH_REL} unreadable ({exc}) — entities empty")
        return []

    if df.empty:
        notes.append(f"{_LIVE_PATH_REL} has no rows — entities empty")
        return []

    try:
        # Identity key: entity_id when mapped, else native_id (unmapped kept).
        df = df.copy()
        df["_key"] = df["entity_id"].where(df["entity_id"].notna(), df["native_id"])
        df = df.sort_values(["_key", "date"], kind="stable")
        latest = df.groupby("_key", as_index=False, sort=True).tail(1)

        rows: list[dict] = []
        for _, r in latest.iterrows():
            phase = _fstr(r.get("phase_v2")) or _fstr(r.get("phase"))
            d = r.get("date")
            rows.append({
                "entity_id": _fstr(r.get("entity_id")),
                "native_id": _fstr(r.get("native_id")),
                "family": _fstr(r.get("family")),
                "phase_v2": phase,
                "hazard_1m_p": _fnum(r.get("hazard_1m_p")),
                "hazard_3m_p": _fnum(r.get("hazard_3m_p")),
                "hazard_6m_p": _fnum(r.get("hazard_6m_p")),
                "hazard_src": {
                    "1m": _fstr(r.get("hazard_1m_src")),
                    "3m": _fstr(r.get("hazard_3m_src")),
                    "6m": _fstr(r.get("hazard_6m_src")),
                },
                "date": (str(d.date()) if hasattr(d, "date") else _fstr(d)),
            })
        rows.sort(key=lambda e: (e["family"] or "", e["native_id"] or ""))
        return rows
    except Exception as exc:  # noqa: BLE001
        notes.append(f"entity extraction failed ({exc}) — entities empty")
        return []


def _truth_summary(notes: list[str]) -> dict:
    """Counts + latest ids from the truth registry (active_truths only)."""
    empty = {"n_active": 0, "n_promoted_null": 0, "latest_truth_ids": []}
    try:
        from engine.cycle_pattern.truths import active_truths  # noqa: PLC0415
        active = active_truths()
    except Exception as exc:  # noqa: BLE001
        notes.append(f"truth registry unreadable ({exc}) — truth_summary empty")
        return empty
    if not active:
        notes.append("truth registry empty — truth_summary zeroed")
        return empty
    latest = sorted(active, key=lambda r: (str(r.get("created") or ""), str(r.get("truth_id") or "")))
    return {
        "n_active": len(active),
        "n_promoted_null": sum(1 for r in active if r.get("status") == "promoted_null"),
        "latest_truth_ids": [r.get("truth_id") for r in latest[-_N_LATEST_TRUTHS:]],
    }


def build() -> dict:
    """Assemble and write data/neuralweb/cycle_pattern_state.json.

    Returns the emitted artifact dict (useful for testing). Never raises —
    degrades gracefully to a valid JSON with notes + empty lists.
    """
    t0 = time.perf_counter()
    out_path = _REPO_ROOT / _OUT_PATH_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    gate_status, model_epoch = _gate_status(notes)
    entities = _entities(notes)
    truth_summary = _truth_summary(notes)

    output: dict = {
        "schema": SCHEMA,
        "asof": date.today().isoformat(),
        "model_epoch": model_epoch,
        "gate_status": gate_status,
        "entities": entities,
        "truth_summary": truth_summary,
        "display_only": True,
        "note": _CEILING_NOTE,
    }
    if notes:
        output["degraded_notes"] = notes

    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info(
        "cycle_pattern_state: entities=%d gate_cells=%d truths_active=%d%s → %s in %.2fs",
        len(entities),
        sum(len(v) for v in gate_status.values()),
        truth_summary.get("n_active", 0),
        (" (DEGRADED: " + "; ".join(notes) + ")") if notes else "",
        out_path,
        time.perf_counter() - t0,
    )
    return output


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    build()


if __name__ == "__main__":
    main()
