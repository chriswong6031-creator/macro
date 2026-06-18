"""Tests for engine.event_risk — the non-directional event-risk banner.

Guards the honesty invariants: never directional, never a dampener, defensive on
missing data, and the fragility overlay reads the real latest.json keys.
"""
from __future__ import annotations

from datetime import date

from engine import event_risk as er


def _ev(etype, d, **kw):
    return {"type": etype, "date": d, "label": kw.get("label", etype),
            "time_et": kw.get("time_et", "14:00"), "md": kw.get("md", ""), "dow": kw.get("dow", "")}


TODAY = date(2026, 6, 15)


def test_no_events_returns_hidden():
    out = er.snapshot({}, events=[], today=TODAY)
    assert out["show"] is False


def test_picks_nearest_event_in_window():
    events = [_ev("CPI", "2026-06-20"), _ev("FOMC", "2026-06-17"), _ev("NFP", "2026-07-02")]
    out = er.snapshot({}, events=events, today=TODAY)
    assert out["show"] is True
    assert out["type"] == "FOMC"          # nearest (17th) wins
    assert out["days_to"] == 2


def test_past_events_ignored():
    events = [_ev("FOMC", "2026-06-10")]  # already past
    assert er.snapshot({}, events=events, today=TODAY)["show"] is False


def test_non_directional_invariant():
    out = er.snapshot({}, events=[_ev("FOMC", "2026-06-17")], today=TODAY)
    assert out["direction"] == "two-sided"
    # up-rate must be ~coin-flip, never a directional bet
    assert 0.45 <= out["up_rate"] <= 0.6
    blob = (out["headline_en"] + out["sub_en"]).lower()
    # no directional FORECAST verbs (it may say "not a sell signal" — that's allowed)
    for phrase in ("will fall", "will rise", "expect a drop", "expect a selloff", "likely to fall", "likely to rise"):
        assert phrase not in blob
    assert "two-sided" in blob and "not a sell signal" in blob


def test_vol_tier_mapping():
    assert er.snapshot({}, events=[_ev("FOMC", "2026-06-17")], today=TODAY)["vol_tier"] == "high"
    assert er.snapshot({}, events=[_ev("PPI", "2026-06-17")], today=TODAY)["vol_tier"] == "elevated"


def test_fragility_reads_real_keys_and_overlays():
    latest = {
        "turning_point": {"present": True},
        "cross_asset": {"absorption_pctile_5y": 0.96},
        "fed_path": {"gap": {"gap_bp": 38}},
        "conditions": {"risk_appetite": {"stock_bond_corr": 0.67}},
    }
    frag = er.fragility(latest)
    assert frag["fragile"] is True
    assert frag["score"] == 4
    out = er.snapshot(latest, events=[_ev("FOMC", "2026-06-17")], today=TODAY)
    assert out["fragility"]["fragile"] is True
    assert "FRAGILE" in out["headline_en"]
    assert len(out["fragility"]["reasons"]) == 4


def test_not_fragile_when_calm():
    latest = {"turning_point": {"present": False}, "cross_asset": {"absorption_pctile_5y": 0.4},
              "fed_path": {"gap": {"gap_bp": 5}}}
    frag = er.fragility(latest)
    assert frag["fragile"] is False
    assert frag["score"] == 0


def test_defensive_on_missing_or_none():
    assert er.snapshot(None, events=[], today=TODAY)["show"] is False
    # malformed event dicts must not crash
    out = er.snapshot({}, events=[{"type": "FOMC"}, {"date": "not-a-date"}], today=TODAY)
    assert out["show"] is False
    # fragility on empty dict is safe
    assert er.fragility({})["fragile"] is False


def test_is_context_only_always():
    assert er.snapshot({}, events=[], today=TODAY)["is_context_only"] is True
    assert er.snapshot({}, events=[_ev("FOMC", "2026-06-17")], today=TODAY)["is_context_only"] is True
