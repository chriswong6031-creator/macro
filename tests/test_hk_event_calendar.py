"""Tests for engine/hk_event_calendar.py — the HK/US/China macro calendar leaf.

Pure date-arithmetic; display/context only; bilingual; region-tagged.
"""
from __future__ import annotations

from datetime import date

from engine import hk_event_calendar as cal


def test_events_shape_and_window():
    asof = date(2026, 6, 17)
    evs = cal.hk_macro_events(asof=asof, horizon_days=14)
    assert isinstance(evs, list) and evs
    for e in evs:
        assert e["name_en"] and e["name_zh"]          # bilingual
        assert e["region"] in ("HK", "US", "CN")
        assert e["importance"] in ("high", "med")
        assert 0 <= e["days_until"] <= 14
        assert e["is_context_only"] is True


def test_three_regions_present_over_a_month():
    """A 31-day window should surface HK, US and China releases."""
    asof = date(2026, 6, 1)
    regions = {e["region"] for e in cal.hk_macro_events(asof=asof, horizon_days=31)}
    assert {"HK", "US", "CN"} <= regions


def test_fomc_and_hkma_chain():
    """A window over the 2026-06-17 FOMC should carry FOMC + the next-day HKMA rate."""
    asof = date(2026, 6, 15)
    evs = cal.hk_macro_events(asof=asof, horizon_days=10)
    types = {e["type"] for e in evs}
    assert "FOMC" in types
    assert "HKMA_RATE" in types


def test_high_impact_strip_and_imminent():
    asof = date(2026, 6, 17)
    strip = cal.high_impact_strip(asof=asof, horizon_days=14)
    for e in strip:
        assert e["importance"] == "high"
        assert e["dow"] and e["dow_zh"] and e["md"] and e["md_zh"]
    im = cal.imminent_line(asof=asof, horizon_days=14)
    assert im is None or (im["en"] and im["zh"])


def test_sorted_by_date():
    evs = cal.hk_macro_events(asof=date(2026, 6, 1), horizon_days=30)
    dates = [e["date"] for e in evs]
    assert dates == sorted(dates)
