"""engine.thesis_monitor — deterministic kill-criteria watcher. Verifies the BROKEN /
WEAKENING / INTACT transitions as the convergence a thesis was built on decays.
"""
from __future__ import annotations

from engine import thesis_monitor as tm


def test_status_transitions():
    opened = {"heat_at_open": 0.70, "physical_at_open": True, "n_surfaces_at_open": 3}
    assert tm._status(opened, heat_now=0.68, phys_now=True, n_now=3) == "INTACT"
    assert tm._status(opened, heat_now=0.55, phys_now=True, n_now=3) == "WEAKENING"   # -0.15 heat
    assert tm._status(opened, heat_now=0.40, phys_now=True, n_now=3) == "BROKEN"      # -0.30 heat
    assert tm._status(opened, heat_now=0.68, phys_now=False, n_now=3) == "BROKEN"     # physical lost
    assert tm._status(opened, heat_now=0.68, phys_now=True, n_now=1) == "BROKEN"      # below quorum
    assert tm._status(opened, heat_now=0.68, phys_now=True, n_now=2) == "WEAKENING"   # lost a surface


def test_compute_marks_broken_when_convergence_decays(monkeypatch):
    monkeypatch.setattr(tm, "_open_theses", lambda: {
        "memory_storage": {"theme": "memory_storage", "asof": "2026-06-01", "heat_at_open": 0.70,
                           "physical_at_open": True, "n_surfaces_at_open": 3, "kill_criteria": ["x"]},
        "solar": {"theme": "solar", "asof": "2026-06-01", "heat_at_open": 0.60,
                  "physical_at_open": False, "n_surfaces_at_open": 2, "kill_criteria": ["y"]},
    })
    # current convergence: memory still hot, solar collapsed (absent from the board)
    conv = {"asof": "2026-06-28", "ranked": [
        {"theme": "memory_storage", "heat": 0.69, "physical_confirmed": True, "n_signals": 3}]}
    out = tm.compute_thesis_monitor(conv, write_state=False)
    by = {m["theme"]: m["status"] for m in out["monitored"]}
    assert by["memory_storage"] == "INTACT"
    assert by["solar"] == "BROKEN"            # gone from the board -> convergence collapsed
    assert out["n_broken"] == 1


def test_none_without_open_or_convergence(monkeypatch):
    monkeypatch.setattr(tm, "_open_theses", lambda: {})
    assert tm.compute_thesis_monitor({"ranked": []}) is None
    monkeypatch.setattr(tm, "_open_theses", lambda: {"x": {"theme": "x", "asof": "1"}})
    assert tm.compute_thesis_monitor(None) is None
