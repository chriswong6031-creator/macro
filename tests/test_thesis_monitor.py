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


# ── N4 new regression tests ──────────────────────────────────────────────────

# (a) two REAL builds same asof with write_state=True → counter does NOT double-increment
def test_b2_same_asof_no_double_increment(monkeypatch, tmp_path):
    """B2: two builds with the same cascade asof must not double-increment the consecutive counter.

    Without the fix, run1 appends an update event, run2 appends a second event for the same
    asof — and a WEAKENING criterion reaches BROKEN prematurely.
    With the fix, run2 detects that (criterion_kind, asof) already logged and skips it.
    """
    _patch_paths(monkeypatch, tmp_path)
    _write_log(tmp_path, [
        {"theme": "memory_storage", "asof": "2026-07-02",
         "stage": "PRECIPICE", "bottleneck_band": "AWAITING_DATA",
         "revision_breadth": 0.1},
    ])

    # Run 1: write_state=True — WEAKENING on first build (no prior events → 1 of 2)
    out1 = tm.compute_thesis_monitor(None, write_state=True)
    assert out1 is not None
    th1 = next(m for m in out1["monitored"] if m["theme"] == "memory_storage")
    # band_loosens should be WEAKENING (1 of 2 needed)
    assert th1["status"] == "WEAKENING"

    # Run 2 same asof, write_state=True — must still be WEAKENING, NOT BROKEN
    out2 = tm.compute_thesis_monitor(None, write_state=True)
    assert out2 is not None
    th2 = next(m for m in out2["monitored"] if m["theme"] == "memory_storage")
    # B2 fix: deduplicated to one event per (criterion_kind, asof) → still WEAKENING
    assert th2["status"] == "WEAKENING", (
        "B2 regression: same-asof re-run incremented counter twice (BROKEN prematurely)"
    )


# (b) same theme in both producers → n_open=1, counted once in n_broken
def test_b3_same_theme_both_producers_counted_once(monkeypatch, tmp_path):
    """B3: when the same theme appears in both deterministic and LLM producers, it must appear
    exactly once in monitored and be counted once in n_broken (not twice)."""
    _patch_paths(monkeypatch, tmp_path)

    # Deterministic: ag_fertilizer thesis, stage regressed → BROKEN
    _write_det_ledger(tmp_path, [
        {"theme": "ag_fertilizer", "opened": "2026-06-01",
         "source": "deterministic", "stage_at_open": "PRECIPICE (text)",
         "kill_criteria": [
             {"kind": "stage_regressed_to_watch",
              "detail": "cascade stage no longer thesis-stage"},
         ]},
    ])
    _write_log(tmp_path, [
        {"theme": "ag_fertilizer", "asof": "2026-07-02",
         "stage": "WATCH", "bottleneck_band": None, "revision_breadth": 0.02},
    ])
    # LLM: same theme
    _write_llm_ledger(tmp_path, [
        {"theme": "ag_fertilizer", "asof": "2026-06-01",
         "heat_at_open": 0.80, "physical_at_open": True, "n_surfaces_at_open": 3},
    ])

    # No convergence (so LLM heat-decay sees heat=0 → BROKEN anyway)
    out = tm.compute_thesis_monitor(None, write_state=False)
    assert out is not None
    # Only ONE monitored row for ag_fertilizer (B3 dedup)
    ag_rows = [m for m in out["monitored"] if m["theme"] == "ag_fertilizer"]
    assert len(ag_rows) == 1, f"B3 regression: {len(ag_rows)} rows for same theme (expected 1)"
    # n_open = 1 (the deduplicated row)
    assert out["n_open"] == 1
    # n_broken = 1 (BROKEN counted once)
    assert out["n_broken"] == 1
    # LLM enrichment fields were folded onto the deterministic row
    assert ag_rows[0]["source"] == "deterministic"
    assert "llm_status" in ag_rows[0]
    assert out["n_llm"] == 1


# (c) kill → close → re-flag → fresh thesis opens
def test_b2b_kill_close_reflag_opens_fresh(monkeypatch, tmp_path):
    """B2b: after a thesis is BROKEN and closed, a re-flag (new cascade thesis row) must
    open a FRESH thesis header — not reuse the closed one."""
    _patch_paths(monkeypatch, tmp_path)

    # Epoch 1: thesis opened, then closed
    _write_det_ledger(tmp_path, [
        {"theme": "solar", "opened": "2026-05-01",
         "source": "deterministic", "stage_at_open": "PRECIPICE",
         "kill_criteria": [
             {"kind": "stage_regressed_to_watch",
              "detail": "cascade stage no longer thesis-stage"},
         ]},
        {"kind": "close", "theme": "solar", "reason": "BROKEN",
         "ts": "2026-06-01T00:00:00+00:00"},
    ])

    # Current cascade: solar is back in PRECIPICE (re-flagged)
    _write_log(tmp_path, [
        {"theme": "solar", "asof": "2026-07-02",
         "stage": "PRECIPICE", "bottleneck_band": "TIGHT", "revision_breadth": 0.05},
    ])

    out = tm.compute_thesis_monitor(None, write_state=False)
    assert out is not None
    # A fresh thesis must have been opened for solar (the closed epoch is excluded)
    solar_rows = [m for m in out["monitored"] if m["theme"] == "solar"]
    assert len(solar_rows) == 1
    th = solar_rows[0]
    # The re-opened thesis's opened date should be the new cascade flag's asof
    assert th.get("opened") == "2026-07-02"
    # Status should be INTACT (stage is still PRECIPICE)
    assert th["status"] == "INTACT"


# (g) opened == flag asof
def test_b2b_opened_equals_flag_asof(monkeypatch, tmp_path):
    """B2b: the 'opened' field in the thesis header must be the cascade flag row's asof,
    not date.today()."""
    _patch_paths(monkeypatch, tmp_path)
    _write_log(tmp_path, [
        {"theme": "ag_fertilizer", "asof": "2026-05-15",
         "stage": "PRECIPICE (text)", "bottleneck_band": "TIGHT (text)",
         "revision_breadth": 0.1, "members": ["CF"]},
    ])

    out = tm.compute_thesis_monitor(None, write_state=False)
    assert out is not None
    th = next(m for m in out["monitored"] if m["theme"] == "ag_fertilizer")
    # B2b fix: opened == asof of the log row that opened the thesis
    assert th.get("opened") == "2026-05-15", (
        f"B2b regression: opened={th.get('opened')!r} expected '2026-05-15' (flag asof)"
    )
