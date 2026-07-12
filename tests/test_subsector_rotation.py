"""Unit tests for engine.subsector_rotation — the rotation/velocity math."""
from __future__ import annotations

from engine import subsector_rotation as sr


def _tree():
    # ≥3 members each so they clear the emerging/fading breadth floor (MIN_BREADTH=3).
    return [
        {"theme": "Alpha", "subsectors": [
            {"key": "a1", "name": "A-One", "members": ["AA", "AB", "AD"]},
            {"key": "a2", "name": "A-Two", "members": ["AC", "AE", "AF"]},
        ]},
        {"theme": "Beta", "subsectors": [
            {"key": "b1", "name": "B-One", "members": ["BA", "BC", "BD"]},
            {"key": "b2", "name": "B-Two", "members": ["BB", "BE", "BF"]},
        ]},
    ]


def _perf():
    # a1: hot & accelerating (1W pace >> 3M pace), strong recent RS.
    # b2: established leader rolling over (big 3M/6M, weak 1W) -> weakening.
    # b1: laggard turning up -> improving. a2: flat laggard.
    return {
        "a1": {"1D": 1.0, "1W": 9.0, "1M": 10.0, "3M": 12.0, "6M": 14.0, "1Y": 20.0, "MTD": 5, "YTD": 18},
        "a2": {"1D": -0.2, "1W": -1.0, "1M": -2.0, "3M": -3.0, "6M": -4.0, "1Y": -5.0, "MTD": -1, "YTD": -4},
        "b1": {"1D": 0.5, "1W": 4.0, "1M": 1.0, "3M": -8.0, "6M": -12.0, "1Y": -10.0, "MTD": 2, "YTD": -9},
        "b2": {"1D": -0.5, "1W": -2.0, "1M": 3.0, "3M": 30.0, "6M": 50.0, "1Y": 60.0, "MTD": -1, "YTD": 55},
    }


def test_structure_and_coverage():
    out = sr.compute_rotation(_tree(), _perf(), {"AA": {"1W": 9, "1M": 11}})
    assert out["n_subsectors"] == 4 and out["n_themes"] == 2
    assert {s["key"] for s in out["subsectors"]} == {"a1", "a2", "b1", "b2"}
    # ranked by emerging_score desc; rank field consistent.
    scores = [s["emerging_score"] for s in out["subsectors"]]
    assert scores == sorted(scores, reverse=True)
    assert out["subsectors"][0]["rank"] == 1
    for s in out["subsectors"]:
        assert s["quadrant"] in ("leading", "weakening", "improving", "lagging")
        assert set(s["perf"]) == set(sr.HORIZONS)


def test_quadrant_logic():
    out = {s["key"]: s for s in sr.compute_rotation(_tree(), _perf())["subsectors"]}
    # a1 leads and is improving -> leading.
    assert out["a1"]["quadrant"] == "leading"
    assert out["a1"]["rs_ratio"] > 0 and out["a1"]["rs_mom"] > 0
    # b2 is a strong leader by level but momentum rolling over -> weakening.
    assert out["b2"]["rs_ratio"] > 0 and out["b2"]["rs_mom"] < 0
    assert out["b2"]["quadrant"] == "weakening"
    # b1 is a laggard turning up -> improving (negative level, positive momentum).
    assert out["b1"]["rs_ratio"] < 0 and out["b1"]["rs_mom"] > 0
    assert out["b1"]["quadrant"] == "improving"


def test_acceleration_and_highlights():
    out = sr.compute_rotation(_tree(), _perf())
    m = {s["key"]: s for s in out["subsectors"]}
    # a1: weekly pace (9) far exceeds 3M weekly pace (12/13≈0.9) -> strong +accel.
    assert m["a1"]["accel"] is not None and m["a1"]["accel"] > 0
    # b2: 1W negative, 3M huge -> decelerating.
    assert m["b2"]["accel"] < 0
    # highlights: a1 emerging; b2 fading; b2 a leader; a2 a laggard.
    assert "a1" in out["highlights"]["emerging"]
    assert "b2" in out["highlights"]["fading"]
    assert "b2" in out["highlights"]["leaders"]
    assert "a2" in out["highlights"]["laggards"]


def test_missing_horizons_are_safe():
    tree = [{"theme": "X", "subsectors": [
        {"key": "x1", "name": "X1", "members": []},
        {"key": "x2", "name": "X2", "members": []},
    ]}]
    perf = {"x1": {"1W": 3.0}, "x2": {"3M": 5.0}}  # disjoint horizons
    out = sr.compute_rotation(tree, perf)
    assert out["n_subsectors"] == 2
    for s in out["subsectors"]:
        assert s["quadrant"] in ("leading", "weakening", "improving", "lagging")


def test_breadth_floor_excludes_thin_subsectors():
    # a 2-member subsector that is momentum-hot must NOT reach the emerging call
    # (it's a stock or two, not a rotation) — while an identical 3-member one does.
    tree = [{"theme": "T", "subsectors": [
        {"key": "thin", "name": "Thin", "members": ["TA", "TB"]},
        {"key": "broad", "name": "Broad", "members": ["BA", "BB", "BC"]},
        {"key": "c1", "name": "C1", "members": ["CA", "CB", "CC"]},
        {"key": "c2", "name": "C2", "members": ["DA", "DB", "DC"]},
    ]}]
    # improving = weak over long windows, strong recently (relative rank RISES short-term).
    improving = {"1W": 15.0, "1M": 8.0, "3M": -5.0, "6M": -10.0, "1Y": -8.0}
    fading = {"1W": -8.0, "1M": -5.0, "3M": 10.0, "6M": 15.0, "1Y": 12.0}
    perf = {"thin": dict(improving), "broad": dict(improving),
            "c1": dict(fading), "c2": dict(fading)}
    em = sr.compute_rotation(tree, perf)["highlights"]["emerging"]
    assert "broad" in em and "thin" not in em


# ── Rotation Command RC-R4: synthetic-node perf feed ─────────────────────────

def test_perf_from_close_horizons():
    import pandas as pd
    idx = pd.bdate_range("2024-01-02", periods=400)
    s = pd.Series([100.0 * (1.001 ** k) for k in range(400)], index=idx)
    out = sr.perf_from_close(s)
    assert out is not None
    assert set(out) == {"1D", "1W", "1M", "MTD", "3M", "6M", "1Y", "YTD"}
    assert abs(out["1D"] - 0.1) < 0.02          # +0.1%/session drift
    assert abs(out["1W"] - 0.5) < 0.1
    assert out["1Y"] > 20.0                     # ≈ +28.5% over 252 sessions
    assert out["YTD"] is not None and out["MTD"] is not None


def test_perf_from_close_thin_series_none():
    import pandas as pd
    idx = pd.bdate_range("2026-01-02", periods=100)
    assert sr.perf_from_close(pd.Series(100.0, index=idx)) is None
