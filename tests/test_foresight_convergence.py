"""engine.foresight_convergence — W4a rebuild tests.

Required test targets from the W4a spec:
  (a) merged edgar surface counts once (de-dup: subsector_scarcity + discovery_echo = ONE edgar_scarcity)
  (b) dark surface leaves the denominator (n_available shrinks, not penalised)
  (c) earliness gated on n_legs_live (below 2 → absent → neutral 0.5)
  (d) meta-driver card emitted for ≥3 same-cluster hot themes

Plus regression tests preserving original convergence semantics.
"""
from __future__ import annotations

from unittest import mock

from engine import foresight_convergence as cv


def _cas(rows):
    return {"asof": "2026-07-02", "themes": rows}


def _base_row(theme="memory_storage", name="Memory", stage="PRECIPICE",
              bottleneck_band="TIGHT", demand_band="ACCELERATING",
              guidance_band="RAISING", n_altdata_leading=1,
              revision_breadth=0.05, score=70, score_detail=None):
    return {
        "theme": theme, "name": name, "stage": stage,
        "bottleneck_band": bottleneck_band, "demand_band": demand_band,
        "guidance_band": guidance_band, "n_altdata_leading": n_altdata_leading,
        "revision_breadth": revision_breadth, "score": score,
        "score_detail": score_detail or {"physical_confirmed": True},
    }


# ---------------------------------------------------------------------------
# (a) Merged edgar surface counts once
# ---------------------------------------------------------------------------

def test_edgar_scarcity_is_one_source_not_two():
    """subsector_scarcity + discovery_echo both light the same EDGAR parquet.
    W4a merges them into ONE edgar_scarcity source — a theme that overlaps both
    pools should have edgar_scarcity in lit_sources ONCE, not twice."""
    rows = [_base_row(bottleneck_band="AWAITING_DATA",   # physical dark
                      demand_band=None, guidance_band=None, n_altdata_leading=0)]
    subs = {"subsectors": [{"sub_industry": "Semis", "n_scarcity": 2,
                            "scarcity_members": ["MU"]}]}   # MU in memory_storage
    emg = {"candidates": [{"sic_desc": "Semis", "new_filers": ["WDC"]}]}  # WDC also in memory_storage
    out = cv.compute_convergence(_cas(rows), emergence=emg, subsectors=subs)
    it = out["ranked"][0]
    # edgar_scarcity should appear ONCE in lit_sources
    assert it["lit_sources"].count("edgar_scarcity") == 1
    # total lit should be 1 (edgar_scarcity only — physical/demand/guidance/altdata all dark)
    assert it["n_lit"] == 1


def test_no_edgar_overlap_gives_zero():
    """A theme with no members in subsector or discovery pools: edgar_scarcity not lit."""
    rows = [_base_row(bottleneck_band="AWAITING_DATA", demand_band=None,
                      guidance_band=None, n_altdata_leading=0)]
    subs = {"subsectors": [{"sub_industry": "Copper", "n_scarcity": 2,
                            "scarcity_members": ["FCX"]}]}   # FCX NOT in memory_storage
    emg = {"candidates": [{"sic_desc": "Ag", "new_filers": ["CF"]}]}   # CF NOT in memory_storage
    out = cv.compute_convergence(_cas(rows), emergence=emg, subsectors=subs)
    it = out["ranked"][0]
    assert "edgar_scarcity" not in it["lit_sources"]


# ---------------------------------------------------------------------------
# (b) Dark surface leaves the denominator
# ---------------------------------------------------------------------------

def test_dark_physical_excluded_from_denominator():
    """When physical is AWAITING_DATA (dark), it should NOT appear in n_available.
    This means n_available < max_sources — the desk is not penalised for the outage."""
    rows = [_base_row(bottleneck_band="AWAITING_DATA", demand_band="ACCELERATING",
                      guidance_band=None, n_altdata_leading=0)]
    out = cv.compute_convergence(_cas(rows))
    it = out["ranked"][0]
    # physical is dark — should not count in n_available
    assert it["source_available"]["physical"] is False
    assert it["n_available"] < cv.len_sources()
    # heat should be based only on available sources — non-zero since demand is lit
    assert it["heat"] > 0.0


def test_all_dark_except_demand_still_gets_reasonable_heat():
    """When only demand is available AND lit, heat = 1/1 × earliness_effective."""
    rows = [_base_row(bottleneck_band="AWAITING_DATA", demand_band="ACCELERATING",
                      guidance_band=None, n_altdata_leading=None)]
    out = cv.compute_convergence(_cas(rows))
    it = out["ranked"][0]
    assert it["n_available"] >= 1
    assert it["n_lit"] >= 1
    # heat should be > 0 (demand lit)
    assert it["heat"] > 0.0


# ---------------------------------------------------------------------------
# (c) Earliness gated on n_legs_live
# ---------------------------------------------------------------------------

def test_earliness_absent_when_n_legs_live_below_2():
    """When earliness payload has n_legs_live < 2, earliness should be treated as absent
    (the spec says absent earliness → neutral 0.5 in the heat formula)."""
    rows = [_base_row(demand_band="ACCELERATING", bottleneck_band="TIGHT")]
    # Inject an earliness payload with n_legs_live=1 (below gate)
    earliness_payload = {
        "memory_storage": {
            "earliness": 0.9,   # high value that WOULD boost heat
            "n_legs_live": 1,   # BELOW gate — must be treated as absent
        }
    }
    out = cv.compute_convergence(_cas(rows), earliness_payload=earliness_payload)
    it = out["ranked"][0]
    # earliness_absent should be True
    assert it["earliness_absent"] is True
    # The stored earliness should be None (absent)
    assert it["earliness"] is None
    # n_earliness_legs should be 1
    assert it["n_earliness_legs"] == 1


def test_earliness_used_when_n_legs_live_ge_2():
    """When n_legs_live >= 2, earliness should be used in the heat formula."""
    rows = [_base_row(demand_band="ACCELERATING", bottleneck_band="TIGHT")]
    earliness_payload = {
        "memory_storage": {
            "earliness": 0.9,
            "n_legs_live": 2,   # AT the gate — should be used
        }
    }
    out = cv.compute_convergence(_cas(rows), earliness_payload=earliness_payload)
    it = out["ranked"][0]
    assert it["earliness_absent"] is False
    assert it["earliness"] == 0.9


def test_earliness_absent_payload_uses_neutral():
    """When earliness payload has no data for the theme, neutral 0.5 is used (not 0)."""
    rows = [_base_row(demand_band="ACCELERATING", bottleneck_band="TIGHT")]
    # No data for memory_storage in the payload
    out = cv.compute_convergence(_cas(rows), earliness_payload={})
    it = out["ranked"][0]
    assert it["earliness_absent"] is True
    # heat should still be > 0 (neutral 0.5 applied, not 0)
    assert it["heat"] > 0.0


# ---------------------------------------------------------------------------
# (d) Meta-driver card emitted for ≥3 same-cluster hot themes
# ---------------------------------------------------------------------------

def test_meta_driver_card_emitted_for_3_co_heating_cluster_themes():
    """When ≥3 themes in the same cluster all have heat >= HEAT_HOT,
    ONE meta-driver card should be emitted for that cluster."""
    # All three are hot: physical + demand lit, physical is numeric TIGHT → bonus
    rows = [
        _base_row(theme="ai_semiconductors", name="AI Semis", stage="PRECIPICE",
                  bottleneck_band="TIGHT", demand_band="ACCELERATING",
                  guidance_band="RAISING", revision_breadth=0.05, n_altdata_leading=1),
        _base_row(theme="memory_storage", name="Memory", stage="PRECIPICE",
                  bottleneck_band="TIGHT", demand_band="ACCELERATING",
                  guidance_band="RAISING", revision_breadth=0.05, n_altdata_leading=1),
        _base_row(theme="semicap_equipment", name="Semicap", stage="PRECIPICE",
                  bottleneck_band="TIGHT", demand_band="ACCELERATING",
                  guidance_band="RAISING", revision_breadth=0.05, n_altdata_leading=1),
    ]
    # Inject clusters: all three in "ai_capex"
    clusters_map = {
        "ai_semiconductors": "ai_capex",
        "memory_storage": "ai_capex",
        "semicap_equipment": "ai_capex",
    }
    # Inject earliness with 2+ legs so it's used (high earliness → hot)
    early_payload = {k: {"earliness": 0.8, "n_legs_live": 2} for k in
                     ["ai_semiconductors", "memory_storage", "semicap_equipment"]}

    with mock.patch("engine.foresight_convergence._load_enb_clusters", return_value=clusters_map), \
         mock.patch("engine.foresight_convergence._theme_members",
                    return_value={t["theme"]: set() for t in rows}):
        out = cv.compute_convergence(_cas(rows), earliness_payload=early_payload)

    assert out["n_meta_drivers"] >= 1
    md = out["meta_drivers"][0]
    assert md["cluster_id"] == "ai_capex"
    assert md["n_members"] == 3
    assert set(md["member_themes"]) == {"ai_semiconductors", "memory_storage", "semicap_equipment"}


def test_meta_driver_not_emitted_for_only_2_cluster_themes():
    """Only 2 co-heating themes in same cluster → no meta-driver card (threshold is 3)."""
    rows = [
        _base_row(theme="ai_semiconductors", name="AI Semis", stage="PRECIPICE",
                  bottleneck_band="TIGHT", demand_band="ACCELERATING",
                  revision_breadth=0.05, n_altdata_leading=1),
        _base_row(theme="memory_storage", name="Memory", stage="PRECIPICE",
                  bottleneck_band="TIGHT", demand_band="ACCELERATING",
                  revision_breadth=0.05, n_altdata_leading=1),
    ]
    clusters_map = {"ai_semiconductors": "ai_capex", "memory_storage": "ai_capex"}
    early_payload = {k: {"earliness": 0.8, "n_legs_live": 2}
                     for k in ["ai_semiconductors", "memory_storage"]}

    with mock.patch("engine.foresight_convergence._load_enb_clusters", return_value=clusters_map), \
         mock.patch("engine.foresight_convergence._theme_members",
                    return_value={t["theme"]: set() for t in rows}):
        out = cv.compute_convergence(_cas(rows), earliness_payload=early_payload)

    assert out["n_meta_drivers"] == 0


# ---------------------------------------------------------------------------
# Regression: original convergence semantics preserved
# ---------------------------------------------------------------------------

def test_heat_ranks_early_high_signal_first():
    rows = [
        _base_row(theme="memory_storage", name="Memory", stage="PRECIPICE",
                  bottleneck_band="TIGHT", demand_band="ACCELERATING",
                  guidance_band="RAISING", n_altdata_leading=1, revision_breadth=0.05,
                  score=70, score_detail={"physical_confirmed": True}),
        _base_row(theme="solar", name="Solar", stage="RE-RATING",
                  bottleneck_band=None, demand_band=None, guidance_band=None,
                  n_altdata_leading=0, revision_breadth=0.9, score=40,
                  score_detail={"physical_confirmed": False}),
    ]
    out = cv.compute_convergence(_cas(rows))
    assert out["ranked"][0]["theme"] == "memory_storage"
    assert out["ranked"][0]["heat"] > out["ranked"][1]["heat"]


def test_none_on_empty():
    assert cv.compute_convergence(None) is None
    assert cv.compute_convergence({"themes": []}) is None


def test_power_scarcity_supplies_physical_surface():
    cascade = _cas([{"theme": "data_center_power", "name": "DCP", "stage": "PRECIPICE",
                     "bottleneck_band": "AWAITING_DATA", "demand_band": None,
                     "guidance_band": None, "n_altdata_leading": 0,
                     "revision_breadth": 0.05, "score": 50,
                     "score_detail": {"physical_confirmed": False}}])
    power = {"band": "TIGHT", "themes": {"data_center_power": {}}}
    out = cv.compute_convergence(cascade, power_scarcity=power)
    it = out["ranked"][0]
    assert "physical" in it["lit_sources"] and it["physical_confirmed"] is True
    # Without TIGHT power read, no physical surface
    out2 = cv.compute_convergence(
        cascade, power_scarcity={"band": "LOOSE", "themes": {"data_center_power": {}}})
    assert "physical" not in out2["ranked"][0]["lit_sources"]
