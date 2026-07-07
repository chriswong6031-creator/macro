"""tests/test_options_structure.py — Schema validation + chain-heat aggregation tests.

Package A — Options Sensor Contract (engine/options_structure.py).

Coverage:
  1. Schema round-trips via validate() dispatcher for all 6 schemas.
  2. Specific field constraint enforcement per schema.
  3. aggregate_chain_heat(): threshold gating, lean mapping, span math.
  4. Confidence ceiling enforcement on management_state.
  5. authority_tier and direction_reliability invariants.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone, timedelta

import pytest

from engine.options_structure import (
    AUTHORITY_DISPLAY,
    AUTHORITY_SHADOW,
    MANAGEMENT_CONFIDENCE_CEILING,
    aggregate_chain_heat,
    validate,
    validate_chain_heat_feed,
    validate_gex_state,
    validate_management_state,
    validate_matrix,
    validate_structural,
    validate_trade_plan,
)


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

NOW_ISO = "2026-07-07T20:05:00-04:00"
SESSION  = "2026-07-07"


def _make_event(
    root: str = "SPY",
    strike: float = 530.0,
    exp: str = "2026-07-18",
    right: str = "P",
    premium: float = 1_500_000.0,
    ask_share: float | None = 0.80,
    ts: str | None = None,
) -> dict:
    """Build a minimal live_flow.feed/v1 event dict."""
    if ts is None:
        ts = "2026-07-07T10:00:00Z"
    ev = {
        "root": root,
        "strike": strike,
        "exp": exp,
        "right": right,
        "premium": premium,
        "ts": ts,
    }
    if ask_share is not None:
        ev["ask_share"] = ask_share
    return ev


# ===========================================================================
# 1. GEX STATE
# ===========================================================================

def _gex_state_clean() -> dict:
    return {
        "schema": "options_structure.gex_state/v1",
        "asof": NOW_ISO,
        "root": "SPY",
        "spot": 543.2,
        "net_gex_bn": 1.8,
        "gamma_regime": "RANGE",
        "stability_pct": 71.0,
        "gamma_flip": 539.0,
        "dist_to_flip_pct": 0.77,
        "call_wall": 550.0,
        "put_wall": 535.0,
        "magnet": 542.0,
        "max_pain": 541.0,
        "pin_probability": 0.34,
        "gravity_direction": "up",
        "gravity_up_pct": 63.0,
        "cascade_trigger": None,
        "upside_trigger": 548.0,
        "oi_delta_clusters": {"new_oi": [], "exit_oi": []},
        "regime_passport": {
            "basis": "dealer-short-assumption",
            "structurally_constant": False,
            "is_index_product": True,
            "verdict": "robust-assumption",
            "note": "Index product — assumption is relatively stable.",
        },
        "authority_tier": AUTHORITY_DISPLAY,
        "reliability": {
            "levels": "display-only-until-gate",
            "regime": "assumption-signed",
        },
    }


def test_gex_state_clean():
    errors = validate_gex_state(_gex_state_clean())
    assert errors == [], errors


def test_gex_state_dispatcher():
    errors = validate(_gex_state_clean())
    assert errors == [], errors


def test_gex_state_missing_asof():
    d = _gex_state_clean()
    d["asof"] = ""
    errors = validate_gex_state(d)
    assert any("asof" in e for e in errors)


def test_gex_state_missing_root():
    d = _gex_state_clean()
    d["root"] = ""
    errors = validate_gex_state(d)
    assert any("root" in e for e in errors)


def test_gex_state_bad_regime():
    d = _gex_state_clean()
    d["gamma_regime"] = "HYPER"
    errors = validate_gex_state(d)
    assert any("gamma_regime" in e for e in errors)


def test_gex_state_valid_regimes():
    for regime in ("PIN", "DRIFT", "RANGE", "TRANSITION", "TREND", "CASCADE"):
        d = _gex_state_clean()
        d["gamma_regime"] = regime
        assert validate_gex_state(d) == [], regime


def test_gex_state_wrong_schema():
    d = _gex_state_clean()
    d["schema"] = "wrong.schema/v1"
    errors = validate_gex_state(d)
    assert any("schema" in e for e in errors)


# ===========================================================================
# 2. CHAIN HEAT FEED
# ===========================================================================

def _chain_heat_clean() -> dict:
    return {
        "schema": "options_flow.chain_heat/v1",
        "asof": NOW_ISO,
        "session_date": SESSION,
        "campaigns": [
            {
                "option_symbol": "SMH   260618P00530000",
                "ticker": "SMH",
                "right": "PUT",
                "strike": 530.0,
                "expiry": "2026-06-18",
                "dte": 20,
                "total_premium_mn": 11.97,
                "alert_count": 29,
                "span_minutes": 91.0,
                "first_seen": "2026-07-07T09:35:00Z",
                "last_seen": "2026-07-07T11:06:00Z",
                "ask_share": 0.91,
                "lean": "accumulation",
                "direction_reliability": "soft",
                "authority_tier": AUTHORITY_DISPLAY,
            }
        ],
        "authority_tier": AUTHORITY_DISPLAY,
    }


def test_chain_heat_clean():
    errors = validate_chain_heat_feed(_chain_heat_clean())
    assert errors == [], errors


def test_chain_heat_dispatcher():
    errors = validate(_chain_heat_clean())
    assert errors == [], errors


def test_chain_heat_bad_lean():
    d = _chain_heat_clean()
    d["campaigns"][0]["lean"] = "BULLISH"
    errors = validate_chain_heat_feed(d)
    assert any("lean" in e for e in errors)


def test_chain_heat_direction_reliability_must_be_soft():
    """direction_reliability may only be 'soft' in Package A."""
    d = _chain_heat_clean()
    d["campaigns"][0]["direction_reliability"] = "reliable"
    errors = validate_chain_heat_feed(d)
    assert any("direction_reliability" in e for e in errors)


def test_chain_heat_missing_asof():
    d = _chain_heat_clean()
    d["asof"] = ""
    errors = validate_chain_heat_feed(d)
    assert any("asof" in e for e in errors)


# ===========================================================================
# 3. MATRIX
# ===========================================================================

def _matrix_clean() -> dict:
    return {
        "schema": "options_structure.matrix/v1",
        "asof": NOW_ISO,
        "root": "NVDA",
        "spot": 844.8,
        "expiries": ["2026-07-07", "2026-07-18"],
        "strikes": [840.0, 850.0],
        "cells": [
            {
                "strike": 850.0,
                "expiry": "2026-07-18",
                "gex": 34.1e6,
                "call_oi": 12000,
                "put_oi": 800,
                "call_vol": 4200,
                "put_vol": 300,
                "delta_oi": {"call": 1200, "put": 0},
                "unusual": None,
            }
        ],
        "levels": {
            "call_wall": 900.0,
            "put_support": 800.0,
            "hvl": 850.0,
            "gamma_flip": 840.0,
            "max_pain": 845.0,
        },
        "heat_seeker": {
            "strike": 850.0,
            "expiry": "2026-07-18",
            "lens": "GEX",
            "standout_ratio": 1.7,
            "confidence": 0.23,
            "note": "descriptive — not a recommendation",
        },
        "authority_tier": AUTHORITY_DISPLAY,
        "reliability": {
            "note": "Sign is an assumption, not a fact. Magnitude is the reliable read.",
        },
    }


def test_matrix_clean():
    errors = validate_matrix(_matrix_clean())
    assert errors == [], errors


def test_matrix_dispatcher():
    errors = validate(_matrix_clean())
    assert errors == [], errors


def test_matrix_heat_seeker_note_enforced():
    d = _matrix_clean()
    d["heat_seeker"]["note"] = "strong buy signal"
    errors = validate_matrix(d)
    assert any("note" in e for e in errors)


def test_matrix_cell_missing_strike():
    d = _matrix_clean()
    del d["cells"][0]["strike"]
    errors = validate_matrix(d)
    assert any("strike" in e for e in errors)


def test_matrix_missing_root():
    d = _matrix_clean()
    d["root"] = ""
    errors = validate_matrix(d)
    assert any("root" in e for e in errors)


# ===========================================================================
# 4. STRUCTURAL STATE
# ===========================================================================

def _structural_clean() -> dict:
    return {
        "schema": "options_structure.structural/v1",
        "asof": NOW_ISO,
        "root": "NVDA",
        "squeeze_state": "BUILDING",
        "cascade_state": "NONE",
        "top_relevance_score": 72.0,
        "contributing_flows": 4,
        "flow_near_flip": True,
        "flow_near_wall": False,
        "dealer_regime": "TRANSITION",
        "explanation": "bullish accumulation near gamma flip in transition regime",
        "vol_ladder_suppressed": False,
        "authority_tier": AUTHORITY_SHADOW,
        "allowed_authority": "context-only-until-gauntlet",
        "reliability": {
            "structural_state": "shadow — context sensor only, not a signal",
        },
    }


def test_structural_clean():
    errors = validate_structural(_structural_clean())
    assert errors == [], errors


def test_structural_dispatcher():
    errors = validate(_structural_clean())
    assert errors == [], errors


def test_structural_bad_squeeze_state():
    d = _structural_clean()
    d["squeeze_state"] = "EXPLODING"
    errors = validate_structural(d)
    assert any("squeeze_state" in e for e in errors)


def test_structural_must_be_shadow():
    """structural/v1 MUST be shadow tier — not display."""
    d = _structural_clean()
    d["authority_tier"] = AUTHORITY_DISPLAY
    errors = validate_structural(d)
    assert any("authority_tier" in e for e in errors)


def test_structural_valid_states():
    for sq in ("NONE", "BUILDING", "ACTIVE"):
        for ca in ("NONE", "BUILDING", "ACTIVE"):
            d = _structural_clean()
            d["squeeze_state"] = sq
            d["cascade_state"] = ca
            assert validate_structural(d) == [], (sq, ca)


# ===========================================================================
# 5. ORACLE TRADE PLAN
# ===========================================================================

def _trade_plan_clean() -> dict:
    return {
        "schema": "oracle.trade_plan/v1",
        "id": "nvda-bull-20260707-001",
        "asof": NOW_ISO,
        "asset": "NVDA",
        "direction": "BULL",
        "thesis": "AI capex cycle driving upside through Q4.",
        "source_engines": ["neural_web"],
        "trigger": 910.0,
        "entry": 905.0,
        "invalidation": 870.0,
        "targets": [950.0, 980.0, 1050.0],
        "horizon_days": 90,
        "min_hold_days": 14,
        "tranche": 1,
        "option_contract": {
            "type": "CALL",
            "strike": 910.0,
            "expiry": "2026-09-19",
            "entry_premium": 5.1,
        },
        "management_ref": "oracle/state/nvda-bull-20260707-001.json",
        "authority_tier": AUTHORITY_DISPLAY,
    }


def test_trade_plan_clean():
    errors = validate_trade_plan(_trade_plan_clean())
    assert errors == [], errors


def test_trade_plan_dispatcher():
    errors = validate(_trade_plan_clean())
    assert errors == [], errors


def test_trade_plan_bad_direction():
    d = _trade_plan_clean()
    d["direction"] = "NEUTRAL"
    errors = validate_trade_plan(d)
    assert any("direction" in e for e in errors)


def test_trade_plan_bad_tranche():
    d = _trade_plan_clean()
    d["tranche"] = 3
    errors = validate_trade_plan(d)
    assert any("tranche" in e for e in errors)


def test_trade_plan_empty_source_engines():
    """source_engines must be non-empty: LLMs cannot originate plans."""
    d = _trade_plan_clean()
    d["source_engines"] = []
    errors = validate_trade_plan(d)
    assert any("source_engines" in e for e in errors)


def test_trade_plan_bear():
    d = _trade_plan_clean()
    d["direction"] = "BEAR"
    assert validate_trade_plan(d) == []


# ===========================================================================
# 6. ORACLE MANAGEMENT STATE
# ===========================================================================

def _management_state_clean() -> dict:
    return {
        "schema": "oracle.management_state/v1",
        "id": "nvda-bull-20260707-001",
        "asof": NOW_ISO,
        "phase": "triggered_pre_t1",
        "management_confidence": 72.2,
        "raw_confidence": 73.1,
        "delta_vs_base": 6.2,
        "recommended_action": "hold",
        "components": {
            "validity": 81.0,
            "progress": 40.0,
            "pace": 66.0,
            "retention": 50.0,
            "overlay": 55.0,
        },
        "geometry": {
            "dist_to_stop_r": 1.6,
            "dist_to_t1_r": 0.8,
            "horizon_pct_used": 41.0,
        },
        "change_reason": "Trigger Confirmed",
        "confidence_ceiling": MANAGEMENT_CONFIDENCE_CEILING,
        "authority": "trade-management-only-NOT-pick-rank",
        "authority_tier": AUTHORITY_DISPLAY,
    }


def test_management_state_clean():
    errors = validate_management_state(_management_state_clean())
    assert errors == [], errors


def test_management_state_dispatcher():
    errors = validate(_management_state_clean())
    assert errors == [], errors


def test_management_state_confidence_ceiling_enforced():
    """management_confidence must not exceed MANAGEMENT_CONFIDENCE_CEILING (92)."""
    d = _management_state_clean()
    d["management_confidence"] = 95.0
    errors = validate_management_state(d)
    assert any("ceiling" in e or "exceed" in e for e in errors)


def test_management_state_at_ceiling_ok():
    d = _management_state_clean()
    d["management_confidence"] = float(MANAGEMENT_CONFIDENCE_CEILING)
    assert validate_management_state(d) == []


def test_management_state_bad_phase():
    d = _management_state_clean()
    d["phase"] = "won"
    errors = validate_management_state(d)
    assert any("phase" in e for e in errors)


def test_management_state_all_phases():
    phases = [
        "pre_trigger", "triggered_pre_t1", "at_t1", "between_t1_t2",
        "at_t2", "overtime", "invalidated",
    ]
    for p in phases:
        d = _management_state_clean()
        d["phase"] = p
        assert validate_management_state(d) == [], p


def test_management_state_bad_action():
    d = _management_state_clean()
    d["recommended_action"] = "double_down"
    errors = validate_management_state(d)
    assert any("recommended_action" in e for e in errors)


# ===========================================================================
# 7. DISPATCHER — unknown schema
# ===========================================================================

def test_dispatcher_unknown_schema():
    errors = validate({"schema": "totally.unknown/v9"})
    assert any("Unknown schema" in e for e in errors)


# ===========================================================================
# 8. CHAIN HEAT AGGREGATION
# ===========================================================================

def _ts(hhmm: str) -> str:
    """Return ISO timestamp string for today at given HH:MM UTC."""
    return f"2026-07-07T{hhmm}:00Z"


class TestAggregateChainHeat:
    """Unit tests for aggregate_chain_heat()."""

    def test_empty_input(self):
        result = aggregate_chain_heat([])
        assert result == []

    def test_single_event_below_threshold(self):
        """A single $1M event (below $3M) yields no campaigns."""
        ev = _make_event(premium=1_000_000.0, ts=_ts("10:00"))
        result = aggregate_chain_heat([ev])
        assert result == []

    def test_single_event_above_threshold_but_min_alerts_2(self):
        """1 event at $5M passes premium gate but fails min_alerts=2."""
        ev = _make_event(premium=5_000_000.0, ts=_ts("10:00"))
        result = aggregate_chain_heat([ev], min_premium_mn=3.0, min_alerts=2)
        assert result == []

    def test_single_event_min_alerts_1(self):
        """With min_alerts=1, a single $5M event should surface."""
        ev = _make_event(premium=5_000_000.0, ts=_ts("10:00"))
        result = aggregate_chain_heat([ev], min_premium_mn=3.0, min_alerts=1)
        assert len(result) == 1
        assert result[0]["total_premium_mn"] == pytest.approx(5.0, abs=0.01)

    def test_two_events_same_contract_aggregate(self):
        """Two events for the same contract sum premium and count."""
        ev1 = _make_event(premium=2_000_000.0, ts=_ts("10:00"))
        ev2 = _make_event(premium=2_000_000.0, ts=_ts("10:30"))
        result = aggregate_chain_heat([ev1, ev2], min_premium_mn=3.0, min_alerts=2)
        assert len(result) == 1
        c = result[0]
        assert c["total_premium_mn"] == pytest.approx(4.0, abs=0.01)
        assert c["alert_count"] == 2

    def test_span_minutes_math(self):
        """span_minutes = time between first and last event."""
        ev1 = _make_event(premium=2_000_000.0, ts="2026-07-07T10:00:00Z")
        ev2 = _make_event(premium=2_000_000.0, ts="2026-07-07T11:31:00Z")
        result = aggregate_chain_heat([ev1, ev2], min_premium_mn=3.0, min_alerts=2)
        assert len(result) == 1
        assert result[0]["span_minutes"] == pytest.approx(91.0, abs=0.1)

    def test_lean_accumulation(self):
        """ask_share >= 0.65 → lean='accumulation'."""
        ev1 = _make_event(premium=2_000_000.0, ask_share=0.91, ts=_ts("10:00"))
        ev2 = _make_event(premium=2_000_000.0, ask_share=0.91, ts=_ts("10:10"))
        result = aggregate_chain_heat([ev1, ev2], min_premium_mn=3.0, min_alerts=2)
        assert len(result) == 1
        assert result[0]["lean"] == "accumulation"

    def test_lean_distribution(self):
        """ask_share <= 0.35 → lean='distribution'."""
        ev1 = _make_event(premium=2_000_000.0, ask_share=0.20, ts=_ts("10:00"))
        ev2 = _make_event(premium=2_000_000.0, ask_share=0.20, ts=_ts("10:10"))
        result = aggregate_chain_heat([ev1, ev2], min_premium_mn=3.0, min_alerts=2)
        assert len(result) == 1
        assert result[0]["lean"] == "distribution"

    def test_lean_contested(self):
        """ask_share between 0.35 and 0.65 → lean='contested'."""
        ev1 = _make_event(premium=2_000_000.0, ask_share=0.50, ts=_ts("10:00"))
        ev2 = _make_event(premium=2_000_000.0, ask_share=0.50, ts=_ts("10:10"))
        result = aggregate_chain_heat([ev1, ev2], min_premium_mn=3.0, min_alerts=2)
        assert len(result) == 1
        assert result[0]["lean"] == "contested"

    def test_lean_missing_ask_share(self):
        """When ask_share is absent, lean defaults to 'contested'."""
        ev1 = _make_event(premium=2_000_000.0, ask_share=None, ts=_ts("10:00"))
        ev2 = _make_event(premium=2_000_000.0, ask_share=None, ts=_ts("10:10"))
        result = aggregate_chain_heat([ev1, ev2], min_premium_mn=3.0, min_alerts=2)
        assert len(result) == 1
        assert result[0]["lean"] == "contested"
        assert result[0]["ask_share"] is None

    def test_direction_reliability_always_soft(self):
        """direction_reliability is hardcoded 'soft' — cannot be elevated in aggregator."""
        ev1 = _make_event(premium=2_000_000.0, ts=_ts("10:00"))
        ev2 = _make_event(premium=2_000_000.0, ts=_ts("10:10"))
        result = aggregate_chain_heat([ev1, ev2], min_premium_mn=3.0, min_alerts=2)
        assert len(result) == 1
        assert result[0]["direction_reliability"] == "soft"

    def test_authority_tier_always_display(self):
        ev1 = _make_event(premium=2_000_000.0, ts=_ts("10:00"))
        ev2 = _make_event(premium=2_000_000.0, ts=_ts("10:10"))
        result = aggregate_chain_heat([ev1, ev2], min_premium_mn=3.0, min_alerts=2)
        assert len(result) == 1
        assert result[0]["authority_tier"] == AUTHORITY_DISPLAY

    def test_separate_contracts_separate_campaigns(self):
        """Events for different contracts produce separate campaigns."""
        ev_call = _make_event(right="C", premium=2_000_000.0, ts=_ts("10:00"))
        ev_call2 = _make_event(right="C", premium=2_000_000.0, ts=_ts("10:10"))
        ev_put  = _make_event(right="P", premium=4_000_000.0, ts=_ts("10:00"))
        ev_put2 = _make_event(right="P", premium=4_000_000.0, ts=_ts("10:10"))
        result = aggregate_chain_heat(
            [ev_call, ev_call2, ev_put, ev_put2],
            min_premium_mn=3.0, min_alerts=2,
        )
        assert len(result) == 2
        tickers = [c["right"] for c in result]
        assert "CALL" in tickers
        assert "PUT" in tickers

    def test_sorted_by_premium_descending(self):
        """Campaigns are sorted by total_premium_mn descending."""
        ev_a1 = _make_event(root="AAA", premium=1_000_000.0, ts=_ts("10:00"))
        ev_a2 = _make_event(root="AAA", premium=1_000_000.0, ts=_ts("10:10"))
        ev_b1 = _make_event(root="BBB", premium=5_000_000.0, ts=_ts("10:00"))
        ev_b2 = _make_event(root="BBB", premium=5_000_000.0, ts=_ts("10:10"))
        # AAA meets $2M but not $3M → filtered; BBB = $10M → surfaced
        result = aggregate_chain_heat(
            [ev_a1, ev_a2, ev_b1, ev_b2],
            min_premium_mn=3.0, min_alerts=2,
        )
        assert len(result) == 1
        assert result[0]["ticker"] == "BBB"

    def test_multiple_campaigns_sorted(self):
        """Multiple campaigns surface in descending order."""
        events = []
        for i, (root, prem) in enumerate([("AAA", 2_000_000), ("BBB", 4_000_000)]):
            events.append(_make_event(root=root, premium=prem, ts=_ts("10:00")))
            events.append(_make_event(root=root, premium=prem, ts=_ts("10:10")))
        result = aggregate_chain_heat(events, min_premium_mn=3.0, min_alerts=2)
        # Only BBB ($8M) passes the $3M gate; AAA ($4M total) also passes
        assert len(result) == 2
        assert result[0]["ticker"] == "BBB"   # higher premium first
        assert result[1]["ticker"] == "AAA"

    def test_custom_threshold(self):
        """min_premium_mn=5.0 filters out $4M campaigns."""
        ev1 = _make_event(premium=2_000_000.0, ts=_ts("10:00"))
        ev2 = _make_event(premium=2_000_000.0, ts=_ts("10:10"))
        result = aggregate_chain_heat([ev1, ev2], min_premium_mn=5.0, min_alerts=2)
        assert result == []

    def test_events_with_invalid_right_skipped(self):
        """Events without a valid C/P right code are silently skipped."""
        ev_bad = {"root": "SPY", "strike": 530, "exp": "2026-07-18",
                  "right": "", "premium": 5_000_000, "ts": _ts("10:00")}
        ev_bad2 = dict(ev_bad, ts=_ts("10:10"))
        result = aggregate_chain_heat([ev_bad, ev_bad2], min_premium_mn=3.0, min_alerts=2)
        assert result == []

    def test_option_symbol_format(self):
        """option_symbol follows OCC-style padded format."""
        ev1 = _make_event(root="SPY", strike=530.0, exp="2026-07-18",
                          right="P", premium=2_000_000.0, ts=_ts("10:00"))
        ev2 = _make_event(root="SPY", strike=530.0, exp="2026-07-18",
                          right="P", premium=2_000_000.0, ts=_ts("10:10"))
        result = aggregate_chain_heat([ev1, ev2], min_premium_mn=3.0, min_alerts=2)
        assert len(result) == 1
        sym = result[0]["option_symbol"]
        assert "SPY" in sym
        assert "P" in sym

    def test_smh_worked_example(self):
        """Reproduce the worked example from chain_heat_spec §1: SMH 530P $11.97M 29 alerts."""
        events = []
        base_premium = 11_970_000 / 29  # ~$412k per alert
        for i in range(29):
            hh = 9 + (i * 3) // 60
            mm = (35 + i * 3) % 60
            ts = f"2026-07-07T{hh:02d}:{mm:02d}:00Z"
            events.append(_make_event(
                root="SMH", strike=530.0, exp="2026-06-18",
                right="P", premium=base_premium, ask_share=0.91, ts=ts,
            ))
        result = aggregate_chain_heat(events, min_premium_mn=3.0, min_alerts=2)
        assert len(result) == 1
        c = result[0]
        assert c["ticker"] == "SMH"
        assert c["right"] == "PUT"
        assert c["alert_count"] == 29
        assert c["total_premium_mn"] == pytest.approx(11.97, abs=0.05)
        assert c["lean"] == "accumulation"   # ask_share=0.91 >= 0.65
        assert c["direction_reliability"] == "soft"
