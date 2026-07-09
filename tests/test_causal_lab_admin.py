"""tests/test_causal_lab_admin.py — admin Causal Lab panel tests (CHF-R13).

All tests are hermetic.  Monkeypatches the path constants in admin.causal_lab
so no real filesystem artifacts are required.

Test coverage:
1.  panel_ok_always_when_absent       — ok=True even when all artifacts absent
2.  panel_is_context_only             — is_context_only, annotate_only, not_a_signal
3.  panel_reads_lab_state_primary     — reads site/ copy first
4.  panel_falls_back_to_data          — uses data/ copy when site/ absent
5.  panel_funnel_counts               — funnel block populated from lab state
6.  panel_scan_width                  — scan_width from causal_scan block
7.  panel_frontier_summary            — frontier block fields
8.  panel_surprise_queue              — surprise_queue block fields
9.  panel_llm_lane_status             — llm_lane block
10. panel_latest_edges_from_jsonl     — latest_edges populated from causal_edges.jsonl
11. panel_latest_edges_cap            — at most 5 edges shown
12. panel_audit_counts_when_present   — audit_counts populated when audit artifact present
13. panel_audit_counts_when_absent    — audit_counts available=False when audit absent
14. panel_latest_annotations          — latest_audit_annotations up to 5 entries
15. panel_data_absent_notes           — data_absent_notes propagated
16. panel_import_clean                — admin.causal_lab imports without error
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import admin.causal_lab as causal_lab_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_LAB_STATE = {
    "schema": "neuralweb.causal_lab_state.v1",
    "asof": "2026-07-09T12:00:00Z",
    "heartbeat": {
        "program": "CHF",
        "wave": "W6",
        "status": "live",
        "description": "test lab state",
    },
    "funnel": {
        "edges_by_verdict": {"null": 2, "screened_candidate": 1},
        "total_edges": 3,
        "nulls_count": 2,
        "mechanisms_by_status": {"inbox": 1},
        "total_mechanisms": 1,
    },
    "causal_scan": {
        "cumulative_width": 24,
        "description": "24 cells logged",
    },
    "frontier": {
        "total_cells": 42,
        "cells_by_state": {"unexplored": 40, "null_basin": 2},
        "target_families": ["regime_risk"],
        "environments": ["full"],
    },
    "surprise_queue": {
        "size": 3,
        "stalest_source": "mechanism_pathways",
        "stalest_source_asof": "2026-07-08",
    },
    "llm_lane": {
        "status": "awaiting_phase_a",
        "description": "Phase-A gate not yet met",
    },
    "data_absent_notes": ["replay_boarded.parquet not found"],
}

_EDGE_ROW = {
    "edge_id": "e_abc123",
    "cause_feature_id": "breadth__pct_above_50",
    "target_id": "regime_worsening_5d",
    "verdict": "null",
    "concerns": ["degenerate target"],
    "scanned_at": "2026-07-09T10:00:00Z",
}

_AUDIT_ARTIFACT = {
    "schema": "neuralweb.causal_confluence_audit.v1",
    "asof": "2026-07-09T11:00:00Z",
    "counts": {
        "duplicate_exposure": 2,
        "shared_parent_suspect": 0,
        "collider_risk": 1,
        "total": 3,
    },
    "duplicate_exposure": [
        {
            "rule_id": "CHF-R10-DE-001",
            "annotation_type": "duplicate_exposure",
            "display_text": "test annotation 1",
        },
        {
            "rule_id": "CHF-R10-DE-002",
            "annotation_type": "duplicate_exposure",
            "display_text": "test annotation 2",
        },
    ],
    "shared_parent_suspect": [],
    "collider_risk": [
        {
            "rule_id": "CHF-R10-CR-001",
            "annotation_type": "collider_risk",
            "display_text": "test collider warning",
        }
    ],
}


def _write_lab(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


# ---------------------------------------------------------------------------
# Context manager for monkeypatching module paths
# ---------------------------------------------------------------------------

class _PatchedPaths:
    """Context manager: redirect all causal_lab path constants to tmp_path."""

    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self._original: dict = {}

    def __enter__(self):
        import admin.causal_lab as m  # noqa: PLC0415
        attrs = ["_LAB_PRIMARY", "_LAB_FALLBACK", "_EDGES", "_NULLS", "_MECHANISMS", "_AUDIT"]
        for attr in attrs:
            self._original[attr] = getattr(m, attr)

        m._LAB_PRIMARY  = self.tmp / "site" / "neuralwebdata" / "causal_lab_state.json"
        m._LAB_FALLBACK = self.tmp / "data" / "neuralweb" / "causal_lab_state.json"
        m._EDGES        = self.tmp / "data" / "neuralweb" / "causal_edges.jsonl"
        m._NULLS        = self.tmp / "data" / "neuralweb" / "causal_nulls.jsonl"
        m._MECHANISMS   = self.tmp / "data" / "neuralweb" / "causal_mechanisms.jsonl"
        m._AUDIT        = self.tmp / "data" / "neuralweb" / "causal_confluence_audit.json"
        return m

    def __exit__(self, *args):
        import admin.causal_lab as m  # noqa: PLC0415
        for attr, val in self._original.items():
            setattr(m, attr, val)


# ---------------------------------------------------------------------------
# 1. panel_ok_always_when_absent
# ---------------------------------------------------------------------------

def test_panel_ok_always_when_absent(tmp_path):
    with _PatchedPaths(tmp_path):
        result = causal_lab_mod.panel()
    assert result["ok"] is True
    assert "error" in result


# ---------------------------------------------------------------------------
# 2. panel_is_context_only
# ---------------------------------------------------------------------------

def test_panel_is_context_only(tmp_path):
    with _PatchedPaths(tmp_path):
        result = causal_lab_mod.panel()
    assert result["is_context_only"] is True
    assert result["annotate_only"] is True
    assert result["not_a_signal"] is True


# ---------------------------------------------------------------------------
# 3. panel_reads_lab_state_primary
# ---------------------------------------------------------------------------

def test_panel_reads_lab_state_primary(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        result = causal_lab_mod.panel()
    assert result["ok"] is True
    assert result.get("asof") == "2026-07-09T12:00:00Z"
    assert "error" not in result


# ---------------------------------------------------------------------------
# 4. panel_falls_back_to_data
# ---------------------------------------------------------------------------

def test_panel_falls_back_to_data(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        # Only write fallback, not primary
        _write_lab(m._LAB_FALLBACK, _LAB_STATE)
        result = causal_lab_mod.panel()
    assert result["ok"] is True
    assert result.get("asof") == "2026-07-09T12:00:00Z"


# ---------------------------------------------------------------------------
# 5. panel_funnel_counts
# ---------------------------------------------------------------------------

def test_panel_funnel_counts(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        result = causal_lab_mod.panel()
    fn = result["funnel"]
    assert fn["total_edges"] == 3
    assert fn["nulls_count"] == 2
    assert fn["edges_by_verdict"]["null"] == 2


# ---------------------------------------------------------------------------
# 6. panel_scan_width
# ---------------------------------------------------------------------------

def test_panel_scan_width(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        result = causal_lab_mod.panel()
    sw = result["scan_width"]
    assert sw["cumulative_width"] == 24


# ---------------------------------------------------------------------------
# 7. panel_frontier_summary
# ---------------------------------------------------------------------------

def test_panel_frontier_summary(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        result = causal_lab_mod.panel()
    fr = result["frontier"]
    assert fr["total_cells"] == 42
    assert fr["cells_by_state"]["unexplored"] == 40


# ---------------------------------------------------------------------------
# 8. panel_surprise_queue
# ---------------------------------------------------------------------------

def test_panel_surprise_queue(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        result = causal_lab_mod.panel()
    sq = result["surprise_queue"]
    assert sq["size"] == 3
    assert sq["stalest_source"] == "mechanism_pathways"


# ---------------------------------------------------------------------------
# 9. panel_llm_lane_status
# ---------------------------------------------------------------------------

def test_panel_llm_lane_status(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        result = causal_lab_mod.panel()
    ll = result["llm_lane"]
    assert ll["status"] == "awaiting_phase_a"


# ---------------------------------------------------------------------------
# 10. panel_latest_edges_from_jsonl
# ---------------------------------------------------------------------------

def test_panel_latest_edges_from_jsonl(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        _write_jsonl(m._EDGES, [_EDGE_ROW])
        result = causal_lab_mod.panel()
    edges = result["latest_edges"]
    assert len(edges) == 1
    assert edges[0]["edge_id"] == "e_abc123"
    assert edges[0]["verdict"] == "null"
    assert edges[0]["n_concerns"] == 1
    assert result["n_edges"] == 1


# ---------------------------------------------------------------------------
# 11. panel_latest_edges_cap
# ---------------------------------------------------------------------------

def test_panel_latest_edges_cap(tmp_path):
    """At most 5 edges shown regardless of how many exist."""
    rows = [
        {**_EDGE_ROW, "edge_id": f"e_{i:03d}", "scanned_at": f"2026-07-0{i+1}T10:00:00Z"}
        for i in range(10)
    ]
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        _write_jsonl(m._EDGES, rows)
        result = causal_lab_mod.panel()
    assert len(result["latest_edges"]) <= 5
    assert result["n_edges"] == 10  # total count still shows 10


# ---------------------------------------------------------------------------
# 12. panel_audit_counts_when_present
# ---------------------------------------------------------------------------

def test_panel_audit_counts_when_present(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        m._AUDIT.parent.mkdir(parents=True, exist_ok=True)
        m._AUDIT.write_text(json.dumps(_AUDIT_ARTIFACT), encoding="utf-8")
        result = causal_lab_mod.panel()
    ac = result["audit_counts"]
    assert ac["available"] is True
    assert ac["duplicate_exposure"] == 2
    assert ac["collider_risk"] == 1
    assert ac["total"] == 3


# ---------------------------------------------------------------------------
# 13. panel_audit_counts_when_absent
# ---------------------------------------------------------------------------

def test_panel_audit_counts_when_absent(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        # _AUDIT file NOT written
        result = causal_lab_mod.panel()
    ac = result["audit_counts"]
    assert ac["available"] is False


# ---------------------------------------------------------------------------
# 14. panel_latest_annotations
# ---------------------------------------------------------------------------

def test_panel_latest_annotations(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        m._AUDIT.parent.mkdir(parents=True, exist_ok=True)
        m._AUDIT.write_text(json.dumps(_AUDIT_ARTIFACT), encoding="utf-8")
        result = causal_lab_mod.panel()
    anns = result["latest_audit_annotations"]
    assert len(anns) >= 1
    assert len(anns) <= 5  # capped
    assert anns[0]["rule_id"].startswith("CHF-R10-")


# ---------------------------------------------------------------------------
# 15. panel_data_absent_notes
# ---------------------------------------------------------------------------

def test_panel_data_absent_notes(tmp_path):
    with _PatchedPaths(tmp_path) as m:
        _write_lab(m._LAB_PRIMARY, _LAB_STATE)
        result = causal_lab_mod.panel()
    notes = result["data_absent_notes"]
    assert isinstance(notes, list)
    assert len(notes) == 1
    assert "replay_boarded" in notes[0]


# ---------------------------------------------------------------------------
# 16. panel_import_clean
# ---------------------------------------------------------------------------

def test_panel_import_clean():
    """admin.causal_lab imports without error and has panel() callable."""
    import admin.causal_lab as m  # noqa: PLC0415
    assert callable(m.panel)
