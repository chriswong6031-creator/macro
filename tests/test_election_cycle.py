"""Tests for engine/election_cycle.py + its wiring into engine/risk_radar.py.

The load-bearing invariant: the election cycle is a MODULATOR, never an alert originator.
These tests pin (1) the cycle math, (2) that the sensitivity nudge fires ONLY in the
risk-ON midterm window, (3) that it can NEVER manufacture a loud (elevated+) banner — the
context gate still rules — and (4) that it can't conjure an alert from a calm tape.
"""
from __future__ import annotations

import pandas as pd

from engine import election_cycle as ec
from engine import risk_radar as rr


# --- cycle math --------------------------------------------------------------
def test_year_in_term_anchors():
    assert ec.year_in_term(2025) == 1   # Trump inaug Jan 2025 = post-election
    assert ec.year_in_term(2026) == 2   # midterm
    assert ec.year_in_term(2027) == 3   # pre-election
    assert ec.year_in_term(2028) == 4   # election
    assert ec.year_in_term(2024) == 4   # election (Y%4==0)
    assert ec.year_in_term(2022) == 2 and ec.year_in_term(2018) == 2 and ec.year_in_term(1994) == 2


def test_context_flags():
    mid_win = ec.context("2026-06-28")     # midterm, inside Apr-Oct, before H2
    assert mid_win["is_midterm"] and mid_win["in_drawdown_window"] and mid_win["show"]
    assert not mid_win["in_h2"]
    mid_h2 = ec.context("2026-08-15")      # midterm, H2, trough zone
    assert mid_h2["in_h2"] and mid_h2["in_trough_window"]
    off = ec.context("2025-08-15")         # non-midterm
    assert not off["is_midterm"] and not off["show"] and off["sector_bias"] is None
    mid_winter = ec.context("2026-02-01")  # midterm but outside the Apr-Oct window
    assert mid_winter["is_midterm"] and not mid_winter["in_drawdown_window"]


# --- modulation: the one defensible slice ------------------------------------
def test_modulation_band_nudge_only_risk_on_window():
    # risk-ON inside the midterm window = the measured ~1.25x cut -> nudge fires
    on = ec.modulation("2026-08-15", spy_risk_on=True)
    assert on["band_delta"] > 0 and on["risk_on_slice"] and on["active"]
    assert on["gross_mult"] < 1.0
    # risk-OFF inside the window = near-collinear with price-already-weak -> NO band nudge,
    # but the small sizing prior still applies (window-wide)
    off = ec.modulation("2026-08-15", spy_risk_on=False)
    assert off["band_delta"] == 0.0 and not off["risk_on_slice"]
    assert off["active"] and off["gross_mult"] < 1.0
    # outside a midterm year: nothing at all
    none_ = ec.modulation("2025-08-15", spy_risk_on=True)
    assert none_["band_delta"] == 0.0 and none_["gross_mult"] == 1.0 and not none_["active"]
    # midterm but outside Apr-Oct: inactive
    winter = ec.modulation("2026-02-01", spy_risk_on=True)
    assert not winter["active"] and winter["band_delta"] == 0.0


def test_sector_bias_only_midterm_h2():
    sb = ec.sector_bias("2026-09-01")
    assert sb is not None and sb["display_only"]
    favor = {f["ticker"] for f in sb["favor"]}
    avoid = {a["ticker"] for a in sb["avoid"]}
    assert "XLV" in favor and "XLE" in avoid
    assert ec.sector_bias("2026-03-01") is None   # not H2
    assert ec.sector_bias("2025-09-01") is None   # not midterm


# --- integration through risk_radar.compute() --------------------------------
def _sigs(**legs):
    idx = pd.to_datetime(["2026-08-14", "2026-08-15"])
    return pd.DataFrame({leg: [v, v] for leg, v in legs.items()}, index=idx)


_RISK_ON = {"met": False, "spy_below_200dma": False, "breadth_weak": None}
_RISK_OFF = {"met": True, "spy_below_200dma": True, "breadth_weak": True}


def test_cycle_cannot_manufacture_loud_banner_when_risk_on():
    # A credit scare that WOULD be 'elevated' on its own, but the tape is risk-ON (gate not met).
    sigs = _sigs(credit_oas_roc=0.96)
    out = rr.compute(sigs=sigs, asof="2026-08-15", gate=_RISK_ON)
    assert out["cycle_context"] and out["cycle_context"]["is_midterm"]
    assert out["cycle_context"]["modulation"]["risk_on_slice"] is True
    # the loud banner is still gated: capped at caution, NOT elevated/risk-off
    assert out["state"] == "caution"
    assert out["alert"] is False


def test_cycle_nudge_cannot_conjure_alert_from_calm():
    out = rr.compute(sigs=_sigs(credit_oas_roc=0.20, rates_move=0.20), asof="2026-08-15", gate=_RISK_ON)
    assert out["state"] == "calm"   # nudged bands still far above a calm tape


def test_normal_elevated_behavior_preserved_when_risk_off():
    # Broad tape breaking (gate met) + a screaming scare -> the radar still goes loud as before;
    # in the risk-OFF slice the calendar adds only the sizing trim (no band nudge).
    sigs = _sigs(credit_oas_roc=0.96)
    out = rr.compute(sigs=sigs, asof="2026-08-15", gate=_RISK_OFF)
    assert out["state"] in ("elevated", "risk-off")
    assert out["cycle_context"]["modulation"]["band_delta"] == 0.0
    assert out["gross_factor"] < rr._gross_for("elevated")   # sizing prior applied


def test_non_midterm_year_is_passthrough():
    sigs = _sigs(credit_oas_roc=0.96)
    out = rr.compute(sigs=sigs, asof="2025-08-15", gate=_RISK_OFF)
    cyc = out["cycle_context"]
    assert cyc is not None and not cyc["is_midterm"] and not cyc["show"]
    assert cyc["modulation"]["active"] is False
    assert out["gross_factor"] == rr._gross_for(out["state"])   # untouched
