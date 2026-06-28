"""Tests for engine.entry_signal — the second (entry-timing) gauge."""
from __future__ import annotations
import numpy as np
import pandas as pd
import pytest

from engine import entry_signal


def _uptrend(n: int = 320, start: float = 100.0, drift: float = 0.004) -> pd.Series:
    idx = pd.bdate_range("2024-01-01", periods=n)
    vals = start * np.cumprod(1 + drift + 0.0 * np.arange(n))
    return pd.Series(vals, index=idx)


def _rec(state, urgency, tag, *, dc_phase="approaching_band", dc_day=35,
         dcl=None, eq=0, bc=None, pv200=20.0, pv50=8.0):
    return {
        "ladder": {"state": state, "eq_score": eq, "bottom_confidence": bc,
                   "eq_grade": "good", "entry": {"urgency": urgency, "tag": tag,
                                                 "text": "do the thing", "text_zh": "做"}},
        "cycle": {"dc_phase": dc_phase, "dc_day": dc_day, "dc_band": [36, 42],
                  "dcl_price": dcl, "cand_price": None},
        "mtf": {"D": {}},
        "tech": {"price": None, "pct_vs_200dma": pv200, "pct_vs_50dma": pv50},
    }


def test_extended_name_gets_pullback_zone_below_spot() -> None:
    """An extended TOP WATCH / DON'T CHASE name (the HWM case) must read 'extended'
    with a buy zone BELOW spot and a don't-chase line at/under spot — never a buy-now."""
    close = _uptrend()
    spot = float(close.iloc[-1])
    rec = _rec("TOP WATCH", "caution", "DON'T CHASE", dc_phase="approaching_band",
               dcl=spot * 0.85, eq=-25)
    es = entry_signal.assess(close, None, rec)
    assert es["status"] == "extended"
    assert es["buy_zone"]["high"] < spot               # accumulate on a pullback
    assert es["buy_zone"]["pct_from_spot"] < 0
    assert es["chase_above"] <= spot * 1.001
    assert es["act_level"] == 0                          # stand aside, don't act now


def test_pullback_zone_depth_is_capped() -> None:
    """A vertically-extended name's 50-day MA can be -25% away; the daily-cycle buy
    zone must stay a realistic dip (<= ~3*ATR or 10%), not a crash target."""
    close = _uptrend(drift=0.01)                         # steep ramp -> MAs far below
    spot = float(close.iloc[-1])
    rec = _rec("TOP WATCH", "caution", "DON'T CHASE", dcl=spot * 0.6, eq=-20)
    es = entry_signal.assess(close, None, rec)
    depth = (spot - es["buy_zone"]["low"]) / spot
    assert depth <= 0.20, depth                          # capped, not -40%


def test_fresh_buy_zone_anchors_to_cycle_low() -> None:
    close = _uptrend()
    spot = float(close.iloc[-1])
    rec = _rec("FRESH BUY", "now", "BUY NOW", dc_phase="new", dc_day=4,
               dcl=spot * 0.95, eq=40, bc=70)
    es = entry_signal.assess(close, None, rec)
    assert es["status"] == "buy_now"
    assert es["buy_zone"]["high"] == pytest.approx(spot, rel=1e-3)
    assert es["stop"] == pytest.approx(spot * 0.95, rel=1e-2)
    assert es["act_level"] == 3
    assert es["timing"]["opens_in_days_lo"] == 0


def test_half_size_is_partial_not_full_buy() -> None:
    close = _uptrend()
    rec = _rec("TURN SIGNALED", "now", "HALF SIZE", dc_phase="in_band", dc_day=40,
               dcl=float(close.iloc[-1]) * 0.93)
    es = entry_signal.assess(close, None, rec)
    assert es["status"] == "partial"


def test_horizon_read_penalizes_stretched_position() -> None:
    """The d63 (position) read should be worse for a very stretched name than a
    mildly extended one — captures 'great trend but a poor entry right now'."""
    close = _uptrend()
    mild = entry_signal.assess(close, None, _rec("TOP WATCH", "caution", "DON'T CHASE",
                                                 pv200=8.0, eq=-10))
    stretched = entry_signal.assess(close, None, _rec("TOP WATCH", "caution", "DON'T CHASE",
                                                      pv200=55.0, eq=-10))
    assert stretched["horizon"]["d63"] < mild["horizon"]["d63"]


def test_no_ladder_returns_none() -> None:
    assert entry_signal.assess(_uptrend(), None, {"ladder": {}}) is None
