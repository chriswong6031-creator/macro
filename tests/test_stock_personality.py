"""Tests for engine/stock_personality.py — W2a spec.

Coverage:
- Per-label cascade tests: every chart/micro/ownership/mode label
  (positive AND negative case per label).
- Precedence tests: two-label inputs → higher-precedence label wins / appears first;
  caps respected.
- Degradation: assess(ticker, as_of=...) bare → all axes None, evidence.missing
  populated, no exception.
- Close-only path_features (gap keys None) → event_gapper unreachable, no exception.
- Authority stanza immutability + exact schema keys.
- setup_compatibility: applies-match, hostile-match, retired/excluded.
- Determinism.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.stock_personality import (  # noqa: E402
    CHART_MAX_LABELS,
    CHART_MIN_BARS,
    CHART_PRECEDENCE,
    CURRENT_MODE_PRECEDENCE,
    MICROSTRUCTURE_PRECEDENCE,
    MODE_MAX_LABELS,
    OWNERSHIP_PRECEDENCE,
    _AUTHORITY,
    _classify_chart,
    _classify_current_mode,
    _classify_microstructure,
    _classify_ownership,
    assess,
    setup_compatibility,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_path_features(
    n_bars: int = 600,
    has_ohlc: bool = True,
    has_volume: bool = True,
    **overrides,
) -> dict:
    """Return a baseline path_features dict with all features present."""
    base = {
        "trend_persist_20": 0.10,
        "trend_persist_60": 0.10,
        "trend_persist_126": 0.10,
        "slope_stability_126": 0.70,
        "pullback_median_252": 0.03,
        "pullback_p90_252": 0.10,
        "breakout_ft_rate_63": 0.45,
        "failed_breakout_rate_63": 0.30,
        "gap_share_252": 0.20,
        "event_gap_contrib_252": 0.15,
        "wick_share_126": 0.35,
        "reversal_half_life": 6.0,
        "extreme_bar_freq_252": 0.01,
        "range_compression_pct": 40.0,
        "dollar_adv_21d": 10_000_000.0,
        "amihud_252": 0.05,
        "cs_spread_252": 0.008,
        "coverage": {
            "n_bars": n_bars,
            "has_ohlc": has_ohlc,
            "has_volume": has_volume,
            "as_of": "2026-01-01",
        },
    }
    base.update(overrides)
    return base


def _make_tech(**overrides) -> dict:
    """Baseline tech block — no special state."""
    base = {
        "hv_pctile": 50.0,
        "rel_volume": 1.0,
        "obv_slope_up": True,
        "off_52w_high_pct": 20.0,
        "ret_21d": 0.03,
        "months_underwater": 0.0,
        "vol_squeeze_state": "QUIET",
        "ladder_state": None,
    }
    base.update(overrides)
    return base


def _make_positioning(**overrides) -> dict:
    base = {
        "short_pct_float": 2.0,
        "days_to_cover": 1.0,
        "insider_net_usd_mn": 0.0,
        "insider_cluster": False,
        "insider_n_buyers": 0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# CHART personality — per-label positive & negative
# ---------------------------------------------------------------------------


class TestChartEventGapper:
    def test_positive_event_gap_contrib(self):
        pf = _make_path_features(event_gap_contrib_252=0.40)
        labels, _, _ = _classify_chart(pf, {})
        assert labels is not None
        assert "event_gapper" in labels

    def test_positive_gap_share(self):
        pf = _make_path_features(gap_share_252=0.50, event_gap_contrib_252=None)
        labels, _, _ = _classify_chart(pf, {})
        assert labels is not None
        assert "event_gapper" in labels

    def test_negative_both_below_threshold(self):
        pf = _make_path_features(
            event_gap_contrib_252=0.10,
            gap_share_252=0.10,
            trend_persist_60=0.10,
            failed_breakout_rate_63=0.30,
        )
        labels, _, _ = _classify_chart(pf, {})
        assert labels is not None
        assert "event_gapper" not in labels

    def test_negative_gap_keys_none_close_only(self):
        """Close-only path_features: gap keys None → event_gapper unreachable."""
        pf = _make_path_features(gap_share_252=None, event_gap_contrib_252=None)
        labels, _, _ = _classify_chart(pf, {})
        assert "event_gapper" not in (labels or [])


class TestChartFailedBreakoutTrap:
    def test_positive(self):
        pf = _make_path_features(
            failed_breakout_rate_63=0.65,
            event_gap_contrib_252=0.05,
            gap_share_252=0.10,
        )
        labels, _, _ = _classify_chart(pf, {})
        assert labels is not None
        assert "failed_breakout_trap" in labels

    def test_negative(self):
        pf = _make_path_features(
            failed_breakout_rate_63=0.40,
            event_gap_contrib_252=0.05,
            gap_share_252=0.10,
        )
        labels, _, _ = _classify_chart(pf, {})
        assert "failed_breakout_trap" not in (labels or [])


class TestChartMeanReversionRubberBand:
    def test_positive(self):
        pf = _make_path_features(
            trend_persist_60=-0.15,
            event_gap_contrib_252=0.05,
            gap_share_252=0.10,
            failed_breakout_rate_63=0.30,
        )
        labels, _, _ = _classify_chart(pf, {})
        assert labels is not None
        assert "mean_reversion_rubber_band" in labels

    def test_negative(self):
        pf = _make_path_features(trend_persist_60=0.05)
        labels, _, _ = _classify_chart(pf, {})
        assert "mean_reversion_rubber_band" not in (labels or [])


class TestChartSmoothCompounderGrind:
    def test_positive(self):
        pf = _make_path_features(
            trend_persist_126=0.10,
            pullback_median_252=0.03,
            extreme_bar_freq_252=0.01,
            event_gap_contrib_252=0.05,
            gap_share_252=0.10,
            failed_breakout_rate_63=0.30,
            trend_persist_60=0.05,
        )
        labels, _, _ = _classify_chart(pf, {})
        assert labels is not None
        assert "smooth_compounder_grind" in labels

    def test_negative_pullback_too_large(self):
        pf = _make_path_features(
            trend_persist_126=0.10,
            pullback_median_252=0.10,  # above threshold
            extreme_bar_freq_252=0.01,
        )
        labels, _, _ = _classify_chart(pf, {})
        assert "smooth_compounder_grind" not in (labels or [])


class TestChartStairStepLeader:
    def test_positive(self):
        pf = _make_path_features(
            breakout_ft_rate_63=0.65,
            slope_stability_126=0.70,
            event_gap_contrib_252=0.05,
            gap_share_252=0.10,
            failed_breakout_rate_63=0.30,
            trend_persist_60=0.05,
            trend_persist_126=0.03,  # below smooth threshold
        )
        labels, _, _ = _classify_chart(pf, {})
        assert labels is not None
        assert "stair_step_leader" in labels

    def test_negative_ft_rate_too_low(self):
        pf = _make_path_features(breakout_ft_rate_63=0.40, slope_stability_126=0.70)
        labels, _, _ = _classify_chart(pf, {})
        assert "stair_step_leader" not in (labels or [])


class TestChartVolatileMomentumVehicle:
    def test_positive(self):
        tech = _make_tech(hv_pctile=85.0, vol_squeeze_state="QUIET")
        pf = _make_path_features(
            trend_persist_20=0.05,
            event_gap_contrib_252=0.05,
            gap_share_252=0.10,
            failed_breakout_rate_63=0.30,
            trend_persist_60=0.05,
            trend_persist_126=0.03,
            breakout_ft_rate_63=0.40,
            slope_stability_126=0.50,
        )
        labels, _, _ = _classify_chart(pf, tech)
        assert labels is not None
        assert "volatile_momentum_vehicle" in labels

    def test_negative_hv_too_low(self):
        tech = _make_tech(hv_pctile=50.0)
        pf = _make_path_features(trend_persist_20=0.05)
        labels, _, _ = _classify_chart(pf, tech)
        assert "volatile_momentum_vehicle" not in (labels or [])


class TestChartBasingAccumulator:
    def test_positive(self):
        tech = _make_tech(vol_squeeze_state="COILED")
        pf = _make_path_features(
            range_compression_pct=15.0,
            event_gap_contrib_252=0.05,
            gap_share_252=0.10,
            failed_breakout_rate_63=0.30,
            trend_persist_60=0.05,
            trend_persist_126=0.03,
            breakout_ft_rate_63=0.40,
            slope_stability_126=0.50,
            trend_persist_20=-0.05,  # below VMV threshold, so VMV won't fire
        )
        labels, _, _ = _classify_chart(pf, tech)
        assert labels is not None
        assert "basing_accumulator" in labels

    def test_positive_compressed(self):
        tech = _make_tech(vol_squeeze_state="COMPRESSED", hv_pctile=50.0)
        pf = _make_path_features(range_compression_pct=10.0)
        labels, _, _ = _classify_chart(pf, tech)
        assert "basing_accumulator" in (labels or [])

    def test_negative_range_too_high(self):
        tech = _make_tech(vol_squeeze_state="COILED")
        pf = _make_path_features(range_compression_pct=50.0)
        labels, _, _ = _classify_chart(pf, tech)
        assert "basing_accumulator" not in (labels or [])


class TestChartDefensiveRangeStock:
    def test_positive(self):
        tech = _make_tech(hv_pctile=25.0)
        pf = _make_path_features(
            trend_persist_126=0.01,
            pullback_p90_252=0.10,
            # ensure nothing higher fires
            event_gap_contrib_252=0.05,
            gap_share_252=0.10,
            failed_breakout_rate_63=0.30,
            trend_persist_60=0.01,
            breakout_ft_rate_63=0.40,
            slope_stability_126=0.50,
            trend_persist_20=-0.05,
            range_compression_pct=50.0,
        )
        labels, _, _ = _classify_chart(pf, tech)
        assert labels is not None
        assert "defensive_range_stock" in labels

    def test_negative_hv_too_high(self):
        tech = _make_tech(hv_pctile=60.0)
        pf = _make_path_features(trend_persist_126=0.01, pullback_p90_252=0.10)
        labels, _, _ = _classify_chart(pf, tech)
        assert "defensive_range_stock" not in (labels or [])


class TestChartMixedFallback:
    def test_mixed_when_nothing_matches(self):
        """Moderate values that don't trigger any label → mixed_chart."""
        pf = _make_path_features(
            event_gap_contrib_252=0.05,
            gap_share_252=0.10,
            failed_breakout_rate_63=0.30,
            trend_persist_60=0.0,
            trend_persist_126=0.03,   # below smooth threshold
            pullback_median_252=0.04,
            extreme_bar_freq_252=0.03,  # above smooth threshold, so smooth won't fire
            breakout_ft_rate_63=0.40,
            slope_stability_126=0.50,
            trend_persist_20=0.0,
            range_compression_pct=50.0,
        )
        tech = _make_tech(hv_pctile=50.0, vol_squeeze_state="QUIET")
        labels, _, _ = _classify_chart(pf, tech)
        assert labels == ["mixed_chart"]


class TestChartNoneOnInsufficientBars:
    def test_none_below_min_bars(self):
        pf = _make_path_features(n_bars=100)
        labels, missing, _ = _classify_chart(pf, {})
        assert labels is None
        assert any("n_bars" in m for m in missing)

    def test_none_when_no_path_features(self):
        labels, missing, _ = _classify_chart(None, None)
        assert labels is None
        assert missing  # something in missing list


# ---------------------------------------------------------------------------
# MICROSTRUCTURE — per-label
# ---------------------------------------------------------------------------


class TestMicroTightSpreadAbsorber:
    def test_positive(self):
        pf = _make_path_features(
            dollar_adv_21d=100_000_000.0,
            cs_spread_252=0.003,
            amihud_252=0.05,
        )
        labels, _, _ = _classify_microstructure(pf)
        assert labels is not None
        assert "tight_spread_absorber" in labels

    def test_negative_adv_too_low(self):
        pf = _make_path_features(
            dollar_adv_21d=10_000_000.0,  # below $50M threshold
            cs_spread_252=0.003,
            amihud_252=0.05,
        )
        labels, _, _ = _classify_microstructure(pf)
        assert "tight_spread_absorber" not in (labels or [])

    def test_negative_spread_too_high(self):
        pf = _make_path_features(
            dollar_adv_21d=100_000_000.0,
            cs_spread_252=0.010,  # above threshold
            amihud_252=0.05,
        )
        labels, _, _ = _classify_microstructure(pf)
        assert "tight_spread_absorber" not in (labels or [])


class TestMicroWideSpreadImpact:
    def test_positive_low_adv(self):
        pf = _make_path_features(
            dollar_adv_21d=2_000_000.0,
            cs_spread_252=0.008,
            amihud_252=0.5,
            reversal_half_life=10.0,
        )
        labels, _, _ = _classify_microstructure(pf)
        assert labels is not None
        assert "wide_spread_impact" in labels

    def test_positive_high_spread(self):
        pf = _make_path_features(
            dollar_adv_21d=20_000_000.0,
            cs_spread_252=0.020,
            amihud_252=0.5,
            reversal_half_life=10.0,
        )
        labels, _, _ = _classify_microstructure(pf)
        assert "wide_spread_impact" in (labels or [])

    def test_negative(self):
        pf = _make_path_features(
            dollar_adv_21d=20_000_000.0,
            cs_spread_252=0.008,
            amihud_252=0.05,
        )
        labels, _, _ = _classify_microstructure(pf)
        assert "wide_spread_impact" not in (labels or [])


class TestMicroGapDiscontinuity:
    def test_positive_extreme_bar(self):
        pf = _make_path_features(
            dollar_adv_21d=10_000_000.0,
            cs_spread_252=0.009,
            amihud_252=0.3,
            extreme_bar_freq_252=0.05,
            gap_share_252=0.20,
            reversal_half_life=10.0,
        )
        labels, _, _ = _classify_microstructure(pf)
        assert "gap_discontinuity_risk" in (labels or [])

    def test_positive_gap_share(self):
        pf = _make_path_features(
            dollar_adv_21d=10_000_000.0,
            cs_spread_252=0.009,
            amihud_252=0.3,
            extreme_bar_freq_252=0.01,
            gap_share_252=0.65,
            reversal_half_life=10.0,
        )
        labels, _, _ = _classify_microstructure(pf)
        assert "gap_discontinuity_risk" in (labels or [])

    def test_negative(self):
        pf = _make_path_features(
            dollar_adv_21d=10_000_000.0,
            cs_spread_252=0.009,
            amihud_252=0.3,
            extreme_bar_freq_252=0.01,
            gap_share_252=0.20,
        )
        labels, _, _ = _classify_microstructure(pf)
        assert "gap_discontinuity_risk" not in (labels or [])


class TestMicroSlowMeanReversionLiquidity:
    def test_positive(self):
        pf = _make_path_features(
            dollar_adv_21d=10_000_000.0,
            cs_spread_252=0.009,
            amihud_252=0.3,
            extreme_bar_freq_252=0.01,
            gap_share_252=0.20,
            reversal_half_life=3.0,
        )
        labels, _, _ = _classify_microstructure(pf)
        assert "slow_mean_reversion_liquidity" in (labels or [])

    def test_negative(self):
        pf = _make_path_features(reversal_half_life=8.0)
        labels, _, _ = _classify_microstructure(pf)
        assert "slow_mean_reversion_liquidity" not in (labels or [])


class TestMicroNoneOnVolumelessHistory:
    def test_none_when_no_volume_features(self):
        # All volume-dependent micro inputs None
        pf = _make_path_features(
            dollar_adv_21d=None,
            cs_spread_252=None,
            amihud_252=None,
            reversal_half_life=None,
            extreme_bar_freq_252=None,
            gap_share_252=None,
        )
        labels, missing, _ = _classify_microstructure(pf)
        assert labels is None
        assert any("volume" in m.lower() for m in missing)


class TestMicroMixedFallback:
    def test_mixed_when_nothing_matches(self):
        pf = _make_path_features(
            dollar_adv_21d=10_000_000.0,  # not tight ($50M), not thin ($5M)
            cs_spread_252=0.009,           # not tight (≤0.006), not wide (≥0.015)
            amihud_252=0.3,
            extreme_bar_freq_252=0.01,
            gap_share_252=0.20,
            reversal_half_life=8.0,        # > 5, so no slow_mr
        )
        labels, _, _ = _classify_microstructure(pf)
        assert "mixed_microstructure" in (labels or [])


# ---------------------------------------------------------------------------
# OWNERSHIP HABITAT — per-label
# ---------------------------------------------------------------------------


class TestOwnershipShortInterestTinderbox:
    def test_positive_short_pct(self):
        pos = _make_positioning(short_pct_float=20.0)
        labels, _, _, proxy = _classify_ownership(pos, None, [], None, None, None, None)
        assert labels is not None
        assert "short_interest_tinderbox" in labels
        assert "finra_si" in proxy

    def test_positive_dtc(self):
        pos = _make_positioning(short_pct_float=5.0, days_to_cover=10.0)
        labels, _, _, _ = _classify_ownership(pos, None, [], None, None, None, None)
        assert "short_interest_tinderbox" in (labels or [])

    def test_negative(self):
        pos = _make_positioning(short_pct_float=3.0, days_to_cover=2.0)
        labels, _, _, _ = _classify_ownership(pos, None, [], 0.1, 0.5, "none", 1e9)
        assert "short_interest_tinderbox" not in (labels or [])


class TestOwnershipRetailAttention:
    def test_positive(self):
        labels, _, _, proxy = _classify_ownership(
            _make_positioning(), None, [], None, 2.5, None, None
        )
        assert "retail_attention" in (labels or [])
        assert any("attention" in p for p in proxy)

    def test_negative(self):
        labels, _, _, _ = _classify_ownership(
            _make_positioning(), None, [], None, 1.0, None, None
        )
        assert "retail_attention" not in (labels or [])


class TestOwnershipInsiderFounderControlled:
    def test_positive(self):
        pos = _make_positioning(insider_cluster=True, insider_n_buyers=4, short_pct_float=2.0)
        labels, _, _, proxy = _classify_ownership(pos, None, [], None, 0.5, None, None)
        assert "insider_founder_controlled" in (labels or [])
        assert "form4_cluster" in proxy

    def test_negative_no_cluster(self):
        pos = _make_positioning(insider_cluster=False, insider_n_buyers=5)
        labels, _, _, _ = _classify_ownership(pos, None, [], None, None, None, None)
        assert "insider_founder_controlled" not in (labels or [])

    def test_negative_too_few_buyers(self):
        pos = _make_positioning(insider_cluster=True, insider_n_buyers=2)
        labels, _, _, _ = _classify_ownership(pos, None, [], None, None, None, None)
        assert "insider_founder_controlled" not in (labels or [])


class TestOwnershipPassiveIndexMagnet:
    def test_positive_etf_weight(self):
        labels, _, _, proxy = _classify_ownership(
            _make_positioning(), None, [], 0.6, None, None, None
        )
        assert "passive_index_magnet" in (labels or [])
        assert "etf_weight" in proxy

    def test_positive_large_cap(self):
        labels, _, _, _ = _classify_ownership(
            _make_positioning(), None, [], None, None, None, 300e9
        )
        assert "passive_index_magnet" in (labels or [])

    def test_negative(self):
        labels, _, _, _ = _classify_ownership(
            _make_positioning(), None, [], 0.1, None, None, 1e9
        )
        assert "passive_index_magnet" not in (labels or [])


class TestOwnershipEtfBasketedConduit:
    def test_positive(self):
        labels, _, _, proxy = _classify_ownership(
            _make_positioning(), None, ["QQQ", "XLK", "VGT"], None, None, None, None
        )
        assert "etf_basketed_conduit" in (labels or [])
        assert "basket_membership" in proxy

    def test_negative_one_basket(self):
        labels, _, _, _ = _classify_ownership(
            _make_positioning(), None, ["QQQ"], None, None, None, None
        )
        assert "etf_basketed_conduit" not in (labels or [])


class TestOwnershipLongOnlySponsor:
    def test_positive(self):
        pos = _make_positioning(short_pct_float=1.5)
        labels, _, _, proxy = _classify_ownership(
            pos, None, [], None, None, "passive", None
        )
        assert "long_only_sponsor" in (labels or [])
        assert "13dg_passive" in proxy

    def test_negative_high_short(self):
        pos = _make_positioning(short_pct_float=5.0)
        labels, _, _, _ = _classify_ownership(pos, None, [], None, None, "passive", None)
        assert "long_only_sponsor" not in (labels or [])

    def test_negative_wrong_bo_regime(self):
        pos = _make_positioning(short_pct_float=1.5)
        labels, _, _, _ = _classify_ownership(pos, None, [], None, None, "activist", None)
        assert "long_only_sponsor" not in (labels or [])


class TestOwnershipNoneWhenAllMissing:
    def test_none_on_no_inputs(self):
        labels, missing, _, _ = _classify_ownership(None, None, [], None, None, None, None)
        assert labels is None
        assert missing


class TestOwnershipMixedFallback:
    def test_mixed_when_nothing_matches(self):
        # Inputs present but nothing triggers a label
        pos = _make_positioning(short_pct_float=2.0, days_to_cover=1.0)
        labels, _, _, _ = _classify_ownership(pos, None, [], 0.1, 0.5, "custodial", 1e9)
        assert "mixed_ownership" in (labels or [])


# ---------------------------------------------------------------------------
# CURRENT MODE — per-label
# ---------------------------------------------------------------------------


class TestModeEventOverride:
    def test_positive_event_window(self):
        ev = {"days_to_earnings": 10, "event_window_active": True}
        modes, _, _, _ = _classify_current_mode(None, None, ev, _make_tech(), None, None, None)
        assert "event_override" in (modes or [])

    def test_positive_near_earnings(self):
        ev = {"days_to_earnings": 3, "event_window_active": False}
        modes, _, _, _ = _classify_current_mode(None, None, ev, _make_tech(), None, None, None)
        assert "event_override" in (modes or [])

    def test_negative(self):
        ev = {"days_to_earnings": 30, "event_window_active": False}
        tech = _make_tech()
        modes, _, _, _ = _classify_current_mode(None, None, ev, tech, None, None, None)
        assert "event_override" not in (modes or [])


class TestModeForcedLiquidation:
    def test_positive(self):
        tech = _make_tech(ret_21d=-0.30, rel_volume=3.0)
        modes, _, ev, _ = _classify_current_mode(None, None, None, tech, None, None, None)
        assert "forced_liquidation" in (modes or [])
        assert "ret_21d" in ev

    def test_negative_mild_drop(self):
        tech = _make_tech(ret_21d=-0.10, rel_volume=3.0)
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, None, None, None)
        assert "forced_liquidation" not in (modes or [])


class TestModeSqueeze:
    def test_positive(self):
        pos = _make_positioning(short_pct_float=20.0)
        tech = _make_tech(ret_21d=0.30)
        modes, _, _, _ = _classify_current_mode(pos, None, None, tech, None, None, None)
        assert "squeeze" in (modes or [])

    def test_negative_low_short(self):
        pos = _make_positioning(short_pct_float=3.0)
        tech = _make_tech(ret_21d=0.30)
        modes, _, _, _ = _classify_current_mode(pos, None, None, tech, None, None, None)
        assert "squeeze" not in (modes or [])


class TestModeOptionsPin:
    def test_positive(self):
        gex = {"gamma_regime": "positive", "flip_distance_pct": 1.5}
        tech = _make_tech()
        modes, _, ev, expiry = _classify_current_mode(None, gex, None, tech, None, None, None)
        assert "options_pin" in (modes or [])
        assert expiry == 7

    def test_negative_flip_too_far(self):
        gex = {"gamma_regime": "positive", "flip_distance_pct": 5.0}
        modes, _, _, _ = _classify_current_mode(None, gex, None, _make_tech(), None, None, None)
        assert "options_pin" not in (modes or [])


class TestModeNegativeGammaTrend:
    def test_positive(self):
        gex = {"gamma_regime": "negative", "flip_distance_pct": 10.0}
        modes, _, _, expiry = _classify_current_mode(None, gex, None, _make_tech(), None, None, None)
        assert "negative_gamma_trend" in (modes or [])
        assert expiry == 7

    def test_negative_regime_positive(self):
        gex = {"gamma_regime": "positive", "flip_distance_pct": 10.0}
        modes, _, _, _ = _classify_current_mode(None, gex, None, _make_tech(), None, None, None)
        assert "negative_gamma_trend" not in (modes or [])


class TestModeSectorRotationFeeder:
    def test_positive(self):
        tech = _make_tech()
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, None, True, None)
        assert "sector_rotation_feeder" in (modes or [])

    def test_negative(self):
        tech = _make_tech()
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, None, False, None)
        assert "sector_rotation_feeder" not in (modes or [])


class TestModePostNewsAttention:
    def test_positive(self):
        tech = _make_tech()
        modes, _, _, expiry = _classify_current_mode(None, None, None, tech, 4.0, None, None)
        assert "post_news_attention" in (modes or [])
        assert expiry == 7

    def test_negative(self):
        tech = _make_tech()
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, 1.5, None, None)
        assert "post_news_attention" not in (modes or [])


class TestModeStaleDeadMoney:
    def test_positive(self):
        tech = _make_tech(months_underwater=8.0, hv_pctile=20.0, rel_volume=0.5)
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, None, None, None)
        assert "stale_dead_money" in (modes or [])

    def test_negative_hv_too_high(self):
        tech = _make_tech(months_underwater=8.0, hv_pctile=50.0, rel_volume=0.5)
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, None, None, None)
        assert "stale_dead_money" not in (modes or [])


class TestModeAccumulation:
    def test_positive(self):
        tech = _make_tech(vol_squeeze_state="COILED", obv_slope_up=True)
        pf = _make_path_features(trend_persist_20=0.05)
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, None, None, pf)
        assert "accumulation" in (modes or [])

    def test_positive_compressed(self):
        tech = _make_tech(vol_squeeze_state="COMPRESSED", obv_slope_up=True)
        pf = _make_path_features(trend_persist_20=0.05)
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, None, None, pf)
        assert "accumulation" in (modes or [])

    def test_negative_no_obv(self):
        tech = _make_tech(vol_squeeze_state="COILED", obv_slope_up=False)
        pf = _make_path_features(trend_persist_20=0.05)
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, None, None, pf)
        assert "accumulation" not in (modes or [])


class TestModeDistribution:
    def test_positive(self):
        tech = _make_tech(off_52w_high_pct=5.0, obv_slope_up=False)
        pf = _make_path_features(failed_breakout_rate_63=0.60)
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, None, None, pf)
        assert "distribution" in (modes or [])

    def test_negative_obv_up(self):
        tech = _make_tech(off_52w_high_pct=5.0, obv_slope_up=True)
        pf = _make_path_features(failed_breakout_rate_63=0.60)
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, None, None, pf)
        assert "distribution" not in (modes or [])


class TestModeNormalDefault:
    def test_normal_when_nothing_fires(self):
        tech = _make_tech()  # no special conditions
        modes, _, _, _ = _classify_current_mode(None, None, None, tech, None, None, None)
        assert "normal" in (modes or [])

    def test_none_when_no_tech(self):
        modes, missing, _, _ = _classify_current_mode(None, None, None, None, None, None, None)
        assert modes is None
        assert "tech_missing" in missing


# ---------------------------------------------------------------------------
# PRECEDENCE and CAP tests
# ---------------------------------------------------------------------------


class TestChartPrecedence:
    def test_event_gapper_before_failed_breakout(self):
        """event_gapper has higher precedence than failed_breakout_trap."""
        pf = _make_path_features(
            event_gap_contrib_252=0.40,   # event_gapper fires
            failed_breakout_rate_63=0.65,  # failed_breakout_trap fires too
            gap_share_252=0.50,
            trend_persist_60=0.05,
        )
        labels, _, _ = _classify_chart(pf, {})
        assert labels is not None
        assert labels[0] == "event_gapper"

    def test_chart_max_2_labels(self):
        """At most CHART_MAX_LABELS labels."""
        pf = _make_path_features(
            event_gap_contrib_252=0.40,
            failed_breakout_rate_63=0.65,
            trend_persist_60=-0.15,
            trend_persist_126=0.10,
            pullback_median_252=0.03,
            extreme_bar_freq_252=0.01,
        )
        labels, _, _ = _classify_chart(pf, {})
        assert labels is not None
        assert len(labels) <= CHART_MAX_LABELS

    def test_precedence_list_is_canonical(self):
        """CHART_PRECEDENCE contains all expected labels."""
        expected = {
            "event_gapper", "failed_breakout_trap", "mean_reversion_rubber_band",
            "smooth_compounder_grind", "stair_step_leader", "volatile_momentum_vehicle",
            "basing_accumulator", "defensive_range_stock", "mixed_chart",
        }
        assert set(CHART_PRECEDENCE) == expected


class TestModePrecedence:
    def test_event_override_before_accumulation(self):
        """event_override has higher precedence than accumulation."""
        ev = {"days_to_earnings": 3, "event_window_active": True}
        tech = _make_tech(vol_squeeze_state="COILED", obv_slope_up=True)
        pf = _make_path_features(trend_persist_20=0.05)
        modes, _, _, _ = _classify_current_mode(None, None, ev, tech, None, None, pf)
        assert modes is not None
        assert modes[0] == "event_override"

    def test_mode_max_labels(self):
        """Modes list never exceeds MODE_MAX_LABELS."""
        ev = {"days_to_earnings": 3, "event_window_active": True}
        pos = _make_positioning(short_pct_float=20.0)
        gex = {"gamma_regime": "negative", "flip_distance_pct": 5.0}
        tech = _make_tech(ret_21d=0.30)
        modes, _, _, _ = _classify_current_mode(pos, gex, ev, tech, 4.0, True, None)
        assert modes is not None
        assert len(modes) <= MODE_MAX_LABELS

    def test_options_pin_expiry_7(self):
        gex = {"gamma_regime": "positive", "flip_distance_pct": 1.0}
        modes, _, _, expiry = _classify_current_mode(None, gex, None, _make_tech(), None, None, None)
        assert "options_pin" in (modes or [])
        assert expiry == 7

    def test_normal_expiry_21(self):
        _, _, _, expiry = _classify_current_mode(None, None, None, _make_tech(), None, None, None)
        assert expiry == 21


class TestOwnershipPrecedence:
    def test_tinderbox_before_retail(self):
        pos = _make_positioning(short_pct_float=20.0)
        labels, _, _, _ = _classify_ownership(pos, None, [], None, 3.0, None, None)
        assert labels is not None
        assert labels[0] == "short_interest_tinderbox"

    def test_ownership_max_3(self):
        pos = _make_positioning(
            short_pct_float=20.0, insider_cluster=True, insider_n_buyers=4
        )
        labels, _, _, _ = _classify_ownership(
            pos, None, ["QQQ", "XLK"], 0.6, 3.0, "passive", 300e9
        )
        assert labels is not None
        assert len(labels) <= 3


# ---------------------------------------------------------------------------
# DEGRADATION tests
# ---------------------------------------------------------------------------


class TestDegradation:
    def test_bare_assess_no_exception(self):
        """assess() with only ticker+as_of must not raise."""
        result = assess("AAPL", as_of="2026-01-01")
        assert result is not None
        assert result["schema"] == "stock_personality.v1"

    def test_bare_assess_axes_none(self):
        result = assess("AAPL", as_of="2026-01-01")
        base = result["base"]
        assert base["archetype"]["key"] is None
        assert base["dna_class"]["key"] is None
        assert base["ownership_habitat"]["labels"] is None
        assert base["microstructure"]["labels"] is None
        assert base["chart_personality"]["labels"] is None

    def test_bare_assess_missing_populated(self):
        result = assess("AAPL", as_of="2026-01-01")
        missing = result["evidence"]["missing"]
        assert len(missing) > 0
        # Expect at least archetype, dna_class, ownership missing
        assert "archetype" in missing
        assert "dna_class" in missing

    def test_bare_assess_mode_none(self):
        result = assess("AAPL", as_of="2026-01-01")
        assert result["current_mode"]["modes"] is None

    def test_close_only_path_features_no_exception(self):
        """Close-only path_features (gap keys None) must not raise."""
        pf = _make_path_features(gap_share_252=None, event_gap_contrib_252=None)
        result = assess(
            "XYZ",
            as_of="2026-01-01",
            path_features=pf,
            tech=_make_tech(),
        )
        assert result is not None
        labels = result["base"]["chart_personality"]["labels"]
        if labels:
            assert "event_gapper" not in labels

    def test_missing_is_deduplicated(self):
        result = assess("AAPL", as_of="2026-01-01")
        missing = result["evidence"]["missing"]
        assert len(missing) == len(set(missing))


# ---------------------------------------------------------------------------
# AUTHORITY STANZA tests
# ---------------------------------------------------------------------------


class TestAuthorityStanza:
    def test_exact_authority_keys(self):
        result = assess("AAPL", as_of="2026-01-01")
        auth = result["authority"]
        assert auth == {
            "tier": "display",
            "confidence_class": "descriptive",
            "weights": "none",
            "may_rank": False,
            "may_size": False,
            "may_gate": False,
        }

    def test_authority_is_constant(self):
        """The module-level _AUTHORITY dict matches the expected stanza."""
        assert _AUTHORITY["tier"] == "display"
        assert _AUTHORITY["may_rank"] is False
        assert _AUTHORITY["may_size"] is False
        assert _AUTHORITY["may_gate"] is False

    def test_authority_not_mutated_across_calls(self):
        r1 = assess("AAPL", as_of="2026-01-01")
        r2 = assess("MSFT", as_of="2026-01-02")
        assert r1["authority"] == r2["authority"]


# ---------------------------------------------------------------------------
# SCHEMA KEYS test
# ---------------------------------------------------------------------------


class TestSchemaKeys:
    def test_top_level_keys(self):
        result = assess("AAPL", as_of="2026-01-01")
        assert set(result.keys()) == {
            "schema", "as_of", "ticker",
            "base", "current_mode", "setup_compatibility",
            "evidence", "authority",
        }

    def test_base_keys(self):
        result = assess("AAPL", as_of="2026-01-01")
        assert set(result["base"].keys()) == {
            "archetype", "dna_class", "ownership_habitat",
            "microstructure", "chart_personality",
        }

    def test_current_mode_keys(self):
        result = assess("AAPL", as_of="2026-01-01")
        cm = result["current_mode"]
        assert "modes" in cm
        assert "evidence" in cm
        assert "expires_after_days" in cm

    def test_evidence_keys(self):
        result = assess("AAPL", as_of="2026-01-01")
        ev = result["evidence"]
        assert "coverage" in ev
        assert "missing" in ev
        assert "as_of_by_axis" in ev
        assert "lineage" in ev

    def test_setup_compatibility_keys(self):
        result = assess("AAPL", as_of="2026-01-01")
        sc = result["setup_compatibility"]
        assert "favored_species" in sc
        assert "caution_species" in sc
        assert "derived_from" in sc

    def test_schema_version_string(self):
        result = assess("AAPL", as_of="2026-01-01")
        assert result["schema"] == "stock_personality.v1"

    def test_lineage_path(self):
        result = assess("AAPL", as_of="2026-01-01")
        assert "STOCK_PERSONALITY_MASTERPLAN_BY_FABLE" in result["evidence"]["lineage"]


# ---------------------------------------------------------------------------
# SETUP COMPATIBILITY tests
# ---------------------------------------------------------------------------


class TestSetupCompatibility:
    def _make_species(
        self,
        sid: str,
        status: str,
        applies: list | str,
        hostile: list | str,
    ) -> dict:
        return {
            "id": sid,
            "validation_status": status,
            "archetype_scope": {"applies": applies, "hostile": hostile},
        }

    def test_favored_match(self):
        personality = assess(
            "AAPL",
            as_of="2026-01-01",
            archetype={"key": "quality_compounder", "confidence": 0.8},
        )
        species = [
            self._make_species("S1", "accruing", ["quality_compounder"], []),
            self._make_species("S2", "validated", [], ["quality_compounder"]),
            self._make_species("S3", "retired", ["quality_compounder"], []),  # excluded
        ]
        result = setup_compatibility(personality, species)
        assert "S1" in result["favored_species"]
        assert "S2" in result["caution_species"]
        assert "S3" not in result["favored_species"]
        assert "S3" not in result["caution_species"]

    def test_hostile_match(self):
        personality = assess(
            "AAPL",
            as_of="2026-01-01",
            archetype={"key": "speculative_unprofitable", "confidence": 0.9},
        )
        species = [
            self._make_species("S10", "phase0", [], ["speculative_unprofitable"]),
        ]
        result = setup_compatibility(personality, species)
        assert "S10" in result["caution_species"]
        assert "S10" not in result["favored_species"]

    def test_retired_excluded(self):
        personality = assess(
            "AAPL",
            as_of="2026-01-01",
            archetype={"key": "high_beta_momentum", "confidence": 0.7},
        )
        species = [
            self._make_species("S99", "retired", ["high_beta_momentum"], []),
        ]
        result = setup_compatibility(personality, species)
        assert "S99" not in result["favored_species"]

    def test_hyphen_variant_matches(self):
        """Archetype key underscore variant matches hyphen in scope text."""
        personality = assess(
            "AAPL",
            as_of="2026-01-01",
            archetype={"key": "high_beta_momentum", "confidence": 0.7},
        )
        species = [
            self._make_species("S5", "validated", ["high-beta-momentum"], []),
        ]
        result = setup_compatibility(personality, species)
        assert "S5" in result["favored_species"]

    def test_derived_from_field(self):
        personality = assess("AAPL", as_of="2026-01-01")
        result = setup_compatibility(personality, [])
        assert "display-only" in result["derived_from"]

    def test_empty_species_list(self):
        personality = assess("AAPL", as_of="2026-01-01")
        result = setup_compatibility(personality, [])
        assert result["favored_species"] == []
        assert result["caution_species"] == []

    def test_none_archetype_no_matches(self):
        """No archetype → no matches, no exception."""
        personality = assess("AAPL", as_of="2026-01-01")  # archetype is None
        species = [
            self._make_species("S1", "accruing", ["quality_compounder"], []),
        ]
        result = setup_compatibility(personality, species)
        assert result["favored_species"] == []
        assert result["caution_species"] == []


# ---------------------------------------------------------------------------
# DETERMINISM tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_twice(self):
        pf = _make_path_features()
        tech = _make_tech()
        pos = _make_positioning()
        r1 = assess(
            "AAPL",
            as_of="2026-01-01",
            path_features=pf,
            tech=tech,
            positioning=pos,
            archetype={"key": "quality_compounder", "confidence": 0.8},
        )
        r2 = assess(
            "AAPL",
            as_of="2026-01-01",
            path_features=pf,
            tech=tech,
            positioning=pos,
            archetype={"key": "quality_compounder", "confidence": 0.8},
        )
        assert r1 == r2

    def test_inputs_not_mutated(self):
        pf = _make_path_features()
        pf_orig = copy.deepcopy(pf)
        tech = _make_tech()
        tech_orig = copy.deepcopy(tech)
        assess("AAPL", as_of="2026-01-01", path_features=pf, tech=tech)
        assert pf == pf_orig
        assert tech == tech_orig


# ---------------------------------------------------------------------------
# FULL INTEGRATION — assess() with rich inputs
# ---------------------------------------------------------------------------


class TestAssessIntegration:
    def test_full_rich_inputs(self):
        """Smoke test with all inputs present — no exception, valid schema."""
        result = assess(
            "NVDA",
            as_of="2026-07-06",
            path_features=_make_path_features(
                event_gap_contrib_252=0.40,
                trend_persist_126=0.10,
                pullback_median_252=0.03,
                extreme_bar_freq_252=0.01,
            ),
            archetype={"key": "secular_growth", "confidence": 0.85},
            dna_class={"key": "quality_growth", "style_regime": "growth_momentum", "as_of": "2026-07-05"},
            positioning={"short_pct_float": 2.0, "days_to_cover": 0.5,
                         "insider_net_usd_mn": 5.0, "insider_cluster": False,
                         "insider_n_buyers": 0},
            smart_money={"ownership_hhi": 0.08, "n_holders": 2500},
            basket_membership=["ai_leaders", "semiconductors", "growth_mega"],
            etf_weight_max=0.8,
            attention_z=1.5,
            bo_regime="none",
            gex={"gamma_regime": "positive", "flip_distance_pct": 5.0},
            events={"days_to_earnings": 30, "event_window_active": False},
            tech=_make_tech(hv_pctile=75.0, rel_volume=1.2),
            oracle_episode_active=False,
            market_cap=3_000_000_000_000.0,
        )
        assert result["schema"] == "stock_personality.v1"
        assert result["base"]["archetype"]["key"] == "secular_growth"
        assert result["base"]["dna_class"]["key"] == "quality_growth"
        # event_gapper should fire (event_gap_contrib_252 = 0.40)
        chart = result["base"]["chart_personality"]["labels"]
        assert chart is not None
        assert "event_gapper" in chart
        # passive_index_magnet should fire (etf_weight_max=0.8)
        own = result["base"]["ownership_habitat"]["labels"]
        assert own is not None
        assert "passive_index_magnet" in own
        # Coverage values should be > 0 for all axes
        cov = result["evidence"]["coverage"]
        assert cov["archetype"] == 1.0
        assert cov["dna_class"] == 1.0

    def test_archetype_and_dna_passthrough(self):
        result = assess(
            "XYZ",
            as_of="2026-01-01",
            archetype={"key": "distressed", "confidence": 0.6},
            dna_class={"key": "deep_value", "style_regime": "value_defensive", "as_of": "2026-01-01"},
        )
        assert result["base"]["archetype"]["key"] == "distressed"
        assert result["base"]["archetype"]["source"] == "stock_fundamentals.v2"
        assert result["base"]["dna_class"]["key"] == "deep_value"
        assert result["base"]["dna_class"]["source"] == "site/factordata/dna_class.json"

    def test_coverage_populated(self):
        result = assess(
            "AAPL",
            as_of="2026-01-01",
            path_features=_make_path_features(),
            tech=_make_tech(),
            positioning=_make_positioning(),
            attention_z=0.5,
            etf_weight_max=0.1,
        )
        cov = result["evidence"]["coverage"]
        assert cov["micro"] > 0
        assert cov["chart"] > 0
        assert cov["ownership"] > 0
