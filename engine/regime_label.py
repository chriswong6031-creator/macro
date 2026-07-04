"""The canonical macro regime quad at a point in time — for stamping falsifiable theses.

Every Phase-C desk stamps each thesis with the regime it was logged under, so the shared
scorer (engine.desk_scorer.aggregate) can report hit-rate per regime (Minimum-Regime-
Performance): a signal that only works in one regime can't hide behind a blended average.

Kept as a tiny stdlib-only leaf so every desk can import it without an import cycle
(engine.desk_scorer already imports engine.ai_desk, so the shared reader can't live there).

Migration (W1 PR2): quad_label() now tries world_state.regime.quad_name first; falls
back to the legacy direct read of data/regime/latest.json.  Behavior-preserving: same
return value when stores are in sync.
"""
from __future__ import annotations

import json
from pathlib import Path


def quad_label(root) -> str | None:
    """The macro regime quad name — from world_state if fresh, else latest.json.

    Migration (W1 PR2): tries world_state first via engine.neuralweb.read; falls
    back to the legacy direct read of data/regime/latest.json on any failure.
    Behavior-preserving: returns the same value as before when stores are in sync.
    """
    try:
        from engine.neuralweb.read import load_world_state
        ws = load_world_state(root=root)
        if ws is not None:
            reg = ws.get("regime") or {}
            val = reg.get("quad_name") or reg.get("quad")
            if val is not None:
                return str(val)
    except Exception:  # noqa: BLE001
        pass

    # Legacy fallback: direct read of data/regime/latest.json
    try:
        d = json.loads((Path(root) / "data" / "regime" / "latest.json").read_text())
        return d.get("quad_name") or d.get("quad") or None
    except Exception:  # noqa: BLE001
        return None
