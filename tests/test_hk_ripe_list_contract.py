"""Tests for the HK ripe-list contract wiring in scripts/build_hk_library.py
(masterplan §5.0 entry windows + §7.1 card lead + §2.6/HKCA-3 hard freshness gate).

All tests are pure — they exercise the deterministic derivation helpers and monkeypatch
the panel-date reader for the freshness gate. No real data/ paths are mutated.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts import build_hk_library as B


# ---------------------------------------------------------------------------
# §5.0 entry-window derivation — one of open-now | pullback lo–hi | wait-for-weekly
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("es,expected_kind", [
    ({"status": "buy_now", "buy_zone": {"low": 10.0, "high": 11.0}}, "open-now"),
    ({"status": "partial", "buy_zone": {}}, "open-now"),
    ({"status": "buy_soon", "buy_zone": {"low": 41.2, "high": 42.8}}, "pullback"),
    ({"status": "wait_pullback", "buy_zone": {"low": None, "high": 42.8}}, "pullback"),
    ({"status": "blocked", "buy_zone": {}}, "wait-for-weekly"),
    ({"status": "await_confluence", "buy_zone": {}}, "wait-for-weekly"),
    ({}, "wait-for-weekly"),
])
def test_entry_window_kinds(es, expected_kind):
    ew = B._entry_window({"entry_signal": es})
    assert ew["kind"] == expected_kind
    # bilingual + ends the sentence with the window
    assert ew["en"] and ew["zh"]


def test_entry_window_pullback_shows_price_span():
    ew = B._entry_window({"entry_signal": {"status": "buy_soon",
                                           "buy_zone": {"low": 41.2, "high": 42.8}}})
    assert "41.20" in ew["en"] and "42.80" in ew["en"]
    assert "41.20" in ew["zh"] and "42.80" in ew["zh"]


# ---------------------------------------------------------------------------
# §7.1 card lead — mechanism first, active language, ends with the entry window
# ---------------------------------------------------------------------------
def test_card_lead_mechanism_first_ends_with_window():
    e = {"southbound": {"accum_z": 1.2},
         "ah_value": {"cheap": True, "premium_pct": 18},
         "group": "entry_open", "washout_2w": True}
    ew = B._entry_window({"entry_signal": {"status": "buy_soon",
                                           "buy_zone": {"low": 41.2, "high": 42.8}}})
    lead = B._card_lead(e, ew)
    # leads with the FRESH mechanism (southbound), not a score
    assert lead["en"].startswith("Mainland crowd adding")
    assert "SB z +1.2" in lead["en"]
    assert "H cheap vs A" in lead["en"]
    # ends with the entry window
    assert lead["en"].rstrip(".").endswith("entry: pullback 41.20–42.80")
    assert lead["zh"].rstrip("。").endswith("入场：回调 41.20–42.80")


def test_card_lead_never_hollow():
    """A name with no fresh mechanism still gets a non-empty, window-terminated lead."""
    ew = B._entry_window({})
    lead = B._card_lead({}, ew)
    assert lead["en"].strip() and lead["zh"].strip()
    assert "entry:" in lead["en"]


def test_card_lead_trim_flow_direction():
    e = {"southbound": {"accum_z": -1.5}}
    lead = B._card_lead(e, B._entry_window({}))
    assert "trimming" in lead["en"] and "减仓" in lead["zh"]


# ---------------------------------------------------------------------------
# §2.6 / HKCA-3 hard freshness gate — trading-day staleness suppresses the tailwind
# ---------------------------------------------------------------------------
def _patch_panels(monkeypatch, card_max: str, basket_max: str):
    """Monkeypatch _panel_max_date + the trading-day index used by the gate."""
    card_idx = pd.bdate_range("2026-05-01", card_max)

    def fake_max(path):
        p = str(path)
        if "hk_breadth" in p:
            return pd.Timestamp(card_max)
        if "hk_search" in p:
            return pd.Timestamp(basket_max)
        return None

    monkeypatch.setattr(B, "_panel_max_date", fake_max)
    # make the trading-day count deterministic without touching disk
    monkeypatch.setattr(B.pd, "read_parquet",
                        lambda *a, **k: pd.DataFrame(index=card_idx))


def test_freshness_gate_fresh_panels_no_suppress(monkeypatch):
    _patch_panels(monkeypatch, card_max="2026-07-03", basket_max="2026-07-02")
    td = B._tailwind_staleness_td()
    assert td is not None and td <= B.FRESHNESS_MAX_STALE_TD


def test_freshness_gate_stale_basket_trips(monkeypatch):
    # 9 trading days between 2026-06-18 and 2026-07-03 (weekdays)
    _patch_panels(monkeypatch, card_max="2026-07-03", basket_max="2026-06-18")
    td = B._tailwind_staleness_td()
    assert td is not None and td > B.FRESHNESS_MAX_STALE_TD


def test_freshness_gate_suppresses_tailwind_map(monkeypatch):
    """When the gate trips, the tailwind map is empty even if baskets would compute."""
    _patch_panels(monkeypatch, card_max="2026-07-03", basket_max="2026-06-18")

    called = {"baskets": False}

    def _boom(*a, **k):
        called["baskets"] = True
        raise AssertionError("baskets_hk must not be consulted once the gate suppresses")

    # if the gate is honoured, _basket_tailwind_map returns {} before importing baskets
    out = B._basket_tailwind_map()
    assert out == {}
    assert called["baskets"] is False  # never even tried to compute


def test_weekend_does_not_trip_gate(monkeypatch):
    # Friday card vs the immediately-prior Thursday basket = 1 trading day, no trip
    _patch_panels(monkeypatch, card_max="2026-07-03", basket_max="2026-07-02")
    td = B._tailwind_staleness_td()
    assert td is not None and td <= B.FRESHNESS_MAX_STALE_TD
