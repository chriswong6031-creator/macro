"""Unit tests for NET-REPLAY-1 cost model (scripts/research/net_replay_v1.py).

Tests cover:
1. ADV$-banded spread floor banding logic.
2. Corwin-Schultz max vs floor selection.
3. Square-root impact units (eta * sigma * sqrt(participation) * 10000 bps).
4. Cash-carry accrual (annualized percent unit, DTB3 convention).
5. Round-trip = 2 one-way legs for both spread and impact.
6. Absent-store degradation (missing perfire → clean skip, no crash).
7. Representative ADV$ weighted average math.
8. Net cost = spread + impact - carry (signs correct).

All fixtures are synthetic — no real market data required.
"""
from __future__ import annotations

import importlib
import json
import math
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ── import the module under test ──────────────────────────────────────────────
# We need to import without running main(); the module-level constants are safe.
import importlib.util

def _load_module():
    """Load net_replay_v1 without executing main."""
    spec = importlib.util.spec_from_file_location(
        "net_replay_v1",
        Path(__file__).parents[1] / "scripts" / "research" / "net_replay_v1.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


try:
    nrv1 = _load_module()
    MODULE_AVAILABLE = True
except Exception as e:
    MODULE_AVAILABLE = False
    _LOAD_ERROR = str(e)


def _skip_if_unavailable():
    if not MODULE_AVAILABLE:
        pytest.skip(f"net_replay_v1 module not loadable: {_LOAD_ERROR}")


# ── 1. ADV$-banded spread floor ───────────────────────────────────────────────

class TestAdvBandedFloor:
    def setup_method(self):
        _skip_if_unavailable()

    def test_large_cap_floor(self):
        """ADV > $50M → 3 bps floor."""
        bps = nrv1._adv_banded_floor_bps(100_000_000)
        assert bps == 3.0

    def test_exact_50m_threshold(self):
        """ADV = $50M exactly → 3 bps (at or above threshold)."""
        bps = nrv1._adv_banded_floor_bps(50_000_000)
        assert bps == 3.0

    def test_mid_cap_floor(self):
        """ADV $10-50M → 8 bps floor."""
        bps = nrv1._adv_banded_floor_bps(25_000_000)
        assert bps == 8.0

    def test_small_cap_floor(self):
        """ADV < $10M → 20 bps floor."""
        bps = nrv1._adv_banded_floor_bps(5_000_000)
        assert bps == 20.0

    def test_exact_10m_threshold(self):
        """ADV = $10M exactly → 8 bps (at threshold)."""
        bps = nrv1._adv_banded_floor_bps(10_000_000)
        assert bps == 8.0

    def test_very_small_adv(self):
        """ADV = $0 → 20 bps floor (smallest bucket)."""
        bps = nrv1._adv_banded_floor_bps(0)
        assert bps == 20.0


# ── 2. Corwin-Schultz max vs floor ───────────────────────────────────────────

class TestOneWaySpread:
    def setup_method(self):
        _skip_if_unavailable()

    def test_cs_wins_over_floor(self):
        """CS proxy (50 bps) > floor (3 bps for large cap) → CS wins."""
        spread = nrv1._one_way_spread_bps(
            cs_spread_frac=0.005,   # 0.5% = 50 bps
            adv_usd=100_000_000,    # large cap, floor=3 bps
        )
        assert abs(spread - 50.0) < 0.01

    def test_floor_wins_over_cs(self):
        """CS proxy (1 bps) < floor (8 bps for mid-cap) → floor wins."""
        spread = nrv1._one_way_spread_bps(
            cs_spread_frac=0.0001,  # 1 bps
            adv_usd=25_000_000,     # mid-cap, floor=8 bps
        )
        assert spread == 8.0

    def test_none_cs_uses_floor(self):
        """None CS → floor only."""
        spread = nrv1._one_way_spread_bps(
            cs_spread_frac=None,
            adv_usd=100_000_000,
        )
        assert spread == 3.0

    def test_nan_cs_uses_floor(self):
        """NaN CS → floor only."""
        import math
        spread = nrv1._one_way_spread_bps(
            cs_spread_frac=float("nan"),
            adv_usd=25_000_000,
        )
        assert spread == 8.0


# ── 3. Square-root impact units ───────────────────────────────────────────────

class TestImpactBps:
    def setup_method(self):
        _skip_if_unavailable()

    def test_zero_adv(self):
        """ADV = 0 → 0 impact (no division by zero)."""
        bps = nrv1._impact_bps(10_000, 0, sigma_daily=0.025)
        assert bps == 0.0

    def test_known_value(self):
        """Verify: eta=0.1, sigma=0.025, participation=pos/adv.

        pos=10k, adv=100M → participation=1e-4
        impact_rate = 0.1 * 0.025 * sqrt(1e-4) = 0.1 * 0.025 * 0.01 = 2.5e-5
        impact_bps = 2.5e-5 * 10000 = 0.25 bps
        """
        bps = nrv1._impact_bps(10_000, 100_000_000, sigma_daily=0.025)
        expected = nrv1.IMPACT_ETA * 0.025 * math.sqrt(10_000 / 100_000_000) * 10_000
        assert abs(bps - expected) < 1e-8

    def test_scales_with_sqrt_participation(self):
        """Impact scales with sqrt(participation): 4x position → 2x impact."""
        bps_base = nrv1._impact_bps(10_000, 1_000_000, sigma_daily=0.025)
        bps_4x = nrv1._impact_bps(40_000, 1_000_000, sigma_daily=0.025)
        assert abs(bps_4x / bps_base - 2.0) < 1e-6

    def test_participation_capped_at_1x_adv(self):
        """Position > ADV$ is capped at participation=1.0."""
        bps_1x = nrv1._impact_bps(1_000_000, 1_000_000, sigma_daily=0.025)
        bps_2x = nrv1._impact_bps(2_000_000, 1_000_000, sigma_daily=0.025)
        assert abs(bps_1x - bps_2x) < 1e-8  # both capped at participation=1


# ── 4. Cash-carry accrual ─────────────────────────────────────────────────────

class TestCashCarry:
    def setup_method(self):
        _skip_if_unavailable()

    def test_zero_days_saved(self):
        """No freed days → zero carry credit."""
        credit = nrv1._cash_carry_credit_per_bar(0.0, dtb3_pct=3.69)
        assert credit == 0.0

    def test_zero_rate(self):
        """DTB3=0 → zero carry credit."""
        credit = nrv1._cash_carry_credit_per_bar(100.0, dtb3_pct=0.0)
        assert credit == 0.0

    def test_known_value(self):
        """Verify: 175 days freed at 3.69%/yr.

        credit = (3.69 / 100) * (175 / 365) = 0.0369 * 0.4795 = ~0.01769 (1.769%)
        """
        credit = nrv1._cash_carry_credit_per_bar(175.0, dtb3_pct=3.69)
        expected = (3.69 / 100.0) * (175.0 / 365.0)
        assert abs(credit - expected) < 1e-8

    def test_annualized_percent_not_fraction(self):
        """DTB3 is annualized PERCENT (3.69 means 3.69%/yr, NOT 3.69 as a fraction).

        If caller accidentally passed 0.0369 (fraction), result should be much smaller.
        """
        credit_pct = nrv1._cash_carry_credit_per_bar(365.0, dtb3_pct=3.69)
        credit_frac = nrv1._cash_carry_credit_per_bar(365.0, dtb3_pct=0.0369)
        # credit_pct should be 3.69% ≈ 0.0369; credit_frac should be 0.000369
        assert abs(credit_pct - 0.0369) < 1e-6
        assert abs(credit_frac - 0.000369) < 1e-8

    def test_negative_days_returns_zero(self):
        """Negative freed days (hold longer than reference) → zero credit."""
        credit = nrv1._cash_carry_credit_per_bar(-10.0, dtb3_pct=3.69)
        assert credit == 0.0


# ── 5. Round-trip = 2 one-way legs ───────────────────────────────────────────

class TestRoundTrip:
    def setup_method(self):
        _skip_if_unavailable()

    def test_round_trip_spread_is_2x_one_way(self):
        """Round-trip spread = 2 * one-way spread."""
        cost = nrv1._total_cost_bps(10_000, 100_000_000, cs_spread_frac=None)
        one_way = nrv1._one_way_spread_bps(None, 100_000_000)
        assert abs(cost["round_trip_spread_bps"] - 2.0 * one_way) < 1e-6

    def test_round_trip_impact_is_2x_one_way(self):
        """Round-trip impact = 2 * one-way impact."""
        cost = nrv1._total_cost_bps(10_000, 100_000_000, cs_spread_frac=None,
                                    sigma_daily=0.025)
        one_way_impact = nrv1._impact_bps(10_000, 100_000_000, sigma_daily=0.025)
        assert abs(cost["round_trip_impact_bps"] - 2.0 * one_way_impact) < 1e-6

    def test_total_is_spread_plus_impact(self):
        """Total round-trip = round_trip_spread + round_trip_impact."""
        cost = nrv1._total_cost_bps(10_000, 100_000_000, cs_spread_frac=None,
                                    sigma_daily=0.025)
        expected_total = cost["round_trip_spread_bps"] + cost["round_trip_impact_bps"]
        assert abs(cost["total_round_trip_bps"] - expected_total) < 1e-6


# ── 6. Absent-store degradation ───────────────────────────────────────────────

class TestAbsentStoreDegradation:
    def setup_method(self):
        _skip_if_unavailable()

    def test_missing_perfire_returns_none_no_crash(self):
        """_try_load_perfire with no file → returns None, prints note."""
        with tempfile.TemporaryDirectory() as tmp:
            # Patch _DATA to a temp dir with no files
            with patch.object(nrv1, "_DATA", Path(tmp)), \
                 patch.object(nrv1, "_MAIN_DATA", Path(tmp)):
                result = nrv1._try_load_perfire("nonexistent_exp")
        assert result is None

    def test_missing_massive_returns_zero_coverage(self):
        """_load_massive_sample with absent dir → coverage_n=0, no crash."""
        result = nrv1._load_massive_sample(Path("/tmp/__nonexistent_macro_dir__"))
        assert result["coverage_n"] == 0
        assert result["weighted_median_adv_usd"] is None

    def test_price_cell_works_without_perfire(self):
        """_price_cell with representative ADV$ and no CS → completes without error."""
        import json
        # Minimal cell fixture (matches exit_grid_v1 structure)
        cell = {
            "exit_policy": {"kind": "hold", "H": 21},
            "mean_exit_ret": 0.0193,
            "wr": 0.577,
            "median_exit_ret": 0.0163,
            "n_fires": 49939,
            "held_to_reference_pct": 0.0,
        }
        result = nrv1._price_cell(
            cell_key="hold_21",
            cell=cell,
            dtb3_pct=3.69,
            representative_adv_usd=157_970_000,
            cs_spread_frac=None,
            sigma_daily=0.025,
        )
        # Should have all three position sizes
        assert "pos_10k" in result["net_by_position_size"]
        assert "pos_100k" in result["net_by_position_size"]
        assert "pos_1m" in result["net_by_position_size"]
        # gross should be copied exactly
        assert result["gross"]["mean_ret"] == 0.0193
        # JSON-serializable
        json.dumps(result)


# ── 7. Representative ADV$ weighted average ───────────────────────────────────

class TestRepresentativeAdv:
    def setup_method(self):
        _skip_if_unavailable()

    def test_weighted_average_exact(self):
        """Weighted ADV$ = sum(weight_i * adv_i)."""
        weights = {"T1": 0.5, "T2": 0.3, "T3": 0.2}
        adv = {"T1": 100.0, "T2": 50.0, "T3": 10.0}
        result = nrv1._compute_representative_adv_weighted(weights, adv)
        expected = 0.5 * 100 + 0.3 * 50 + 0.2 * 10
        assert abs(result - expected) < 1e-10

    def test_module_constants_sum_to_one(self):
        """TIER_WEIGHTS must sum to 1.0."""
        total = sum(nrv1.TIER_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9


# ── 8. Net cost sign convention ───────────────────────────────────────────────

class TestNetCostSign:
    def setup_method(self):
        _skip_if_unavailable()

    def test_net_cost_hold126_no_carry(self):
        """hold(126) = reference: no carry credit, net_cost > 0 (pure friction)."""
        costs = nrv1._compute_cell_cost_at_size(
            position_usd=10_000,
            mean_holding_bars=126,   # exactly at reference
            reference_bars=126,
            dtb3_pct=3.69,
            adv_usd=100_000_000,
            cs_spread_frac=None,
            sigma_daily=0.025,
        )
        assert costs["carry_freed_days"] == 0.0
        assert costs["carry_credit_bps"] == 0.0
        assert costs["net_cost_bps"] > 0  # pure cost, no carry

    def test_net_cost_short_hold_has_carry_credit(self):
        """Short hold (5 bars) → large carry credit, net_cost may be negative (net gain)."""
        costs = nrv1._compute_cell_cost_at_size(
            position_usd=10_000,
            mean_holding_bars=5,
            reference_bars=126,
            dtb3_pct=3.69,
            adv_usd=100_000_000,   # large cap → very low spread/impact
            cs_spread_frac=None,
            sigma_daily=0.025,
        )
        # ~121 freed bars * 365/252 days/bar ≈ 175 calendar days
        assert costs["carry_freed_days"] > 0
        assert costs["carry_credit_bps"] > 0
        # net_cost = spread + impact - carry; for large cap with 175d carry, carry dominates
        # This is economically correct per RUL-F3.9 framing

    def test_gross_to_net_adjustment(self):
        """_gross_mean_to_net subtracts net_cost_bps correctly."""
        gross = 0.050   # 5.0%
        net_cost_bps = 10.0   # 10 bps = 0.10%
        net = nrv1._gross_mean_to_net(gross, net_cost_bps)
        assert abs(net - (gross - 10.0 / 10_000.0)) < 1e-10

    def test_gross_to_net_none_input(self):
        """None gross_mean → None net (no crash)."""
        net = nrv1._gross_mean_to_net(None, 10.0)
        assert net is None
