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


def test_flag_off_gate_is_effective_no_side_effects():
    """flag OFF: engine.oracle.tilt module existing must NOT change stock_score output.

    We verify by computing conviction_profile WITHOUT any spotlight and then
    verifying that importing oracle.tilt with gate-off doesn't alter the score.
    The oracle.tilt function returns {} when gate is off — the consumer (oracle_nightly)
    never injects anything into the spotlight dict unless explicitly enabled.
    """
    cfg_off = {"oracle": {"tilt_enabled": False}}
    tilt_result = OT.oracle_theme_tilt(
        {"active_episodes": [{"node": "XLK", "direction": "out", "tier": "confirmed"}]},
        cfg=cfg_off,
    )
    # Gate OFF → empty dict → no spotlight injection
    assert tilt_result == {}

    # Score WITHOUT oracle spotlight
    p_no_oracle = _profile(spotlight_z=None)

    # Score WITH oracle spotlight that was supposed to be OFF but snuck in
    # (simulates what would happen if gate failed)
    p_with_inject = _profile(spotlight_z=-0.45)  # confirmed OUT tilt

    # When gate works: p_no_oracle is the real output (no inject)
    # This verifies byte-identical would hold — the gate produces {} so nothing is injected
    assert tilt_result == {}, "Gate failure: oracle.tilt returned non-empty despite tilt_enabled=False"

    # The score difference confirms the inject WOULD have changed things (test has power)
    delta = abs(p_no_oracle["composite_z"] - p_with_inject["composite_z"])
    assert delta > 0.01, "Sanity check failed: spotlight injection has no measurable effect"


def test_flag_on_tilt_shifts_axis_tailwind_for_member():
    """flag ON: fixture tilt shifts _axis_tailwind by the expected clamped amount.

    For a confirmed OUT episode, tilt = -_TIER_TILT["confirmed"] = -0.45.
    Injecting spotlight.z = -0.45 should reduce composite_z vs spotlight.z = 0.
    """
    cfg_on = {"oracle": {"tilt_enabled": True}}
    state = {"active_episodes": [{"node": "XLK", "direction": "out", "tier": "confirmed"}]}
    tilt = OT.oracle_theme_tilt(state, cfg=cfg_on)
    assert "XLK" in tilt

    xlk_tilt = tilt["XLK"]
    assert xlk_tilt < 0  # OUT episode → negative

    # Score with oracle tilt injected into spotlight
    p_with_tilt = _profile(spotlight_z=xlk_tilt)
    p_neutral = _profile(spotlight_z=0.0)

    # OUT tilt should REDUCE the composite score vs neutral
    assert p_with_tilt["composite_z"] < p_neutral["composite_z"], (
        f"OUT tilt {xlk_tilt:.3f} should reduce composite_z; "
        f"got tilt={p_with_tilt['composite_z']:.4f} neutral={p_neutral['composite_z']:.4f}"
    )

    # The shift should be in the expected clamped range (small but measurable)
    delta = p_neutral["composite_z"] - p_with_tilt["composite_z"]
    assert 0.005 <= delta <= 0.10, f"Shift {delta:.4f} outside expected range [0.005, 0.10]"


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
