"""engine.foresight_convergence — the heating-up fusion. Verifies that heat counts
independent leading signals, decays with lateness (broad revisions), rewards cross-surface
corroboration, and that the board excludes priced-in (late) themes. Pure / fixture.
"""
from __future__ import annotations

from engine import foresight_convergence as cv


def _cas(rows):
    return {"asof": "2026-06-28", "themes": rows}


def test_heat_ranks_multi_signal_early_first():
    rows = [
        {"theme": "memory_storage", "name": "Memory", "stage": "PRECIPICE",
         "bottleneck_band": "TIGHT", "demand_band": "ACCELERATING", "guidance_band": "RAISING",
         "n_altdata_leading": 1, "revision_breadth": 0.05,
         "score_detail": {"physical_confirmed": True}, "score": 70},
        {"theme": "solar", "name": "Solar", "stage": "RE-RATING", "bottleneck_band": None,
         "demand_band": None, "guidance_band": None, "n_altdata_leading": 0,
         "revision_breadth": 0.9, "score_detail": {"physical_confirmed": False}, "score": 40},
    ]
    out = cv.compute_convergence(_cas(rows))
    assert out["ranked"][0]["theme"] == "memory_storage"
    assert out["ranked"][0]["n_signals"] >= 4                  # physical+demand+guidance+altdata
    assert out["ranked"][0]["heat"] > out["ranked"][1]["heat"]
    assert out["heating_up"][0]["theme"] == "memory_storage"


def test_late_theme_not_heating_despite_signals():
    rows = [{"theme": "memory_storage", "name": "M", "stage": "RE-RATING",
             "bottleneck_band": "TIGHT", "demand_band": "ACCELERATING", "guidance_band": "RAISING",
             "n_altdata_leading": 1, "revision_breadth": 0.95,
             "score_detail": {"physical_confirmed": True}}]
    out = cv.compute_convergence(_cas(rows))
    assert out["n_heating"] == 0                              # priced in -> not hot, even with 4 signals


def test_cross_surface_corroboration():
    rows = [{"theme": "memory_storage", "name": "M", "stage": "PRECIPICE",
             "bottleneck_band": "TIGHT", "revision_breadth": 0.05,
             "score_detail": {"physical_confirmed": True}}]
    subs = {"subsectors": [{"sub_industry": "Computer Hardware", "n_scarcity": 2,
                            "scarcity_members": ["MU", "STX"]}]}          # MU is memory_storage
    emg = {"candidates": [{"sic_desc": "Semis", "new_filers": ["WDC"]}]}  # WDC is memory_storage
    out = cv.compute_convergence(_cas(rows), emergence=emg, subsectors=subs)
    it = out["ranked"][0]
    assert "subsector_scarcity" in it["cross_surface"]
    assert "discovery_echo" in it["cross_surface"]
    assert it["n_signals"] >= 3                               # physical + 2 cross-surface


def test_none_on_empty():
    assert cv.compute_convergence(None) is None
    assert cv.compute_convergence({"themes": []}) is None
