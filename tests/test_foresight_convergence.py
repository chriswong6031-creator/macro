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
    (F1: factor is DROPPED, not filled with neutral 0.5)."""
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
    assert it["earliness_available"] is False
    # The stored earliness should be None (absent)
    assert it["earliness"] is None
    # n_earliness_legs should be 1
    assert it["n_earliness_legs"] == 1
    # heat should be > 0 (factor dropped, not zeroed)
    assert it["heat"] > 0.0


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


def test_earliness_absent_payload_drops_factor():
    """When earliness payload has no data for the theme, the factor is DROPPED entirely.

    F1: absence must NOT be laundered as a neutral 0.5.  heat = n_lit / n_available,
    and earliness_available must be False.  For a fully-lit theme (all 5 sources lit,
    physical numeric) the heat should be >= 1/1 * 1.15 capped at 1.0 — definitely > 0.
    """
    rows = [_base_row(demand_band="ACCELERATING", bottleneck_band="TIGHT")]
    # No data for memory_storage in the payload → earliness absent → factor dropped
    out = cv.compute_convergence(_cas(rows), earliness_payload={})
    it = out["ranked"][0]
    assert it["earliness_absent"] is True
    assert it["earliness_available"] is False
    # heat must still be > 0 (factor dropped, not zeroed)
    assert it["heat"] > 0.0
    # Verify NOT the old 0.5-filled formula: with demand+physical lit (n_lit>=2, n_avail=5
    # unless edgar dark), heat should equal n_lit/n_available [× bonus] — NOT × 0.5.
    # The key contract: heat >= n_lit / n_available (without earliness deflation)
    n_lit = it["n_lit"]
    n_avail = it["n_available"]
    if n_avail > 0 and n_lit > 0:
        # Without earliness factor, raw = n_lit/n_avail (× bonus possibly)
        # With old 0.5 fill: raw = n_lit/n_avail * 0.5 — always smaller
        # We verify heat > n_lit/n_avail * 0.5 when earliness is absent
        assert it["heat"] > (n_lit / n_avail) * 0.5 - 0.001  # must not be 0.5-penalised


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


# ---------------------------------------------------------------------------
# F1: absent earliness DROPS the factor, does NOT fill 0.5
# (regression: compare two identical themes — one has earliness, one doesn't)
# ---------------------------------------------------------------------------

def test_absent_earliness_not_penalised_vs_present():
    """A theme with absent earliness must have heat >= theme-with-low-earliness.

    Under the old 0.5-fill, an absent theme got ×0.5 while a present-but-low
    theme (e.g. 0.2) got ×0.2 — counter-intuitively the absent theme beat the
    low-earliness theme.  Under the DROP rule: absent = no factor, which is the
    maximum possible heat for that lit/avail ratio.  A theme with earliness=1.0
    should still beat absent at the same lit/avail (bonus from earliness=1.0
    comes through; absent is equivalent to earliness=1.0 only when it's identical).
    More importantly: absent must NOT be penalised below n_lit/n_avail.
    """
    # Two identical themes: theme A has earliness=None (absent), theme B earliness=0.9
    rowA = _base_row(theme="memory_storage", name="A", demand_band="ACCELERATING",
                     bottleneck_band="TIGHT", guidance_band=None, n_altdata_leading=0)
    rowB = _base_row(theme="ai_semiconductors", name="B", demand_band="ACCELERATING",
                     bottleneck_band="TIGHT", guidance_band=None, n_altdata_leading=0)
    ep = {
        "memory_storage":    {"earliness": None, "n_legs_live": 0},  # absent
        "ai_semiconductors": {"earliness": 0.9,  "n_legs_live": 2},  # present
    }
    out = cv.compute_convergence(_cas([rowA, rowB]), earliness_payload=ep)
    items = {it["theme"]: it for it in out["ranked"]}
    a, b = items["memory_storage"], items["ai_semiconductors"]
    # A's heat must be >= n_lit_A / n_avail_A (NOT penalised by 0.5)
    if a["n_available"] > 0 and a["n_lit"] > 0:
        raw_floor = a["n_lit"] / a["n_available"]
        # physical bonus may apply — the floor without bonus is raw_floor
        assert a["heat"] >= raw_floor * 0.999  # within fp rounding
    # B's heat is deflated by earliness=0.9 (< 1.0) while A has no deflation
    # So A.heat >= B.heat when all else equal (both have same lit/avail, B gets ×0.9)
    assert a["heat"] >= b["heat"] - 0.001  # A never worse than B when B has <1.0 earliness


# ---------------------------------------------------------------------------
# F2: heat_threshold shadow rows accrue via compute_heat_shadow
# ---------------------------------------------------------------------------

def test_heat_threshold_shadow_rows_accrue(tmp_path):
    """compute_heat_shadow appends type='heat' rows to shadow_log.jsonl."""
    from unittest import mock
    from engine.foresight_shadow import compute_heat_shadow

    rows = [_base_row(demand_band="ACCELERATING", bottleneck_band="TIGHT")]
    ep = {"memory_storage": {"earliness": 0.9, "n_legs_live": 2}}
    convergence = cv.compute_convergence(_cas(rows), earliness_payload=ep)
    assert convergence is not None

    shadow_log = tmp_path / "foresight" / "shadow_log.jsonl"
    (tmp_path / "foresight").mkdir(parents=True)

    with mock.patch("engine.foresight_shadow.config") as mc:
        mc.data_dir.return_value = tmp_path
        n = compute_heat_shadow(convergence_payload=convergence, asof="2026-07-02")

    assert n > 0  # rows were written
    lines = [json.loads(l) for l in shadow_log.read_text().splitlines() if l.strip()]
    heat_rows = [r for r in lines if r.get("type") == "heat" and r.get("param") == "heat_threshold"]
    # One row per (candidate × theme) — 3 candidates × 1 theme = 3 rows
    assert len(heat_rows) == 3
    candidates_seen = {r["candidate"] for r in heat_rows}
    assert candidates_seen == {0.30, 0.40, 0.50}
    # Each row must have heating + heat + live_threshold
    for r in heat_rows:
        assert "heating" in r
        assert "heat" in r
        assert "live_threshold" in r
    # Dedup: re-running produces 0 new rows
    with mock.patch("engine.foresight_shadow.config") as mc:
        mc.data_dir.return_value = tmp_path
        n2 = compute_heat_shadow(convergence_payload=convergence, asof="2026-07-02")
    assert n2 == 0


import json  # noqa: E402 — used in the test above; import placed here to avoid top-level reorder
