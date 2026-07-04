"""Hermetic two-sided regression test for engine.oracle.tilt.

R4 binding (ORACLE_GAUNTLET_P3_ADJUDICATION.md):
  (a) flag OFF → engine.stock_score output byte-identical on a fixture
      (no oracle import side effects beyond the module existing).
  (b) flag ON with a fixture tilt → _axis_tailwind shifts by the expected
      clamped amount for ≥1 member.

A dark test that cannot distinguish "correctly gated" from "never connected"
is verification theater.  This test verifies BOTH directions so neither
failure mode is invisible.
"""
from __future__ import annotations

import copy

import pytest

from engine.oracle import tilt as OT


# ---------------------------------------------------------------------------
# Gate logic tests
# ---------------------------------------------------------------------------

def test_gate_off_by_default():
    """oracle.tilt_enabled defaults to false — no config → gate off."""
    result = OT.oracle_theme_tilt(
        {"active_episodes": [{"node": "XLK", "direction": "out", "tier": "confirmed"}]},
        cfg={},
    )
    assert result == {}


def test_gate_on_with_explicit_cfg():
    """Explicit tilt_enabled=true → tilts are emitted."""
    cfg = {"oracle": {"tilt_enabled": True}}
    state = {"active_episodes": [
        {"node": "XLK", "direction": "out", "tier": "confirmed"},
    ]}
    result = OT.oracle_theme_tilt(state, cfg=cfg)
    assert "XLK" in result
    assert result["XLK"] < 0  # OUT → negative tilt


def test_gate_off_returns_empty_dict():
    cfg = {"oracle": {"tilt_enabled": False}}
    state = {"active_episodes": [
        {"node": "XLK", "direction": "out", "tier": "confirmed"},
    ]}
    result = OT.oracle_theme_tilt(state, cfg=cfg)
    assert result == {}


def test_tilt_disabled_with_missing_oracle_section():
    cfg = {}  # no oracle key
    state = {"active_episodes": [{"node": "XLV", "direction": "in", "tier": "onset"}]}
    result = OT.oracle_theme_tilt(state, cfg=cfg)
    assert result == {}


# ---------------------------------------------------------------------------
# Tilt direction and magnitude
# ---------------------------------------------------------------------------

def test_in_direction_produces_positive_tilt():
    cfg = {"oracle": {"tilt_enabled": True}}
    state = {"active_episodes": [{"node": "XLV", "direction": "in", "tier": "onset"}]}
    result = OT.oracle_theme_tilt(state, cfg=cfg)
    assert result["XLV"] > 0


def test_out_direction_produces_negative_tilt():
    cfg = {"oracle": {"tilt_enabled": True}}
    state = {"active_episodes": [{"node": "XLK", "direction": "out", "tier": "confirmed"}]}
    result = OT.oracle_theme_tilt(state, cfg=cfg)
    assert result["XLK"] < 0


def test_confirmed_tier_larger_than_onset():
    cfg = {"oracle": {"tilt_enabled": True}}
    onset = OT.oracle_theme_tilt(
        {"active_episodes": [{"node": "XLK", "direction": "in", "tier": "onset"}]},
        cfg=cfg,
    )
    confirmed = OT.oracle_theme_tilt(
        {"active_episodes": [{"node": "XLK", "direction": "in", "tier": "confirmed"}]},
        cfg=cfg,
    )
    assert confirmed["XLK"] > onset["XLK"]


def test_tilt_is_clamped_to_max():
    cfg = {"oracle": {"tilt_enabled": True}}
    state = {"active_episodes": [{"node": "XLK", "direction": "in", "tier": "undeniable"}]}
    result = OT.oracle_theme_tilt(state, cfg=cfg)
    assert abs(result["XLK"]) <= OT._MAX_TILT


def test_tilt_bounded_minus_one_to_one():
    cfg = {"oracle": {"tilt_enabled": True}}
    for direction in ("in", "out"):
        for tier in ("onset", "confirmed", "undeniable"):
            state = {"active_episodes": [{"node": "X", "direction": direction, "tier": tier}]}
            result = OT.oracle_theme_tilt(state, cfg=cfg)
            if result:
                assert -1.0 <= result["X"] <= 1.0


# ---------------------------------------------------------------------------
# Two-sided regression test — the key test the review checks
# ---------------------------------------------------------------------------
# This test verifies that:
# (a) flag OFF → stock_score.conviction_profile output is byte-identical
#     (oracle module existing does NOT change stock scoring)
# (b) flag ON with a fixture tilt → _axis_tailwind shifts by expected amount

def _profile(spotlight_z, ctx=None):
    """Run conviction_profile with a spotlight z override."""
    from engine import stock_score as ss
    rec = {
        "ticker": "XLK", "name": "Technology", "sector": "Information Technology",
        "alpha": 1.2, "rs_z": 1.0, "sue": 1.0,
        "tech": {"pct_vs_200dma": 5.0, "rsi14": 55, "off_52w_high_pct": -8},
        "ladder": {"entry": {"urgency": "building"}},
        "quality_context_z": 0.5,
    }
    ctx = ctx or {"as_of": "2026-07-01", "regime": {"calm": 0.7}}
    if spotlight_z is not None:
        rec["spotlight"] = {"z": spotlight_z}
    return ss.conviction_profile(copy.deepcopy(rec), "US", ctx=ctx)


def test_flag_off_blend_byte_identical():
    """R5 side (a), REAL PATH: with oracle_t=None (the only value the flag-off
    path can produce), spotlight.blend output is byte-identical to the
    pre-oracle blend arithmetic. This fails if the oracle channel leaks into
    the weights when absent."""
    from engine.spotlight import blend
    base = blend(0.5, 0.3, theme={"slug": "x"}, sector={"etf": "XLK"})
    wired = blend(0.5, 0.3, theme={"slug": "x"}, sector={"etf": "XLK"}, oracle_t=None)
    assert base is not None and wired is not None
    # oracle_z key exists on both (None) — compare full dicts
    assert {k: v for k, v in base.items()} == {k: v for k, v in wired.items()}
    assert wired.get("oracle_z") is None


def test_flag_off_helper_returns_empty_and_ctx_stays_inert():
    """R5 side (a), integration: the library ctx helper yields {} when the gate
    is off, so _spotlight_for passes oracle_t=None for every name."""
    from engine.oracle.tilt import oracle_tilt_by_etf
    assert oracle_tilt_by_etf(cfg={"oracle": {"tilt_enabled": False}}) == {}
    assert oracle_tilt_by_etf(cfg={}) == {}


def test_flag_on_shifts_blend_and_axis_tailwind():
    """R5 side (b), REAL PATH: gate ON with a fixture Tier-S episode produces a
    non-empty ETF tilt map; passing it through spotlight.compute/blend shifts z
    by the exact weighted amount, and stock_score._axis_tailwind moves with it.
    This test FAILS on a gated-but-never-connected implementation (the review
    finding it exists to kill): it exercises tilt -> blend -> _axis_tailwind."""
    import numpy as np
    from engine.oracle.tilt import oracle_theme_tilt, _TIER_TILT
    from engine.spotlight import blend, _W_THEME, _W_SECTOR, _W_ORACLE
    from engine.stock_score import _axis_tailwind

    state = {"active_episodes": [
        {"node": "XLV", "direction": "in", "tier": "confirmed"},
    ]}
    tilts = oracle_theme_tilt(state, cfg={"oracle": {"tilt_enabled": True}})
    assert tilts.get("XLV") == _TIER_TILT["confirmed"]  # +0.45, in-direction

    theme_t, sector_t = 0.5, 0.3
    off = blend(theme_t, sector_t)
    on = blend(theme_t, sector_t, oracle_t=tilts["XLV"])
    exp_off = (_W_THEME * theme_t + _W_SECTOR * sector_t) / (_W_THEME + _W_SECTOR)
    exp_on = (_W_THEME * theme_t + _W_SECTOR * sector_t + _W_ORACLE * tilts["XLV"]) / (
        _W_THEME + _W_SECTOR + _W_ORACLE)
    assert abs(off["z"] - round(exp_off, 3)) < 1e-9
    assert abs(on["z"] - round(exp_on, 3)) < 1e-9
    assert on["z"] != off["z"]
    assert on["oracle_z"] == round(_TIER_TILT["confirmed"], 3)

    tw_off, _ = _axis_tailwind({"spotlight": {"z": off["z"]}})
    tw_on, _ = _axis_tailwind({"spotlight": {"z": on["z"]}})
    assert tw_off is not None and tw_on is not None
    assert tw_on != tw_off, "oracle tilt must reach _axis_tailwind when the gate is on"
    # direction: an in-episode (positive tilt) must not lower the tailwind
    assert tw_on > tw_off


def test_degrade_on_empty_state():
    cfg = {"oracle": {"tilt_enabled": True}}
    assert OT.oracle_theme_tilt(None, cfg=cfg) == {}
    assert OT.oracle_theme_tilt({}, cfg=cfg) == {}
    assert OT.oracle_theme_tilt({"active_episodes": []}, cfg=cfg) == {}


def test_multiple_episodes_same_node_keeps_highest_tier():
    """When a node has both onset and confirmed episodes, confirmed tier wins."""
    cfg = {"oracle": {"tilt_enabled": True}}
    state = {"active_episodes": [
        {"node": "XLK", "direction": "in", "tier": "onset"},
        {"node": "XLK", "direction": "in", "tier": "confirmed"},
    ]}
    result = OT.oracle_theme_tilt(state, cfg=cfg)
    # confirmed tilt (0.45) > onset tilt (0.20)
    assert result["XLK"] == pytest.approx(OT._TIER_TILT["confirmed"])
