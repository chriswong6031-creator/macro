"""Tests for the CONFIRMING TURN evidence-witness bypass in engine/cycles.py (HKRV-W1).

Covers:
(a) confirm=None byte-identity — ladder_state with confirm=None produces the same
    output as the call without confirm (US/CN/basket callers unaffected).
(b) Synthetic V-recovery + all three witnesses → CONFIRMING TURN state.
(c) Same V-recovery but hard_fail=True → stays COUNTERTREND BOUNCE (hard_fail wins).
(d) Flat name (no oversold episode) → rsi_reclaim witness False → unchanged state.
(e) cycle_ontology.resolve_state does not raise for CONFIRMING TURN across all phases.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _REPO)

from engine.cycles import ladder_state, LADDER, LADDER_SCORE, STATE_DISPLAY


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_bearish_regime_mtf() -> dict:
    """An MTF dict where the weekly is firmly bearish WITHOUT a fresh cross-down.

    Regime score accounting (engine.cycles.regime_state):
      W: not macd_pos, not cross_up/dn, not approaching_up → s -= 1.0 (weekly neg)
      3D: not positive, not cross → s -= 0.5
      ic_phase from the cyc fixture is "overdue" → s -= 1.5 (set in _make_cyc_fresh_buy)
      ic_failed=False (no extra -2.0)
      Total: -3.0 → "bear" (s <= -1.5)  ✓

    Extension gate does NOT fire because:
      htf_rollover = W.macd_cross_dn OR 3D.macd_cross_dn = False OR False = False
      daily_rollover = D.macd_cross_dn OR D.macd_curl_dn OR D.macd_approaching_dn = False
      rollover_veto = False (and rsi14=48, not >70, so overbought_late=False)  ✓
    """
    return {
        "D": {
            "macd_cross_up": True,
            "macd_pos": True,
            "macd_curl_dn": False,
            "macd_cross_dn": False,
            "macd_approaching_dn": False,
            "rsi14": 48.0,
            "rsi5": 52.0,
            "stoch": 40.0,
        },
        "W": {
            "macd_pos": False,         # not positive: -1.0 to regime score
            "macd_cross_up": False,
            "macd_cross_dn": False,    # no htf_rollover trigger
            "macd_curl_dn": False,
            "macd_approaching_up": False,
            "rsi14": 38.0,
        },
        "3D": {
            "macd_pos": False,         # not positive: -0.5 to regime score
            "macd_cross_up": False,
            "macd_cross_dn": False,    # no htf_rollover trigger
            "rsi14": 45.0,
        },
    }


def _make_cyc_fresh_buy(*, failed_cycle: bool = False, ic_failed: bool = False) -> dict:
    """A cycle state consistent with a fresh buy setup, optionally with failures.

    ic_phase="overdue" contributes -1.5 to the regime score, pushing the total to
    "bear" when combined with the bearish MTF fixture (-1.0 W, -0.5 3D, -1.5 overdue).
    """
    return {
        "dc_day": 3,
        "dc_phase": "new",
        "dc_band": (18, 40),
        "dc_early": 8,
        "above_ma10": True,
        "ma10_rising": True,
        "swing_low": True,
        "failed_cycle": failed_cycle,
        "ic_failed": ic_failed,
        "ic_phase": "overdue",   # -1.5 in regime_state → total -3.0 → "bear"
        "ic_week": 2,
        "dcl_price": 95.0,
        "cand_price": 95.0,
        "cand_age": 3,
        "cand_dcl": "2024-01-15",
        "cand_swing": True,
        "translation": None,
    }


def _make_early() -> dict:
    return {"dir": None, "signals": [], "tier": None}


# ─────────────────────────────────────────────────────────────────────────────
# Test (a): confirm=None byte-identity
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_none_byte_identity():
    """ladder_state(confirm=None) must be identical to the call without confirm.

    We use a non-HK-path fixture (bear regime, no hard_fail) and verify that
    omitting vs explicitly passing confirm=None gives byte-equal state + score.
    """
    mtf = _make_bearish_regime_mtf()
    cyc = _make_cyc_fresh_buy(failed_cycle=False, ic_failed=False)
    early = _make_early()

    result_default = ladder_state(cyc, mtf, early)
    result_none = ladder_state(cyc, mtf, early, confirm=None)

    assert result_default.get("state") == result_none.get("state"), (
        "state differs between confirm omitted and confirm=None"
    )
    assert result_default.get("score") == result_none.get("score"), (
        "score differs between confirm omitted and confirm=None"
    )
    # The COUNTERTREND BOUNCE path fires here (bear regime, no hard_fail, bullish tactical)
    assert result_default.get("state") == "COUNTERTREND BOUNCE", (
        f"expected COUNTERTREND BOUNCE for bear regime, got {result_default.get('state')}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test (b): all three witnesses True → CONFIRMING TURN
# ─────────────────────────────────────────────────────────────────────────────

def test_v_recovery_all_witnesses_confirming_turn():
    """Bear regime + bullish daily + all three witnesses → CONFIRMING TURN."""
    mtf = _make_bearish_regime_mtf()
    cyc = _make_cyc_fresh_buy(failed_cycle=False, ic_failed=False)
    early = _make_early()

    confirm = {
        "sb_persist": True,
        "rsi_reclaim": True,
        "above_rising_ma10": True,
    }

    result = ladder_state(cyc, mtf, early, confirm=confirm)
    assert result.get("state") == "CONFIRMING TURN", (
        f"expected CONFIRMING TURN, got {result.get('state')!r}"
    )
    # dir must be "caution" not "up" (copy law)
    assert STATE_DISPLAY["CONFIRMING TURN"]["dir"] == "caution"
    # action must not contain predictive language (no "buy" as a command)
    action = STATE_DISPLAY["CONFIRMING TURN"]["action"]
    assert "WATCH" in action or "watch" in action.lower(), (
        f"CONFIRMING TURN action should contain WATCH, got {action!r}"
    )
    # score pins: -15, strictly above COUNTERTREND BOUNCE (-25), and negative
    assert LADDER_SCORE["CONFIRMING TURN"] == -15, (
        f"CONFIRMING TURN score must be -15, got {LADDER_SCORE['CONFIRMING TURN']}"
    )
    assert LADDER_SCORE["CONFIRMING TURN"] > LADDER_SCORE["COUNTERTREND BOUNCE"], (
        "CONFIRMING TURN must be softer (less negative) than COUNTERTREND BOUNCE"
    )
    assert LADDER_SCORE["CONFIRMING TURN"] < 0, (
        "CONFIRMING TURN must remain caution-tier (strictly negative)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test (c): hard_fail wins over evidence_ok
# ─────────────────────────────────────────────────────────────────────────────

def test_hard_fail_wins_over_witnesses():
    """hard_fail (failed_cycle AND ic_failed) must override evidence_ok → COUNTERTREND BOUNCE."""
    mtf = _make_bearish_regime_mtf()
    # Both failed_cycle AND ic_failed = hard_fail condition
    cyc = _make_cyc_fresh_buy(failed_cycle=True, ic_failed=True)
    early = _make_early()

    confirm = {
        "sb_persist": True,
        "rsi_reclaim": True,
        "above_rising_ma10": True,
    }

    result = ladder_state(cyc, mtf, early, confirm=confirm)
    assert result.get("state") == "COUNTERTREND BOUNCE", (
        f"hard_fail should keep COUNTERTREND BOUNCE, got {result.get('state')!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test (d): flat name / no oversold episode → witnesses False → unchanged
# ─────────────────────────────────────────────────────────────────────────────

def test_flat_no_witnesses_unchanged():
    """When witnesses are False (e.g. no oversold episode), state stays COUNTERTREND BOUNCE."""
    mtf = _make_bearish_regime_mtf()
    cyc = _make_cyc_fresh_buy(failed_cycle=False, ic_failed=False)
    early = _make_early()

    # Partial witnesses — rsi_reclaim is False (no oversold episode)
    confirm_partial = {
        "sb_persist": True,
        "rsi_reclaim": False,   # no oversold episode
        "above_rising_ma10": True,
    }

    result = ladder_state(cyc, mtf, early, confirm=confirm_partial)
    assert result.get("state") == "COUNTERTREND BOUNCE", (
        f"partial witnesses should not upgrade, got {result.get('state')!r}"
    )

    # Also test all False
    confirm_none = {
        "sb_persist": False,
        "rsi_reclaim": False,
        "above_rising_ma10": False,
    }
    result2 = ladder_state(cyc, mtf, early, confirm=confirm_none)
    assert result2.get("state") == "COUNTERTREND BOUNCE", (
        f"all-False witnesses should not upgrade, got {result2.get('state')!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test (e): cycle_ontology.resolve_state does not raise for CONFIRMING TURN
# ─────────────────────────────────────────────────────────────────────────────

def test_ontology_crosswalk_resolves_confirming_turn():
    """resolve_state must not raise ValueError for any phase × CONFIRMING TURN."""
    try:
        from engine.cycle_ontology import resolve_state, PHASES
    except ImportError:
        pytest.skip("cycle_ontology not importable in this environment")

    for phase in PHASES:
        result = resolve_state(
            pos=40.0,
            phase=phase,
            phase_dir="up",
            ladder_state="CONFIRMING TURN",
        )
        assert "stance" in result, (
            f"resolve_state({phase!r}, 'CONFIRMING TURN') returned no stance"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Bonus: CONFIRMING TURN in LADDER + STATE_DISPLAY contract checks
# ─────────────────────────────────────────────────────────────────────────────

def test_confirming_turn_in_ladder_and_display():
    """CONFIRMING TURN is in LADDER, LADDER_SCORE, and STATE_DISPLAY with required fields."""
    assert "CONFIRMING TURN" in LADDER, "CONFIRMING TURN must be in LADDER"
    assert "CONFIRMING TURN" in LADDER_SCORE, "CONFIRMING TURN must be in LADDER_SCORE"
    assert "CONFIRMING TURN" in STATE_DISPLAY, "CONFIRMING TURN must be in STATE_DISPLAY"

    d = STATE_DISPLAY["CONFIRMING TURN"]
    assert "label" in d, "STATE_DISPLAY entry must have 'label'"
    assert "label_zh" in d, "STATE_DISPLAY entry must have 'label_zh'"
    assert "action" in d, "STATE_DISPLAY entry must have 'action'"
    assert "action_zh" in d, "STATE_DISPLAY entry must have 'action_zh'"
    assert "dir" in d, "STATE_DISPLAY entry must have 'dir'"
    # dir must be caution (NOT up — copy law)
    assert d["dir"] == "caution", (
        f"CONFIRMING TURN dir must be 'caution', got {d['dir']!r}"
    )
    # English text fields must be non-empty
    assert d["label"], "label must be non-empty"
    assert d["label_zh"], "label_zh must be non-empty"
    assert d["action"], "action must be non-empty"
    assert d["action_zh"], "action_zh must be non-empty"
