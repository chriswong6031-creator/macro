"""Shared regime stamp (engine/regime_label.py) — the macro quad each desk tags theses
with, so engine.desk_scorer reports hit-rate per regime. Stdlib leaf: no import cycle."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.regime_label import quad_label  # noqa: E402


def test_quad_label_reads_quad_name():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "data" / "regime").mkdir(parents=True)
        (root / "data" / "regime" / "latest.json").write_text(
            json.dumps({"quad": "Q1", "quad_name": "Goldilocks"}))
        assert quad_label(root) == "Goldilocks"


def test_quad_label_falls_back_to_quad():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "data" / "regime").mkdir(parents=True)
        (root / "data" / "regime" / "latest.json").write_text(json.dumps({"quad": "Q3"}))
        assert quad_label(root) == "Q3"


def test_quad_label_degrades_to_none():
    with tempfile.TemporaryDirectory() as d:
        assert quad_label(Path(d)) is None                # absent file → None, never raises


def test_no_import_cycle_for_consumers():
    """The stamp leaf must not pull desk_scorer/ai_desk into a cycle for any consumer."""
    import importlib
    for m in ("engine.regime_label", "engine.ai_desk", "engine.desk_scorer",
              "engine.policy_intent_desk", "engine.altdata_brain", "engine.demand_ledger"):
        importlib.import_module(m)
