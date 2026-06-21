"""Tests for engine.bottom_radar — the anticipation-tier bottom-formation score."""
from __future__ import annotations
import numpy as np
import pandas as pd

from engine import bottom_radar


def _close(n=320, lo_at=40):
    """A series with a recent low ~lo_at bars ago then a reclaim (enough for MAs/vol)."""
    idx = pd.bdate_range("2023-01-01", periods=n)
    up = np.linspace(100, 130, n - lo_at - 10)
    dip = np.linspace(130, 118, 10)
    rec = np.linspace(118, 127, lo_at)
    v = np.concatenate([up, dip, rec])[:n]
    return pd.Series(v, index=idx)


def _mtf(turn_up=False, **d):
    base = {"macd_pos": False, "macd_cross_up": False, "macd_curl_up": False,
            "macd_approaching_up": False, "stoch_cross_up": False,
            "macd_cross_dn": False, "macd_curl_dn": False, "rsi14": 45, "rsi5": 40, "stoch": 30}
    base.update(d)
    if turn_up:
        base["macd_curl_up"] = True
    return {"D": base, "3D": base, "W": base, "M": {}}


def _cyc(phase="approaching_band", failed=False, above10=True, swing=True):
    return {"dc_phase": phase, "dc_day": 38, "dc_band": [36, 42], "failed_cycle": failed,
            "above_ma10": above10, "swing_low": swing, "cand_swing": swing,
            "cand_price": 118.0, "dcl_price": 100.0, "cand_age": 4}


def test_structure_and_legs_present():
    r = bottom_radar.assess(_close(), None, None, cyc=_cyc(), mtf=_mtf(turn_up=True),
                            early={}, wo={"level": "none"}, regime={"regime": "neutral"})
    assert r is not None
    assert set(r["legs"]) == {"timing_band", "divergence", "mtf_turn", "vol_contract",
                              "rs_hold", "deter_easing", "capitulation"}
    assert 0 <= r["raw"] <= 100
    assert r["stage"] in ("primed", "turning", "confirmed", "watch", "blocked")


def test_failed_cycle_is_vetoed():
    r = bottom_radar.assess(_close(), None, None, cyc=_cyc(failed=True),
                            mtf=_mtf(turn_up=True), early={}, wo={"level": "none"},
                            regime={"regime": "neutral"})
    assert "failed_cycle" in r["vetos"] and r["blocked"] and r["stage"] == "blocked"


def test_htf_downtrend_is_vetoed():
    r = bottom_radar.assess(_close(), None, None, cyc=_cyc(), mtf=_mtf(turn_up=True),
                            early={}, wo={"level": "none"}, regime={"regime": "bear"})
    assert "htf_downtrend" in r["vetos"] and r["blocked"]


def test_no_lead_blocks_when_nothing_turning():
    # no divergence arm AND no MTF turn => 'no_lead', not a setup yet
    r = bottom_radar.assess(_close(), None, None, cyc=_cyc(), mtf=_mtf(turn_up=False),
                            early={}, wo={"level": "none"}, regime={"regime": "neutral"})
    assert "no_lead" in r["vetos"]


def test_volume_flag_reflects_input():
    vol = pd.Series(1e6, index=_close().index)
    with_v = bottom_radar.assess(_close(), None, vol, cyc=_cyc(), mtf=_mtf(turn_up=True),
                                 early={}, wo={"level": "none"}, regime={"regime": "neutral"})
    without_v = bottom_radar.assess(_close(), None, None, cyc=_cyc(), mtf=_mtf(turn_up=True),
                                    early={}, wo={"level": "none"}, regime={"regime": "neutral"})
    assert with_v["has_volume"] is True and without_v["has_volume"] is False


def test_thin_history_returns_none():
    assert bottom_radar.assess(pd.Series(range(50)), None, None, cyc=_cyc(),
                               mtf=_mtf(), early={}, wo={}, regime={}) is None
