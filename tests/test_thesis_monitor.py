"""engine.thesis_monitor — W4b deterministic thesis monitor tests.

Tests cover:
  (a) a PRECIPICE (text) ledger row auto-opens a deterministic thesis with machine-checkable criteria
  (b) BROKEN fires with NO LLM when the kill predicate is met across 2 builds
  (c) WEAKENING at 1 of 2 consecutive builds
  (d) LLM theses still work via the old heat-decay path
  (e) None when both producers empty
  (f) UNVERIFIABLE when required data absent (never silently INTACT)
  (g) n_deterministic / n_llm counts in output
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import thesis_monitor as tm


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_log(tmp_path: Path, rows: list[dict]) -> None:
    """Write rows to a fake log.jsonl."""
    p = tmp_path / "log.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _write_det_ledger(tmp_path: Path, rows: list[dict]) -> None:
    p = tmp_path / "deterministic_theses.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _write_llm_ledger(tmp_path: Path, rows: list[dict]) -> None:
    p = tmp_path / "analyst_theses.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _patch_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(tm, "_llm_ledger_path", lambda: tmp_path / "analyst_theses.jsonl")
    monkeypatch.setattr(tm, "_det_ledger_path", lambda: tmp_path / "deterministic_theses.jsonl")
    monkeypatch.setattr(tm, "_log_path", lambda: tmp_path / "log.jsonl")
    monkeypatch.setattr(tm, "_foresight_dir", lambda: tmp_path)


# ── (a) PRECIPICE (text) ledger row auto-opens a deterministic thesis ────────

def test_text_stage_opens_deterministic_thesis(monkeypatch, tmp_path):
    """A PRECIPICE (text) log row should auto-instantiate a deterministic thesis
    with text_accel_negative and stage_regressed_to_watch kill-criteria."""
    _patch_paths(monkeypatch, tmp_path)
    _write_log(tmp_path, [
        {"theme": "ag_fertilizer", "asof": "2026-07-01",
         "stage": "PRECIPICE (text)", "bottleneck_band": "TIGHT (text)",
         "revision_breadth": 0.1, "members": ["CF", "MOS"]},
    ])

    # Run with no convergence (deterministic path doesn't need it for thesis creation)
    out = tm.compute_thesis_monitor(None, write_state=False)

    # Should return a result (deterministic theses exist)
    assert out is not None
    assert out["n_deterministic"] == 1
    assert out["n_llm"] == 0

    th = out["monitored"][0]
    assert th["source"] == "deterministic"
    assert th["theme"] == "ag_fertilizer"
    assert th["stage_at_open"] == "PRECIPICE (text)"
    # Kill criteria for a text stage: text_accel_negative + stage_regressed_to_watch
    kinds = {c["kind"] for c in th["kill_criteria"]}
    assert "text_accel_negative" in kinds
    assert "stage_regressed_to_watch" in kinds
    # No numeric criterion for a text stage
    assert "band_loosens" not in kinds
    assert "breadth_rolls_negative" not in kinds


def test_numeric_stage_opens_deterministic_thesis_with_numeric_criteria(monkeypatch, tmp_path):
    """A PRECIPICE (numeric) log row opens a thesis with band_loosens, breadth_rolls_negative."""
    _patch_paths(monkeypatch, tmp_path)
    _write_log(tmp_path, [
        {"theme": "memory_storage", "asof": "2026-07-01",
         "stage": "PRECIPICE", "bottleneck_band": "TIGHT",
         "revision_breadth": 0.05, "members": ["MU"]},
    ])
    out = tm.compute_thesis_monitor(None, write_state=False)
    assert out is not None
    th = next(m for m in out["monitored"] if m["theme"] == "memory_storage")
    kinds = {c["kind"] for c in th["kill_criteria"]}
    assert "band_loosens" in kinds
    assert "breadth_rolls_negative" in kinds
    assert "stage_regressed_to_watch" in kinds
    # No text criterion
    assert "text_accel_negative" not in kinds


# ── (b) BROKEN fires with NO LLM when kill predicate met across 2 builds ────

def test_broken_fires_no_llm_stage_regression(monkeypatch, tmp_path):
    """BROKEN fires immediately on stage_regressed_to_watch (no consecutive builds needed)."""
    _patch_paths(monkeypatch, tmp_path)

    # Thesis opened at PRECIPICE (text)
    _write_det_ledger(tmp_path, [
        {"theme": "ag_fertilizer", "opened": "2026-06-01",
         "source": "deterministic", "stage_at_open": "PRECIPICE (text)",
         "kill_criteria": [
             {"kind": "text_accel_negative",
              "detail": "language accel < 0 for 2 consecutive builds"},
             {"kind": "stage_regressed_to_watch",
              "detail": "cascade stage no longer thesis-stage"},
         ]},
    ])

    # Current cascade: stage has regressed to WATCH
    _write_log(tmp_path, [
        {"theme": "ag_fertilizer", "asof": "2026-07-02",
         "stage": "WATCH", "bottleneck_band": None, "revision_breadth": 0.02},
    ])

    out = tm.compute_thesis_monitor(None, write_state=False)
    assert out is not None
    th = next(m for m in out["monitored"] if m["theme"] == "ag_fertilizer")
    assert th["status"] == "BROKEN"
    assert out["n_broken"] == 1
    # No LLM involvement — n_llm must be 0
    assert out["n_llm"] == 0


def test_broken_fires_band_loosens_after_2_builds(monkeypatch, tmp_path):
    """band_loosens BROKEN after 2 consecutive builds with loosened band."""
    _patch_paths(monkeypatch, tmp_path)

    _write_det_ledger(tmp_path, [
        # Header record
        {"theme": "memory_storage", "opened": "2026-06-01",
         "source": "deterministic", "stage_at_open": "PRECIPICE",
         "kill_criteria": [
             {"kind": "band_loosens",
              "detail": "bottleneck_band is LOOSE or AWAITING_DATA for 2 consecutive builds"},
             {"kind": "breadth_rolls_negative",
              "detail": "revision_breadth < 0 for 2 consecutive builds"},
             {"kind": "stage_regressed_to_watch",
              "detail": "cascade stage no longer thesis-stage"},
         ]},
        # One prior update event showing band_loosens condition was already met once
        {"kind": "update", "theme": "memory_storage",
         "criterion_kind": "band_loosens", "condition_met": True, "status": "WEAKENING",
         "ts": "2026-07-01T09:00:00+00:00"},
    ])

    # Current cascade: band is still AWAITING_DATA (loosened), stage still PRECIPICE
    _write_log(tmp_path, [
        {"theme": "memory_storage", "asof": "2026-07-02",
         "stage": "PRECIPICE", "bottleneck_band": "AWAITING_DATA",
         "revision_breadth": 0.1},
    ])

    out = tm.compute_thesis_monitor(None, write_state=False)
    assert out is not None
    th = next(m for m in out["monitored"] if m["theme"] == "memory_storage")
    # stage_regressed_to_watch = INTACT (still PRECIPICE)
    # breadth_rolls_negative = INTACT (breadth > 0)
    # band_loosens: 1 prior + current = 2 => BROKEN
    assert th["status"] == "BROKEN"


# ── (c) WEAKENING at 1 of 2 consecutive builds ──────────────────────────────

def test_weakening_at_1_of_2_builds(monkeypatch, tmp_path):
    """band_loosens WEAKENING when only current build meets the criterion (no prior event)."""
    _patch_paths(monkeypatch, tmp_path)

    _write_det_ledger(tmp_path, [
        {"theme": "memory_storage", "opened": "2026-06-01",
         "source": "deterministic", "stage_at_open": "PRECIPICE",
         "kill_criteria": [
             {"kind": "band_loosens",
              "detail": "bottleneck_band is LOOSE or AWAITING_DATA for 2 consecutive builds"},
             {"kind": "stage_regressed_to_watch",
              "detail": "cascade stage no longer thesis-stage"},
         ]},
        # No prior update events at all
    ])

    _write_log(tmp_path, [
        {"theme": "memory_storage", "asof": "2026-07-02",
         "stage": "PRECIPICE", "bottleneck_band": "AWAITING_DATA",
         "revision_breadth": 0.1},
    ])

    out = tm.compute_thesis_monitor(None, write_state=False)
    assert out is not None
    th = next(m for m in out["monitored"] if m["theme"] == "memory_storage")
    # Current build meets band_loosens (AWAITING_DATA is a loosened band), but no prior event
    # => WEAKENING (1 of 2 needed)
    assert th["status"] == "WEAKENING"
    assert out["n_weakening"] == 1
    assert out["n_broken"] == 0


# ── (d) LLM thesis heat-decay path still works ──────────────────────────────

def test_llm_thesis_path_intact(monkeypatch, tmp_path):
    """LLM theses still work via the heat-decay evaluation path."""
    _patch_paths(monkeypatch, tmp_path)

    _write_llm_ledger(tmp_path, [
        {"theme": "solar", "asof": "2026-06-01",
         "heat_at_open": 0.70, "physical_at_open": True, "n_surfaces_at_open": 3,
         "kill_criteria": ["bottleneck loosens"]},
    ])

    conv = {"asof": "2026-07-02", "ranked": [
        {"theme": "solar", "heat": 0.69, "physical_confirmed": True, "n_signals": 3},
    ]}

    out = tm.compute_thesis_monitor(conv, write_state=False)
    assert out is not None
    th = next(m for m in out["monitored"] if m["theme"] == "solar")
    assert th["source"] == "llm"
    assert th["status"] == "INTACT"
    assert out["n_llm"] == 1


def test_llm_thesis_broken_when_convergence_decays(monkeypatch, tmp_path):
    """LLM thesis is BROKEN when heat drops > BROKEN_DROP."""
    _patch_paths(monkeypatch, tmp_path)

    _write_llm_ledger(tmp_path, [
        {"theme": "solar", "asof": "2026-06-01",
         "heat_at_open": 0.70, "physical_at_open": True, "n_surfaces_at_open": 3},
    ])

    conv = {"asof": "2026-07-02", "ranked": [
        {"theme": "solar", "heat": 0.40, "physical_confirmed": True, "n_signals": 3},
    ]}

    out = tm.compute_thesis_monitor(conv, write_state=False)
    th = next(m for m in out["monitored"] if m["theme"] == "solar")
    assert th["status"] == "BROKEN"
    assert out["n_broken"] == 1


# ── (e) None when both producers empty ───────────────────────────────────────

def test_none_without_theses(monkeypatch, tmp_path):
    """Returns None when no theses exist in either producer."""
    _patch_paths(monkeypatch, tmp_path)
    # Empty log (no thesis-stage rows)
    _write_log(tmp_path, [
        {"theme": "solar", "asof": "2026-07-01", "stage": "WATCH",
         "bottleneck_band": None, "revision_breadth": -0.3},
    ])
    out = tm.compute_thesis_monitor(None, write_state=False)
    assert out is None


# ── (f) UNVERIFIABLE when required data absent ───────────────────────────────

def test_unverifiable_text_accel_no_data(monkeypatch, tmp_path):
    """text_accel_negative is UNVERIFIABLE when language_accel absent from the cascade row."""
    _patch_paths(monkeypatch, tmp_path)

    _write_det_ledger(tmp_path, [
        {"theme": "ag_fertilizer", "opened": "2026-06-01",
         "source": "deterministic", "stage_at_open": "PRECIPICE (text)",
         "kill_criteria": [
             {"kind": "text_accel_negative",
              "detail": "language accel < 0 for 2 consecutive builds"},
             {"kind": "stage_regressed_to_watch",
              "detail": "cascade stage no longer thesis-stage"},
         ]},
    ])

    # Current cascade row: stage still thesis-stage, but NO language_accel field
    _write_log(tmp_path, [
        {"theme": "ag_fertilizer", "asof": "2026-07-02",
         "stage": "PRECIPICE (text)", "bottleneck_band": "TIGHT (text)",
         "revision_breadth": 0.1},
        # No language_accel field in the row
    ])

    out = tm.compute_thesis_monitor(None, write_state=False)
    assert out is not None
    th = next(m for m in out["monitored"] if m["theme"] == "ag_fertilizer")
    # stage_regressed_to_watch = INTACT (still PRECIPICE (text))
    # text_accel_negative = UNVERIFIABLE (no data)
    # => aggregate: UNVERIFIABLE (all statuses are INTACT or UNVERIFIABLE, with at least one UNVERIFIABLE)
    assert th["status"] == "UNVERIFIABLE"


# ── (g) n_deterministic / n_llm counts ──────────────────────────────────────

def test_combined_counts(monkeypatch, tmp_path):
    """n_deterministic and n_llm are counted correctly when both producers have theses."""
    _patch_paths(monkeypatch, tmp_path)

    # Deterministic thesis from log
    _write_log(tmp_path, [
        {"theme": "ag_fertilizer", "asof": "2026-07-01",
         "stage": "PRECIPICE (text)", "bottleneck_band": "TIGHT (text)",
         "revision_breadth": 0.05},
    ])

    # LLM thesis
    _write_llm_ledger(tmp_path, [
        {"theme": "solar", "asof": "2026-06-01",
         "heat_at_open": 0.60, "physical_at_open": False, "n_surfaces_at_open": 2},
    ])

    conv = {"asof": "2026-07-02", "ranked": [
        {"theme": "solar", "heat": 0.55, "physical_confirmed": False, "n_signals": 2},
    ]}

    out = tm.compute_thesis_monitor(conv, write_state=False)
    assert out is not None
    assert out["n_deterministic"] == 1
    assert out["n_llm"] == 1
    assert out["n_open"] == 2


# ── backward-compat: old _open_theses / _status test (also tests LLM path) ──

def test_legacy_status_transitions():
    """The LLM heat-decay _status_llm function still passes original transition tests."""
    opened = {"heat_at_open": 0.70, "physical_at_open": True, "n_surfaces_at_open": 3}
    assert tm._status_llm(opened, heat_now=0.68, phys_now=True, n_now=3) == "INTACT"
    assert tm._status_llm(opened, heat_now=0.55, phys_now=True, n_now=3) == "WEAKENING"   # -0.15 heat
    assert tm._status_llm(opened, heat_now=0.40, phys_now=True, n_now=3) == "BROKEN"      # -0.30 heat
    assert tm._status_llm(opened, heat_now=0.68, phys_now=False, n_now=3) == "BROKEN"     # physical lost
    assert tm._status_llm(opened, heat_now=0.68, phys_now=True, n_now=1) == "BROKEN"      # below quorum
    assert tm._status_llm(opened, heat_now=0.68, phys_now=True, n_now=2) == "WEAKENING"   # lost a surface
