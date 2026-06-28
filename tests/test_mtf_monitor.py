"""Tests for engine/mtf_monitor.py — the multi-timeframe technical monitor.

The pure tag/MA helpers are unit-tested; monitor() is smoke-tested on the real
store (fast, must never raise and must return the documented schema).
"""
from __future__ import annotations

import pandas as pd

from engine import mtf_monitor as mm


# --- pure tag taxonomy -------------------------------------------------------
def test_tag_breakdown_on_higher_tf_falling():
    assert mm._tag("falling", "rising", "rising", "rising") == "breakdown"
    assert mm._tag("rising", "falling", "turning", "rising") == "breakdown"


def test_tag_rolling_over():
    assert mm._tag("rolling", "rising", "rising", "rising") == "rolling-over"
    assert mm._tag("rising", "rolling", "rising", "rising") == "rolling-over"


def test_tag_weakening_short_term():
    # higher TFs ok, daily/3d rolling or falling
    assert mm._tag("rising", "rising", "rising", "falling") == "weakening"
    assert mm._tag("rising", "rising", "rolling", "rising") == "weakening"


def test_tag_bottoming_only_from_weakness():
    # weekly basing/turning + a lower TF turning => bottoming
    assert mm._tag("basing", "basing", "turning", "rising") == "bottoming"
    assert mm._tag("rising", "turning", "rising", "rising") == "bottoming"


def test_tag_firm_uptrend_is_not_bottoming():
    # a clean uptrend must be 'firm', never 'bottoming'
    assert mm._tag("rising", "rising", "rising", "rising") == "firm"
    assert mm._tag("rising", "rising", "rising", "basing") == "firm"


def test_phase_warn_map_orientation():
    assert mm._PHASE_WARN["falling"] == 1.0
    assert mm._PHASE_WARN["rolling"] > mm._PHASE_WARN["basing"]
    assert mm._PHASE_WARN["rising"] == 0.0
    assert mm._PHASE_WARN["turning"] == 0.0
    assert mm._PHASE_WARN["unknown"] is None


def test_ma_below():
    up = pd.Series(range(1, 301), dtype=float)       # monotonic up -> above MA
    dn = pd.Series(range(300, 0, -1), dtype=float)   # monotonic down -> below MA
    assert mm._ma_below(up, 200) is False
    assert mm._ma_below(dn, 200) is True
    assert mm._ma_below(pd.Series([1.0, 2.0]), 200) is None  # too short


# --- monitor() smoke (real store) --------------------------------------------
def test_monitor_smoke():
    out = mm.monitor()
    assert out["schema"] == "mtf_monitor.v1"
    assert set(out["groups"]) == {"indexes", "assets", "sectors"}
    ti = out["technical_intensity"]
    assert ti is None or (0.0 <= ti <= 1.0)
    assert out["breakdown_count"] >= 0
    # rows carry the documented fields
    for g in out["groups"].values():
        for r in g:
            assert r["tag"] in ("breakdown", "rolling-over", "weakening",
                                "bottoming", "firm", "neutral")
            assert 0.0 <= r["intensity"] <= 1.0
            assert "tfs" in r and "D" in r["tfs"]


def test_monitor_universe_override():
    out = mm.monitor(universe=None)  # default universe path
    # indexes group should include SPY when data is present
    tks = {r["ticker"] for r in out["groups"]["indexes"]}
    assert "SPY" in tks or len(out["groups"]["indexes"]) == 0
