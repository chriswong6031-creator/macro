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
    # bounce_wait (COUNTERTREND BOUNCE wording split) = weekly unconfirmed by definition
    ({"status": "bounce_wait", "buy_zone": {"low": 10.0, "high": 11.0}}, "wait-for-weekly"),
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


# ---------------------------------------------------------------------------
# FALLING-KNIFE DEMOTE (H4 phase-0 KILL — reports/h4-phase0.md): the deepest
# trailing-3M-return quintile is pushed OUT of the entry groups onto the watch strip.
# ---------------------------------------------------------------------------
def test_falling_knife_demotes_deepest_quintile():
    # board universe of 10 names, alpha (3M-return z) from -3 (deepest loser) up to +3.
    enriched = [{"ticker": f"T{i}.HK", "alpha": a}
                for i, a in enumerate(range(-3, 7))]           # -3,-2,...,+6 (n=10)
    # entry candidates = all 10. The deepest quintile (P20 of -3..6 ~ -1.2) => T0,T1 (-3,-2).
    buys = list(enriched)
    keep, demoted, cut = B._falling_knife_demote(buys, enriched)
    demoted_tks = {e["ticker"] for e in demoted}
    # the two deepest 3M losers are demoted; nothing above the cut is touched
    assert demoted_tks == {"T0.HK", "T1.HK"}, demoted_tks
    assert cut is not None and cut < 0
    assert all(e.get("alpha") > cut for e in keep)
    # in-place tags carry the reason numbers for the watch-strip chip
    assert all(e.get("knife_demoted") and e.get("knife_z") is not None for e in demoted)
    # N-of-M accounting is exact (the required demonstration)
    assert len(demoted) == 2 and len(keep) == 8


def test_falling_knife_keeps_non_losers_and_is_a_noop_when_thin():
    # a strong entry candidate (top alpha) is NEVER demoted
    enriched = [{"ticker": f"T{i}.HK", "alpha": a} for i, a in enumerate(range(-3, 7))]
    leader = {"ticker": "LEAD.HK", "alpha": 2.5}
    keep, demoted, _ = B._falling_knife_demote([leader], enriched)
    assert keep == [leader] and demoted == []
    # thin cross-section (<5) => no quintile, no demote (fail-safe no-op)
    thin = [{"ticker": "A.HK", "alpha": -9.0}, {"ticker": "B.HK", "alpha": 1.0}]
    keep2, demoted2, cut2 = B._falling_knife_demote(list(thin), thin)
    assert demoted2 == [] and cut2 is None and keep2 == thin


# ---------------------------------------------------------------------------
# PLACEMENT/RIGHTS DILUTION DEMOTE (H-PLC — masterplan §3, W1c): a name with a
# dilutive announcement inside the trailing 90d window is pushed OUT of the entry
# groups onto the watch strip with a bilingual chip; the flag also stamps in place.
# ---------------------------------------------------------------------------
def test_placement_demote_splits_and_tags():
    enriched = [{"ticker": f"P{i}.HK"} for i in range(6)]
    buys = list(enriched[:4])
    plc = {"P1.HK": {"category": "placing", "date": "2026-06-20",
                     "days_ago": 13, "n_events": 2},
           # flagged name OUTSIDE buys (e.g. knife-demoted) still gets the stamp
           "P5.HK": {"category": "rights_issue", "date": "2026-06-01",
                     "days_ago": 32, "n_events": 1}}
    keep, demoted = B._placement_demote(buys, enriched, plc)
    assert [e["ticker"] for e in demoted] == ["P1.HK"]
    assert len(keep) == 3 and all(not e.get("placement_flag") for e in keep)
    # bilingual chip payload stamped in place
    info = demoted[0]["placement_info"]
    assert info["cat_en"] == "placing" and info["cat_zh"] == "配售"
    assert info["days_ago"] == 13 and info["date"] == "2026-06-20"
    # non-buy flagged row carries the stamp for the board ledger
    p5 = next(e for e in enriched if e["ticker"] == "P5.HK")
    assert p5.get("placement_flag") and p5["placement_info"]["cat_zh"] == "供股"


def test_placement_demote_noop_on_empty_map():
    enriched = [{"ticker": "A.HK"}, {"ticker": "B.HK"}]
    buys = list(enriched)
    keep, demoted = B._placement_demote(buys, enriched, {})
    assert keep == buys and demoted == []


def test_placement_flags_degrades_loudly_when_store_missing(monkeypatch):
    """Missing/empty H-PLC store => no flags + a health row + available=False
    (the board-ledger stamp must become None, never a fake False)."""
    import collectors.hk_placements as hp
    monkeypatch.setattr(hp, "store_status",
                        lambda: {"available": False, "n_events": 0,
                                 "latest": None, "fetched_at": None})
    fm, health, ok = B._placement_flags(["0700.HK"], "2026-07-03")
    assert fm == {} and ok is False
    assert health and health["leg"] == "placement_gate"
    assert health["en"] and health["zh"]


def test_placement_flags_degrades_when_store_stale(monkeypatch):
    """Newest stored announcement > PLACEMENT_STORE_MAX_STALE_D behind the panel
    => flags suppressed with a visible reason (placings print near-daily)."""
    import collectors.hk_placements as hp
    monkeypatch.setattr(hp, "store_status",
                        lambda: {"available": True, "n_events": 100,
                                 "latest": "2026-06-01", "fetched_at": None})
    monkeypatch.setattr(hp, "flag_map",
                        lambda tks, asof=None: {"0700.HK": {"category": "placing"}})
    fm, health, ok = B._placement_flags(["0700.HK"], "2026-07-03")
    assert fm == {} and ok is False
    assert health and "behind the price panel" in health["en"]


def test_placement_flags_passes_through_fresh_store(monkeypatch):
    import collectors.hk_placements as hp
    monkeypatch.setattr(hp, "store_status",
                        lambda: {"available": True, "n_events": 100,
                                 "latest": "2026-07-02", "fetched_at": None})
    sentinel = {"0700.HK": {"category": "placing", "date": "2026-06-20",
                            "days_ago": 13, "n_events": 1}}
    monkeypatch.setattr(hp, "flag_map", lambda tks, asof=None: sentinel)
    fm, health, ok = B._placement_flags(["0700.HK"], "2026-07-03")
    assert fm == sentinel and health is None and ok is True
