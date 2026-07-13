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


# ---- confluence gate (MACD-2D x StochRSI-3D) --------------------------------

def test_confluence_gate_downgrades_open_entry_when_not_buyable() -> None:
    """A daily-cycle 'buy now' with NO fresh MACD-2D x StochRSI-3D confluence cross must read
    'awaiting confluence' — an honest wait state, not an open entry window."""
    close = _uptrend()
    spot = float(close.iloc[-1])
    rec = _rec("FRESH BUY", "now", "BUY NOW", dc_phase="new", dc_day=4,
               dcl=spot * 0.95, eq=40, bc=70)
    es = entry_signal.assess(close, None, rec, buyable=False)
    assert es["status"] == "await_confluence"
    assert es["confluence_gated"] is True
    assert es["act_level"] == 1                       # forming, not act-now (was 3)
    assert "awaiting" in es["headline"].lower()
    assert es["buy_zone"] is not None                 # still shows the watch zone $
    assert es["timing"]["opens_in_days_lo"] != 0      # window not declared open


def test_confluence_gate_also_downgrades_partial() -> None:
    close = _uptrend()
    rec = _rec("TURN SIGNALED", "now", "HALF SIZE", dc_phase="in_band", dc_day=40,
               dcl=float(close.iloc[-1]) * 0.93)
    es = entry_signal.assess(close, None, rec, buyable=False)
    assert es["status"] == "await_confluence" and es["confluence_gated"] is True


def test_confluence_buyable_keeps_open_entry() -> None:
    # the confluence HAS fired -> the open entry stands (buy_now), act-now ring, not gated
    close = _uptrend()
    rec = _rec("FRESH BUY", "now", "BUY NOW", dc_phase="new", dc_day=4,
               dcl=float(close.iloc[-1]) * 0.95, eq=40, bc=70)
    es = entry_signal.assess(close, None, rec, buyable=True)
    assert es["status"] == "buy_now" and es["confluence_gated"] is False
    assert es["act_level"] == 3


def test_confluence_gate_leaves_non_open_states_untouched() -> None:
    # the gate only touches an OPEN entry (buy_now/partial); an extended name is unaffected
    close = _uptrend()
    spot = float(close.iloc[-1])
    rec = _rec("TOP WATCH", "caution", "DON'T CHASE", dcl=spot * 0.85, eq=-25)
    es = entry_signal.assess(close, None, rec, buyable=False)
    assert es["status"] == "extended" and es["confluence_gated"] is False


def test_buyable_none_is_ungated_backward_compatible() -> None:
    # default buyable=None leaves the gauge exactly as before (markets without the gate wired)
    close = _uptrend()
    rec = _rec("FRESH BUY", "now", "BUY NOW", dc_phase="new", dc_day=4,
               dcl=float(close.iloc[-1]) * 0.95, eq=40, bc=70)
    assert entry_signal.assess(close, None, rec)["status"] == "buy_now"
    assert entry_signal.assess(close, None, rec, buyable=None)["status"] == "buy_now"


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


# ---- countertrend bounce (regime-gate demotion) ------------------------------

def test_countertrend_bounce_reads_bounce_wait_not_extended() -> None:
    """A COUNTERTREND BOUNCE (regime gate demoted a fired daily buy) carries urgency
    'caution' meaning 'turn not confirmed' — for a washed-out name far BELOW its
    200dma (the 600519.SS 2026-07-10 case) the headline must never claim 'Extended'."""
    close = _uptrend()
    spot = float(close.iloc[-1])
    rec = _rec("COUNTERTREND BOUNCE", "caution", "UNCONFIRMED — HIGH RISK",
               dcl=spot * 0.9, eq=-10, pv200=-12.5, pv50=-3.0)
    es = entry_signal.assess(close, None, rec)
    assert es["status"] == "bounce_wait"
    assert "extended" not in es["headline"].lower()
    assert "过度拉伸" not in es["headline_zh"]
    assert "not confirmed" in es["headline"].lower()
    assert es["act_level"] == 0                          # unchanged: stand aside
    # the wait-state price plan still renders (zone below spot, don't chase the bounce)
    assert es["buy_zone"]["high"] < spot
    assert es["chase_above"] <= spot * 1.001


def test_true_extended_still_reads_extended() -> None:
    # the split is bounce-specific: a genuinely stretched TOP WATCH keeps 'extended'
    close = _uptrend()
    rec = _rec("TOP WATCH", "caution", "DON'T CHASE", dcl=float(close.iloc[-1]) * 0.85,
               eq=-25, pv200=30.0)
    assert entry_signal.assess(close, None, rec)["status"] == "extended"
