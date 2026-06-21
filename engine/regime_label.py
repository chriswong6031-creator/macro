"""The canonical macro regime quad at a point in time — for stamping falsifiable theses.

Every Phase-C desk stamps each thesis with the regime it was logged under, so the shared
scorer (engine.desk_scorer.aggregate) can report hit-rate per regime (Minimum-Regime-
Performance): a signal that only works in one regime can't hide behind a blended average.

Kept as a tiny stdlib-only leaf so every desk can import it without an import cycle
(engine.desk_scorer already imports engine.ai_desk, so the shared reader can't live there).
"""
from __future__ import annotations

import json
from pathlib import Path


def quad_label(root) -> str | None:
    """The macro regime quad name from data/regime/latest.json (degrades to None)."""
    try:
        d = json.loads((Path(root) / "data" / "regime" / "latest.json").read_text())
        return d.get("quad_name") or d.get("quad") or None
    except Exception:  # noqa: BLE001
        return None
