"""tests/test_intraday_flow_stance.py — Unit tests for dealer_context() and stance()
(IFT v2 upgrade, ruling §3 + §4).

Covers:
 - dealer_context: None in → None out; full summary → all 31 keys; NaN/inf → None.
 - stance: one test per lane (6 lanes); off-hours skeleton (both branches);
   into_ceiling ⇒ take_profits not act; trap-prone (L7=False) with rvol ⇒ watch.

All tests are self-contained; no network, no disk I/O.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.intraday_flow import (
    ConfluenceLegs,
    dealer_context,
    stance,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _full_summary() -> dict:
    """Minimal but complete gex summary dict covering every dealer_context field."""
    return {
        "regime": "long",
        "net_gex_bn": 1.5,
        "gamma_flip": 450.0,
        "dist_to_flip_pct": 2.3,
        "magnet_up": 455.0,
        "magnet_down": 445.0,
        "call_wall": 460.0,
        "put_wall": 440.0,
        "call_wall_band": "strong",
        "call_wall_hard": True,
        "call_wall_dist_sigma": 0.8,
        "put_wall_band": "moderate",
        "max_pain": 450.0,
        "iv30": 0.22,
        "top_oi_share": 0.35,
        "tier": "A",
        "regime_passport": {"structurally_constant": True},
        "skew": {"rr25": -0.04, "tone": "fear"},
        "iv_rank": {"rank_pct": 65.0, "band": "elevated", "low_confidence": False},
        "expected_move": {"daily_pct": 1.2, "weekly_pct": 2.8},
        "vol_hole": {
            "state": "active",
            "bias": "bullish",
            "upper": 456.0,
            "lower": 444.0,
            "compression": 0.6,
            "pos": "mid",
        },
        "tilt": {"read": "call-dominant"},
        "opex_days": 8,
    }


def _legs(**kwargs) -> ConfluenceLegs:
    """Build a ConfluenceLegs with all legs None, then override with kwargs."""
    defaults = {
        "L1_washout_recent": None,
        "L2_reclaim": None,
        "L3_rvol_elevated": None,
        "L4_vol_durable": None,
        "L5_flow_bid": None,
        "L6_upturn_organ": None,
        "L7_leader_quality": None,
    }
    defaults.update(kwargs)
    return ConfluenceLegs(**defaults)


def _full_buy_legs() -> ConfluenceLegs:
    """All legs set for a full Buy-now setup (L1∧L2∧L4∧L7∧L3)."""
    return _legs(
        L1_washout_recent=True,
        L2_reclaim=True,
        L3_rvol_elevated=True,
        L4_vol_durable=True,
        L5_flow_bid=None,
        L6_upturn_organ=True,
        L7_leader_quality=True,
    )


# ── dealer_context ────────────────────────────────────────────────────────────

class TestDealerContextNone:
    def test_none_in_none_out(self):
        assert dealer_context(None) is None


class TestDealerContextFull:
    """Full summary dict → all 31 dealer keys present with expected values."""

    _EXPECTED_KEYS = {
        "regime", "structurally_constant", "net_gex_bn", "gamma_flip",
        "dist_to_flip_pct", "call_wall", "put_wall", "call_wall_band",
        "call_wall_hard", "call_wall_dist_sigma", "put_wall_band",
        "magnet_up", "magnet_down", "max_pain",
        "expected_move_daily_pct", "expected_move_weekly_pct",
        "vol_hole_state", "vol_hole_bias", "vol_hole_upper", "vol_hole_lower",
        "vol_hole_compression",
        "skew_tone", "skew_rr25",
        "iv30", "iv_rank_band", "iv_rank_pct", "iv_rank_low_confidence",
        "opex_days", "tier", "top_oi_share", "tilt_read",
    }

    def setup_method(self):
        self.result = dealer_context(_full_summary())

    def test_returns_dict(self):
        assert isinstance(self.result, dict)

    def test_all_31_keys_present(self):
        assert self._EXPECTED_KEYS == set(self.result.keys()), (
            f"missing: {self._EXPECTED_KEYS - set(self.result.keys())}, "
            f"extra: {set(self.result.keys()) - self._EXPECTED_KEYS}"
        )

    def test_regime_value(self):
        assert self.result["regime"] == "long"

    def test_structurally_constant(self):
        assert self.result["structurally_constant"] is True

    def test_expected_move_daily(self):
        assert self.result["expected_move_daily_pct"] == 1.2

    def test_expected_move_weekly(self):
        assert self.result["expected_move_weekly_pct"] == 2.8

    def test_vol_hole_state(self):
        assert self.result["vol_hole_state"] == "active"

    def test_skew_tone(self):
        assert self.result["skew_tone"] == "fear"

    def test_skew_rr25(self):
        assert self.result["skew_rr25"] == -0.04

    def test_iv_rank_band(self):
        assert self.result["iv_rank_band"] == "elevated"

    def test_iv_rank_pct(self):
        assert self.result["iv_rank_pct"] == 65.0

    def test_iv_rank_low_confidence(self):
        assert self.result["iv_rank_low_confidence"] is False

    def test_tilt_read(self):
        assert self.result["tilt_read"] == "call-dominant"

    def test_opex_days(self):
        assert self.result["opex_days"] == 8

    def test_tier(self):
        assert self.result["tier"] == "A"

    def test_call_wall_hard(self):
        assert self.result["call_wall_hard"] is True

    def test_call_wall_dist_sigma(self):
        assert self.result["call_wall_dist_sigma"] == 0.8


class TestDealerContextNanInf:
    """NaN and inf values must be mapped to None."""

    def test_nan_mapped_to_none(self):
        d = _full_summary()
        d["net_gex_bn"] = float("nan")
        result = dealer_context(d)
        assert result["net_gex_bn"] is None

    def test_inf_mapped_to_none(self):
        d = _full_summary()
        d["dist_to_flip_pct"] = float("inf")
        result = dealer_context(d)
        assert result["dist_to_flip_pct"] is None

    def test_negative_inf_mapped_to_none(self):
        d = _full_summary()
        d["iv30"] = float("-inf")
        result = dealer_context(d)
        assert result["iv30"] is None


class TestDealerContextMissingSubfields:
    """Any missing sub-field should be None, never raise."""

    def test_missing_expected_move(self):
        d = _full_summary()
        del d["expected_move"]
        result = dealer_context(d)
        assert result is not None
        assert result["expected_move_daily_pct"] is None
        assert result["expected_move_weekly_pct"] is None

    def test_missing_vol_hole(self):
        d = _full_summary()
        del d["vol_hole"]
        result = dealer_context(d)
        assert result is not None
        assert result["vol_hole_state"] is None

    def test_missing_regime_passport(self):
        d = _full_summary()
        del d["regime_passport"]
        result = dealer_context(d)
        assert result is not None
        assert result["structurally_constant"] is None

    def test_empty_dict(self):
        result = dealer_context({})
        assert result is not None
        # All values should be None for an empty dict
        assert all(v is None for v in result.values())


# ── stance ────────────────────────────────────────────────────────────────────

class TestStanceTakeProfits:
    """Rule 1: price above VWAP + extended_up ⇒ take_profits."""

    def test_extended_up_via_vwap_delta(self):
        """vwap_delta_pct >= 1.5 × expected_move_daily_pct triggers take_profits."""
        d = _full_summary()
        d["expected_move"]["daily_pct"] = 1.0  # set nested daily_pct to 1.0
        dealer = dealer_context(d)
        legs = _full_buy_legs()
        # vwap_delta = 1.5 × 1.0 = exactly at threshold → trigger
        result = stance(
            legs=legs, K=legs.K,
            vwap_delta_pct=1.5,
            dealer=dealer,
        )
        assert result["key"] == "take_profits"
        assert result["lane"] == "take_profits"
        assert "take profits" in result["en"].lower()
        assert result["zh"]  # non-empty ZH

    def test_pin_watch_triggers_take_profits(self):
        """opex_days <= 5, regime=long, call_wall_dist_sigma <= 0.01 ⇒ pin_watch ⇒ take_profits."""
        d = _full_summary()
        d["opex_days"] = 3
        d["regime"] = "long"
        d["call_wall_dist_sigma"] = 0.005  # within ~1% pin zone
        dealer = dealer_context(d)
        legs = _full_buy_legs()
        result = stance(
            legs=legs, K=legs.K,
            vwap_delta_pct=0.3,  # price above VWAP
            dealer=dealer,
        )
        assert result["key"] == "take_profits"

    def test_take_profits_not_triggered_below_vwap(self):
        """extended_up present but price below VWAP → should NOT be take_profits."""
        d = _full_summary()
        d["expected_move_daily_pct"] = 0.5
        dealer = dealer_context(d)
        legs = _legs(
            L1_washout_recent=True,
            L2_reclaim=False,   # below VWAP
            L3_rvol_elevated=True,
            L4_vol_durable=True,
            L7_leader_quality=True,
        )
        result = stance(
            legs=legs, K=legs.K,
            vwap_delta_pct=-0.5,  # below VWAP
            dealer=dealer,
        )
        assert result["key"] != "take_profits"


class TestStanceAct:
    """Rule 2: L1∧L2∧L4∧L7∧(L3∨L5) ∧ NOT into_ceiling ⇒ act."""

    def test_full_setup_no_ceiling(self):
        """Full setup, call_wall_dist_sigma > 0.5 ⇒ act."""
        d = _full_summary()
        d["call_wall_hard"] = True
        d["call_wall_dist_sigma"] = 1.2  # not into ceiling
        dealer = dealer_context(d)
        legs = _full_buy_legs()
        result = stance(
            legs=legs, K=legs.K,
            vwap_delta_pct=0.3,  # above VWAP but not stretched
            dealer=dealer,
        )
        assert result["key"] == "act"
        assert result["lane"] == "act"
        assert "buy now" in result["en"].lower()

    def test_l5_substitutes_for_l3(self):
        """L1∧L2∧L4∧L7∧L5 (no L3) ⇒ act."""
        d = _full_summary()
        d["call_wall_dist_sigma"] = 2.0  # no ceiling
        dealer = dealer_context(d)
        legs = _legs(
            L1_washout_recent=True,
            L2_reclaim=True,
            L3_rvol_elevated=False,
            L4_vol_durable=True,
            L5_flow_bid=True,
            L7_leader_quality=True,
        )
        result = stance(
            legs=legs, K=legs.K,
            vwap_delta_pct=0.3,
            dealer=dealer,
        )
        assert result["key"] == "act"

    def test_missing_l4_no_act(self):
        """Without L4 (vol_durable), act must NOT fire."""
        d = _full_summary()
        d["call_wall_dist_sigma"] = 2.0
        dealer = dealer_context(d)
        legs = _legs(
            L1_washout_recent=True,
            L2_reclaim=True,
            L3_rvol_elevated=True,
            L4_vol_durable=False,   # not durable
            L7_leader_quality=True,
        )
        result = stance(legs=legs, K=legs.K, vwap_delta_pct=0.3, dealer=dealer)
        assert result["key"] != "act"


class TestStanceGetReady:
    """Rule 3: L1∧(L6∨squeeze)∧L7∧NOT L2 ⇒ get_ready."""

    def test_l1_l6_l7_no_reclaim(self):
        """Washout + upturn organ + quality, but no L2 reclaim ⇒ get_ready."""
        legs = _legs(
            L1_washout_recent=True,
            L2_reclaim=False,
            L6_upturn_organ=True,
            L7_leader_quality=True,
        )
        result = stance(legs=legs, K=legs.K)
        assert result["key"] == "get_ready"
        assert result["lane"] == "get_ready"
        assert "almost ready" in result["en"].lower() or "waiting" in result["en"].lower()

    def test_l1_squeeze_l7_no_reclaim(self):
        """L6=None but squeeze_coiled=True → get_ready (L6 ∨ squeeze)."""
        legs = _legs(
            L1_washout_recent=True,
            L2_reclaim=False,
            L6_upturn_organ=None,
            L7_leader_quality=True,
        )
        result = stance(legs=legs, K=legs.K, squeeze_coiled=True)
        assert result["key"] == "get_ready"

    def test_reclaim_present_no_get_ready(self):
        """L2 present → NOT get_ready (condition requires NOT L2)."""
        legs = _legs(
            L1_washout_recent=True,
            L2_reclaim=True,
            L6_upturn_organ=True,
            L7_leader_quality=True,
        )
        result = stance(legs=legs, K=legs.K)
        assert result["key"] != "get_ready"


class TestStanceInFavour:
    """Rule 4: L2∧L6∧(L3∨L4)∧L7∧NOT L1 ⇒ in_favour."""

    def test_trending_no_washout(self):
        """Running above VWAP + upturn + volume, no L1 washout ⇒ in_favour."""
        legs = _legs(
            L1_washout_recent=False,
            L2_reclaim=True,
            L3_rvol_elevated=True,
            L4_vol_durable=None,
            L6_upturn_organ=True,
            L7_leader_quality=True,
        )
        result = stance(legs=legs, K=legs.K)
        assert result["key"] == "in_favour"
        assert result["lane"] == "in_favour"
        assert "in favour" in result["en"].lower()

    def test_l4_substitutes_for_l3(self):
        """L4 present without L3 → still in_favour."""
        legs = _legs(
            L1_washout_recent=False,
            L2_reclaim=True,
            L3_rvol_elevated=False,
            L4_vol_durable=True,
            L6_upturn_organ=True,
            L7_leader_quality=True,
        )
        result = stance(legs=legs, K=legs.K)
        assert result["key"] == "in_favour"


class TestStanceWatch:
    """Rule 5: (L3∨price_up) ∧ (NOT L1 OR L7==False) ⇒ watch."""

    def test_rvol_no_washout(self):
        """Moving (L3) but no washout base ⇒ watch."""
        legs = _legs(
            L1_washout_recent=False,
            L3_rvol_elevated=True,
            L7_leader_quality=True,
        )
        result = stance(legs=legs, K=legs.K)
        assert result["key"] == "watch"
        assert result["lane"] == "watch"
        assert "watch" in result["en"].lower()

    def test_price_up_trap_prone(self):
        """price_up_on_day + L7=False (trap-prone) ⇒ watch."""
        legs = _legs(
            L1_washout_recent=True,   # washout present, but L7 is False
            L7_leader_quality=False,
        )
        result = stance(
            legs=legs, K=legs.K,
            price_up_on_day=True,
        )
        assert result["key"] == "watch"

    def test_rvol_trap_prone(self):
        """L3 elevated + L7=False (trap-prone) ⇒ watch, not act."""
        legs = _legs(
            L1_washout_recent=True,
            L2_reclaim=True,
            L3_rvol_elevated=True,
            L4_vol_durable=True,
            L7_leader_quality=False,  # trap-prone overrides
        )
        result = stance(legs=legs, K=legs.K, vwap_delta_pct=0.3)
        assert result["key"] == "watch"


class TestStanceStandAside:
    """Rule 6: default when no other rule fires ⇒ stand_aside."""

    def test_all_none_legs(self):
        """No legs set → stand aside."""
        legs = _legs()
        result = stance(legs=legs, K=0)
        assert result["key"] == "stand_aside"
        assert result["lane"] == "stand_aside"
        assert "stand aside" in result["en"].lower()

    def test_all_false_legs(self):
        """All legs False → stand aside."""
        legs = _legs(
            L1_washout_recent=False,
            L2_reclaim=False,
            L3_rvol_elevated=False,
            L4_vol_durable=False,
            L5_flow_bid=False,
            L6_upturn_organ=False,
            L7_leader_quality=False,
        )
        result = stance(legs=legs, K=0)
        assert result["key"] == "stand_aside"

    def test_no_volume_no_setup(self):
        """Washout done but no reclaim, no volume, no squeeze ⇒ stand aside."""
        legs = _legs(
            L1_washout_recent=True,
            L2_reclaim=False,
            L3_rvol_elevated=False,
            L7_leader_quality=True,
            L6_upturn_organ=False,
        )
        result = stance(legs=legs, K=legs.K, squeeze_coiled=False)
        assert result["key"] == "stand_aside"


class TestStanceOffHours:
    """Off-hours skeleton (live_present=False)."""

    def test_l1_l6_get_ready_offhours(self):
        """L1 + L6 ⇒ get_ready off-hours with 'Base in place' copy."""
        legs = _legs(L1_washout_recent=True, L6_upturn_organ=True)
        result = stance(legs=legs, K=legs.K, live_present=False)
        assert result["key"] == "get_ready"
        assert "base in place" in result["en"].lower()
        assert "底部已形成" in result["zh"]

    def test_l1_squeeze_get_ready_offhours(self):
        """L1 + squeeze_coiled ⇒ get_ready off-hours."""
        legs = _legs(L1_washout_recent=True, L6_upturn_organ=False)
        result = stance(
            legs=legs, K=legs.K,
            squeeze_coiled=True,
            live_present=False,
        )
        assert result["key"] == "get_ready"

    def test_no_l1_stand_aside_offhours(self):
        """No L1 ⇒ stand aside off-hours regardless of L6."""
        legs = _legs(L1_washout_recent=False, L6_upturn_organ=True)
        result = stance(legs=legs, K=legs.K, live_present=False)
        assert result["key"] == "stand_aside"

    def test_all_none_stand_aside_offhours(self):
        """No legs → stand aside off-hours."""
        legs = _legs()
        result = stance(legs=legs, K=0, live_present=False)
        assert result["key"] == "stand_aside"


class TestStanceIntoCeiling:
    """into_ceiling blocks act, forcing watch or stand_aside."""

    def test_full_setup_into_ceiling_no_act(self):
        """Full L1∧L2∧L3∧L4∧L7 setup BUT into_ceiling ⇒ NOT act."""
        d = _full_summary()
        d["call_wall_hard"] = True
        d["call_wall_dist_sigma"] = 0.3  # <= 0.5 → into_ceiling = True
        d["expected_move_daily_pct"] = 5.0  # large, so extended_up won't trigger
        dealer = dealer_context(d)
        legs = _legs(
            L1_washout_recent=True,
            L2_reclaim=True,
            L3_rvol_elevated=True,
            L4_vol_durable=True,
            L7_leader_quality=True,
        )
        result = stance(
            legs=legs, K=legs.K,
            vwap_delta_pct=0.3,  # above VWAP but not stretched
            dealer=dealer,
        )
        assert result["key"] != "act", (
            f"Expected not 'act' but got '{result['key']}' "
            "(into_ceiling must block act rule)"
        )

    def test_ceiling_far_away_allows_act(self):
        """call_wall_dist_sigma = 2.0 (far) → into_ceiling = False → act allowed."""
        d = _full_summary()
        d["call_wall_hard"] = True
        d["call_wall_dist_sigma"] = 2.0
        d["expected_move_daily_pct"] = 5.0
        dealer = dealer_context(d)
        legs = _full_buy_legs()
        result = stance(
            legs=legs, K=legs.K,
            vwap_delta_pct=0.3,
            dealer=dealer,
        )
        assert result["key"] == "act"


class TestStanceOutputShape:
    """Every stance result has exactly the four required keys."""

    _REQUIRED_KEYS = {"key", "en", "zh", "lane"}

    @pytest.mark.parametrize("legs_kw,extra", [
        # stand_aside
        ({}, {}),
        # get_ready
        ({"L1_washout_recent": True, "L2_reclaim": False,
          "L6_upturn_organ": True, "L7_leader_quality": True}, {}),
        # in_favour
        ({"L1_washout_recent": False, "L2_reclaim": True,
          "L3_rvol_elevated": True, "L6_upturn_organ": True,
          "L7_leader_quality": True}, {}),
        # watch
        ({"L1_washout_recent": False, "L3_rvol_elevated": True,
          "L7_leader_quality": True}, {}),
    ])
    def test_output_has_required_keys(self, legs_kw, extra):
        result = stance(legs=_legs(**legs_kw), K=0, **extra)
        assert self._REQUIRED_KEYS == set(result.keys()), (
            f"Unexpected keys: {set(result.keys()) - self._REQUIRED_KEYS}"
        )

    def test_key_equals_lane(self):
        """key and lane must always be the same string."""
        legs = _legs()
        result = stance(legs=legs, K=0)
        assert result["key"] == result["lane"]

    def test_en_zh_non_empty(self):
        """EN and ZH copy must always be non-empty strings."""
        for k in ("L1_washout_recent", "L2_reclaim", "L3_rvol_elevated"):
            legs = _legs(**{k: True})
            result = stance(legs=legs, K=legs.K)
            assert isinstance(result["en"], str) and len(result["en"]) > 0
            assert isinstance(result["zh"], str) and len(result["zh"]) > 0


class TestStanceNoDealerFields:
    """dealer=None — helpers default to False; no raises."""

    def test_full_buy_no_dealer(self):
        """Full buy setup with dealer=None ⇒ act (no ceiling to block)."""
        legs = _full_buy_legs()
        result = stance(legs=legs, K=legs.K, vwap_delta_pct=0.3, dealer=None)
        # into_ceiling=False (no dealer), extended_up=False (no dealer) → act
        assert result["key"] == "act"

    def test_stand_aside_no_dealer(self):
        legs = _legs()
        result = stance(legs=legs, K=0, dealer=None)
        assert result["key"] == "stand_aside"


class TestStanceQualityNegativeFilter:
    """L7 gates the good lanes as a NEGATIVE filter: only a KNOWN trap
    (L7 is False) blocks act/get_ready/in_favour; unknown quality (None) passes.
    Regression: trap flags are sparse (mostly None) — `is True` gating made
    "Buy now" unreachable for nearly every real leader (ruling §3)."""

    def _full_buy_with_quality(self, q):
        return _legs(
            L1_washout_recent=True, L2_reclaim=True, L3_rvol_elevated=True,
            L4_vol_durable=True, L6_upturn_organ=True, L7_leader_quality=q,
        )

    def test_unknown_quality_reaches_act(self):
        legs = self._full_buy_with_quality(None)
        r = stance(legs=legs, K=legs.K, vwap_delta_pct=0.3, dealer=None)
        assert r["key"] == "act"

    def test_confirmed_quality_reaches_act(self):
        legs = self._full_buy_with_quality(True)
        r = stance(legs=legs, K=legs.K, vwap_delta_pct=0.3, dealer=None)
        assert r["key"] == "act"

    def test_known_trap_blocks_act_to_watch(self):
        legs = self._full_buy_with_quality(False)
        r = stance(legs=legs, K=legs.K, vwap_delta_pct=0.3, dealer=None)
        assert r["key"] == "watch"
