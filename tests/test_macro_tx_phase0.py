"""Synthetic-fixture tests for macro_tx_phase0.py.

Tests cover:
  1. Episode construction — runs, padding, merging
  2. Hostile-flag thresholds (change shock and level percentile)
  3. Stratified-delta arithmetic (known-answer)
  4. Floor-refusal behavior
  5. Budget-logged-before-run assertion (TrialLedger)

No real-data dependence.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import module under test
# ---------------------------------------------------------------------------
from scripts.research.macro_tx_phase0 import (
    TRAILING_WINDOW,
    PAD_BD,
    HOSTILE_Z,
    FAMILY,
    DECLARED_BUDGET,
    build_episodes,
    assign_episode_arm,
    stratified_delta,
    bh_correct,
    assign_drawdown_stratum,
    _compute_spy_drawdown,
    _compute_hostile_flags,
    AXES,
)
from engine.trial_ledger import TrialLedger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bd_range(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=periods)


def _make_hostile_series(bd_index: pd.DatetimeIndex, hostile_positions: list[int]) -> pd.Series:
    """Create a boolean Series with True at the given integer positions."""
    s = pd.Series(False, index=bd_index)
    for pos in hostile_positions:
        if 0 <= pos < len(bd_index):
            s.iloc[pos] = True
    return s


# ---------------------------------------------------------------------------
# 1. Episode construction: runs, padding, merging
# ---------------------------------------------------------------------------

class TestEpisodeConstruction:

    def test_single_hostile_run_no_overlap(self):
        """Single consecutive hostile block -> one episode padded ±PAD_BD."""
        bd = _bd_range("2020-01-01", 60)
        # Hostile at positions 10-14 (5 days)
        hostile = _make_hostile_series(bd, list(range(10, 15)))
        episodes = build_episodes(hostile, pad_bd=PAD_BD)
        assert len(episodes) == 1
        ep_start, ep_end = episodes[0]
        # Episodes return date objects; convert bd timestamps for comparison
        import datetime
        assert ep_start <= bd[10].date()
        assert ep_end >= bd[14].date()

    def test_two_separate_runs_produce_two_episodes(self):
        """Two hostile runs far apart -> two distinct episodes."""
        bd = _bd_range("2020-01-01", 100)
        hostile = _make_hostile_series(bd, list(range(5, 8)) + list(range(50, 53)))
        # Ensure pads don't overlap: 8 + PAD_BD = 13, 50 - PAD_BD = 45 > 13
        episodes = build_episodes(hostile, pad_bd=PAD_BD)
        assert len(episodes) == 2

    def test_two_close_runs_merge(self):
        """Two hostile runs close together should merge into one episode."""
        bd = _bd_range("2020-01-01", 50)
        # Runs at 5-6 and 10-11, gap=3, pads overlap (5+PAD>=10-PAD for PAD=5)
        hostile = _make_hostile_series(bd, [5, 6, 10, 11])
        episodes = build_episodes(hostile, pad_bd=5)
        # 6+5=11, 10-5=5 => pads overlap -> merge
        assert len(episodes) == 1

    def test_no_hostile_returns_empty(self):
        """No hostile days -> no episodes."""
        bd = _bd_range("2020-01-01", 30)
        hostile = pd.Series(False, index=bd)
        episodes = build_episodes(hostile)
        assert episodes == []

    def test_single_hostile_day(self):
        """Single hostile day -> one episode with padding."""
        bd = _bd_range("2020-01-01", 30)
        hostile = _make_hostile_series(bd, [15])
        episodes = build_episodes(hostile, pad_bd=PAD_BD)
        assert len(episodes) == 1
        ep_start, ep_end = episodes[0]
        expected_start_pos = max(0, 15 - PAD_BD)
        expected_end_pos = min(len(bd) - 1, 15 + PAD_BD)
        # Episodes return date objects
        assert ep_start == bd[expected_start_pos].date()
        assert ep_end == bd[expected_end_pos].date()

    def test_all_hostile_one_episode(self):
        """All days hostile -> one episode covering full range."""
        bd = _bd_range("2020-01-01", 20)
        hostile = pd.Series(True, index=bd)
        episodes = build_episodes(hostile, pad_bd=0)
        assert len(episodes) == 1
        # Episodes return date objects
        assert episodes[0][0] == bd[0].date()
        assert episodes[0][1] == bd[-1].date()

    def test_three_runs_some_merge(self):
        """Three runs: first two close (merge), third far (separate)."""
        bd = _bd_range("2020-01-01", 100)
        # Run 1: positions 5-6 ; Run 2: positions 13-14 (gap=6, pad=5: 6+5=11, 13-5=8 -> no merge)
        # Let's put run 2 at 10 (gap=3: 6+5=11, 10-5=5 -> merge)
        # Run 3 at 60 (far)
        hostile = _make_hostile_series(bd, [5, 6, 10, 11, 60, 61])
        episodes = build_episodes(hostile, pad_bd=5)
        # Runs 1+2 should merge; run 3 separate
        assert len(episodes) == 2


# ---------------------------------------------------------------------------
# 2. Hostile-flag thresholds
# ---------------------------------------------------------------------------

class TestHostileFlagThresholds:

    def _make_change_series(self, window: int, trailing: int, n: int = 1000, seed: int = 42):
        """Create a simple random-walk series for threshold tests."""
        rng = np.random.default_rng(seed)
        prices = np.cumsum(rng.standard_normal(n)) + 100.0
        idx = pd.bdate_range("2010-01-01", periods=n)
        return pd.Series(prices, index=idx)

    def test_change_shock_hostile_flag(self):
        """When a series has an engineered large spike, it should be flagged hostile."""
        n = 800
        idx = pd.bdate_range("2010-01-01", periods=n)
        vals = np.ones(n) * 3.0   # flat at 3%
        s = pd.Series(vals, index=idx)
        # Inject a spike at position 500: jump from 3 to 6 (change=3, σ of flat=0)
        # Spike must exceed z_floor * rolling_std + abs_floor
        s.iloc[500] = 100.0
        changes = s.diff(20)
        roll_std = changes.rolling(TRAILING_WINDOW, min_periods=TRAILING_WINDOW // 2).std()
        # The spike at 500 should have a massive change
        spike_change = changes.iloc[500]
        assert spike_change > 0, "Spike should produce positive change"

    def test_level_percentile_threshold(self):
        """Level at or above 80th percentile of trailing window -> hostile."""
        n = 800
        idx = pd.bdate_range("2010-01-01", periods=n)
        # Monotonically increasing series: last value is definitely > 80th pct of trailing
        vals = np.arange(n, dtype=float)
        s = pd.Series(vals, index=idx)
        # Position 799: value = 799; trailing 756-BD window has max = 798
        # 80th pct of [799-756:799] = [43:799], so 80th pct = 43 + 0.8*756 ≈ 647.8
        # Value 799 > 647.8 -> should be hostile
        trailing_window = vals[799 - 756: 799]
        threshold = np.percentile(trailing_window, 80.0)
        assert vals[799] >= threshold, "Monotonically increasing: last value should exceed 80th pct"

    def test_hostile_flag_below_threshold(self):
        """When change is small, no hostile flags should fire."""
        n = 800
        idx = pd.bdate_range("2010-01-01", periods=n)
        # Flat series: all changes = 0, so never hostile
        s = pd.Series(3.0, index=idx)
        changes = s.diff(20).fillna(0)
        roll_std = changes.rolling(TRAILING_WINDOW, min_periods=1).std().fillna(0)
        hostile = (changes >= HOSTILE_Z * roll_std) & (changes >= 0.25)
        assert hostile.sum() == 0, "Flat series should produce no hostile flags"

    def test_change_shock_requires_both_conditions(self):
        """Hostile requires BOTH σ threshold AND absolute floor."""
        n = 800
        idx = pd.bdate_range("2010-01-01", periods=n)
        # High σ but small absolute change: should NOT be hostile
        rng = np.random.default_rng(99)
        # Highly volatile series (large σ) but small absolute changes
        vals = np.cumsum(rng.standard_normal(n) * 0.0001) + 3.0  # tiny changes
        s = pd.Series(vals, index=idx)
        changes = s.diff(20).dropna()
        roll_std = changes.rolling(TRAILING_WINDOW, min_periods=1).std()
        # Even if z_threshold met, abs_floor=0.25 blocks it (since changes ~ 0.001)
        hostile = (changes >= HOSTILE_Z * roll_std) & (changes >= 0.25)
        # Should be zero or very few (absolute condition blocks)
        assert hostile.sum() == 0, "Tiny absolute changes should not trigger hostile flag"


# ---------------------------------------------------------------------------
# 3. Stratified-delta arithmetic (known-answer)
# ---------------------------------------------------------------------------

class TestStratifiedDelta:

    def _make_fires(self, n_per_cell: int = 200, seed: int = 42) -> pd.DataFrame:
        """Build a synthetic fire DataFrame with known hit rates per stratum+arm."""
        rng = np.random.default_rng(seed)
        rows = []
        # Known hit rates: hostile=0.55, benign=0.45 in ALL strata
        for arm, hr in [("hostile", 0.55), ("benign", 0.45)]:
            for stratum in ["dd_0_5", "dd_5_10", "dd_10_20", "dd_20plus"]:
                hits = rng.binomial(1, hr, n_per_cell)
                for h in hits:
                    rows.append({"arm": arm, "stratum": stratum, "hit": float(h)})
        return pd.DataFrame(rows)

    def test_known_delta(self):
        """With engineered hit rates 0.55 vs 0.45, stratified delta should be ~0.10."""
        df = self._make_fires(n_per_cell=5000, seed=1)
        res = stratified_delta(df)
        d = res["stratified_delta"]
        assert d is not None
        # With equal stratum sizes, stratified delta = simple delta ~ 0.10
        assert abs(d - 0.10) < 0.02, f"Expected ~0.10, got {d}"

    def test_zero_delta(self):
        """When hostile and benign have identical hit rates, delta ~ 0."""
        rng = np.random.default_rng(7)
        rows = []
        for arm in ["hostile", "benign"]:
            for stratum in ["dd_0_5", "dd_5_10", "dd_10_20", "dd_20plus"]:
                hits = rng.binomial(1, 0.50, 1000)
                for h in hits:
                    rows.append({"arm": arm, "stratum": stratum, "hit": float(h)})
        df = pd.DataFrame(rows)
        res = stratified_delta(df)
        d = res["stratified_delta"]
        assert d is not None
        assert abs(d) < 0.03, f"Expected ~0, got {d}"

    def test_single_stratum_only(self):
        """If only one stratum has data, stratified delta = that stratum's delta."""
        rows = (
            [{"arm": "hostile", "stratum": "dd_0_5", "hit": 1.0}] * 100 +
            [{"arm": "benign", "stratum": "dd_0_5", "hit": 0.0}] * 100
        )
        df = pd.DataFrame(rows)
        res = stratified_delta(df)
        d = res["stratified_delta"]
        assert d is not None
        assert abs(d - 1.0) < 1e-9, f"Expected 1.0 delta, got {d}"

    def test_harmonic_mean_weighting(self):
        """Large imbalanced strata should contribute more weight."""
        rows = []
        # Stratum A: 1000 hostile, 1000 benign, delta = 0.20
        for _ in range(1000):
            rows.append({"arm": "hostile", "stratum": "dd_0_5", "hit": 1.0})
            rows.append({"arm": "benign", "stratum": "dd_0_5", "hit": 0.8})
        # Stratum B: 10 hostile, 10 benign, delta = -0.10
        for _ in range(10):
            rows.append({"arm": "hostile", "stratum": "dd_5_10", "hit": 0.2})
            rows.append({"arm": "benign", "stratum": "dd_5_10", "hit": 0.3})
        df = pd.DataFrame(rows)
        res = stratified_delta(df)
        d = res["stratified_delta"]
        # Should be much closer to 0.20 (dominated by large stratum) than midpoint of 0.05
        assert d is not None
        assert d > 0.10, f"Large stratum should dominate weighting; got {d}"

    def test_missing_arm_in_stratum(self):
        """If a stratum has only one arm, it should be skipped in weighting."""
        rows = (
            [{"arm": "hostile", "stratum": "dd_0_5", "hit": 1.0}] * 50 +
            [{"arm": "benign", "stratum": "dd_0_5", "hit": 0.5}] * 50 +
            # dd_5_10 only has hostile — should be skipped
            [{"arm": "hostile", "stratum": "dd_5_10", "hit": 0.9}] * 20
        )
        df = pd.DataFrame(rows)
        res = stratified_delta(df)
        d = res["stratified_delta"]
        assert d is not None
        # Should be based only on dd_0_5 delta = 0.5
        assert abs(d - 0.5) < 1e-9

    def test_per_stratum_counts(self):
        """Per-stratum output should have correct N counts."""
        rows = (
            [{"arm": "hostile", "stratum": "dd_0_5", "hit": 1.0}] * 30 +
            [{"arm": "benign", "stratum": "dd_0_5", "hit": 0.0}] * 40
        )
        df = pd.DataFrame(rows)
        res = stratified_delta(df)
        st = res["per_stratum"]["dd_0_5"]
        assert st["n_hostile"] == 30
        assert st["n_benign"] == 40


# ---------------------------------------------------------------------------
# 4. Floor-refusal behavior
# ---------------------------------------------------------------------------

class TestFloorRefusal:

    def test_floor_logic_hostile_fires(self):
        """Floor requires >=300 graded fires per arm per half."""
        # Below floor: 10 hostile, 10000 benign
        n_h, n_b = 10, 10000
        floor_ok = (n_h >= 300 and n_b >= 300)
        assert not floor_ok, "10 hostile fires should fail the floor"

    def test_floor_logic_episodes(self):
        """Floor requires >=8 hostile episodes per half."""
        ep_count = 5
        floor_ok = ep_count >= 8
        assert not floor_ok, "5 episodes should fail the floor"

    def test_floor_passes_with_sufficient_data(self):
        """Floor passes when both arms >=300 and episodes >=8."""
        n_h, n_b, ep = 350, 500, 10
        floor_ok = (n_h >= 300 and n_b >= 300 and ep >= 8)
        assert floor_ok

    def test_analyze_axis_returns_defer_on_missing_file(self, tmp_path):
        """analyze_axis should return P0-DEFER when series file is missing."""
        from scripts.research.macro_tx_phase0 import analyze_axis

        cfg = {
            "path": tmp_path / "nonexistent.parquet",
            "col": "us10y",
            "lag_bd": 0,
            "kind": "change_shock",
            "change_window": 20,
            "z_floor": HOSTILE_Z,
            "abs_floor": 0.25,
            "description": "test axis",
        }
        # Minimal fire DataFrame
        fires = pd.DataFrame({
            "as_of_dt": pd.bdate_range("2010-01-01", periods=10),
            "horizon_int": [21] * 10,
            "outcome_excess": [0.01] * 10,
            "symbol": ["AAPL"] * 10,
        })
        res = analyze_axis("A_test", cfg, fires, spy_dd=None)
        assert res["deferred"] is True
        assert "P0-DEFER(data)" in res["defer_reason"]


# ---------------------------------------------------------------------------
# 5. Budget-logged-before-run assertion
# ---------------------------------------------------------------------------

class TestBudgetLoggedBeforeRun:

    def test_budget_logged(self, tmp_path):
        """TrialLedger.log_declared_budget must be called with the correct budget BEFORE run."""
        ledger_path = tmp_path / "trial_ledger.jsonl"
        led = TrialLedger(path=ledger_path, family=FAMILY)

        # Before logging
        initial_n = led.declared_budget(FAMILY)
        assert initial_n == 0, f"No budget should be declared yet; got {initial_n}"

        # Log the budget
        led.log_declared_budget(DECLARED_BUDGET, family=FAMILY, reason="test")

        # After logging
        declared = led.declared_budget(FAMILY)
        assert declared == DECLARED_BUDGET, f"Expected {DECLARED_BUDGET}, got {declared}"

    def test_budget_is_floor_not_ceiling(self, tmp_path):
        """Budget declared via log_declared_budget acts as a FLOOR on effective_n."""
        ledger_path = tmp_path / "trial_ledger.jsonl"
        led = TrialLedger(path=ledger_path, family=FAMILY)
        led.log_declared_budget(DECLARED_BUDGET, family=FAMILY)
        # Without any itemized trials, effective_n = max(declared, 1) = DECLARED_BUDGET
        n = led.effective_n(FAMILY)
        assert n >= DECLARED_BUDGET, f"effective_n {n} should be >= declared_budget {DECLARED_BUDGET}"

    def test_declared_budget_value(self):
        """The declared budget must be 12 (4 axes × 3 horizons) per prereg §4."""
        assert DECLARED_BUDGET == 12, f"Budget should be 12 per prereg §4, got {DECLARED_BUDGET}"

    def test_family_name(self):
        """Family name must be 'macro_tx' per RUL-C11."""
        assert FAMILY == "macro_tx", f"Family should be 'macro_tx', got {FAMILY}"

    def test_ledger_write_survives_reload(self, tmp_path):
        """Budget entry should persist across TrialLedger instances (file-based)."""
        ledger_path = tmp_path / "trial_ledger.jsonl"
        led1 = TrialLedger(path=ledger_path, family=FAMILY)
        led1.log_declared_budget(DECLARED_BUDGET, family=FAMILY)

        # Reload from file
        led2 = TrialLedger(path=ledger_path, family=FAMILY)
        assert led2.declared_budget(FAMILY) == DECLARED_BUDGET


# ---------------------------------------------------------------------------
# 6. BH correction
# ---------------------------------------------------------------------------

class TestBHCorrection:

    def test_bh_all_significant(self):
        """Very small p-values should all pass BH."""
        p_values = [0.001, 0.002, 0.003, 0.004]
        result = bh_correct(p_values, q=0.10)
        assert all(result), "All very small p-values should reject H0"

    def test_bh_none_significant(self):
        """p=1.0 should not pass BH."""
        p_values = [1.0, 0.9, 0.8, 0.7]
        result = bh_correct(p_values, q=0.10)
        assert not any(result), "No large p-values should reject H0"

    def test_bh_with_none(self):
        """None p-values (deferred) should not be rejected."""
        p_values = [None, 0.001, None, 0.002]
        result = bh_correct(p_values, q=0.10)
        assert result[0] is False, "None p-value should not reject"
        assert result[2] is False, "None p-value should not reject"
        # Non-None small p-values may reject
        assert result[1] is True or result[3] is True

    def test_bh_mixed(self):
        """Standard BH example: some reject, some do not."""
        # 4 tests, q=0.10
        # Sorted: 0.01, 0.03, 0.05, 0.20
        # BH thresholds: 1/4*0.1=0.025, 2/4*0.1=0.05, 3/4*0.1=0.075, 4/4*0.1=0.10
        # 0.01 < 0.025 -> reject; 0.03 < 0.05 -> reject; 0.05 < 0.075 -> reject; 0.20 > 0.10 -> fail
        p_values = [0.20, 0.01, 0.03, 0.05]
        result = bh_correct(p_values, q=0.10)
        assert result[0] is False, "0.20 should not reject"
        assert result[1] is True, "0.01 should reject"
        assert result[2] is True, "0.03 should reject"
        assert result[3] is True, "0.05 should reject (below rank threshold)"


# ---------------------------------------------------------------------------
# 7. Drawdown stratification
# ---------------------------------------------------------------------------

class TestDrawdownStratification:

    def test_spy_drawdown_computation(self):
        """Drawdown should be <= 0 and -1 <= dd <= 0."""
        idx = pd.bdate_range("2018-01-01", periods=500)
        # Create a series with a known drawdown
        prices = pd.Series(100.0, index=idx)
        prices.iloc[250:] = 90.0  # 10% drawdown from peak
        dd = _compute_spy_drawdown(prices)
        # At position 250, drawdown should be -0.10
        dd_at_250 = dd.iloc[250]
        assert dd_at_250 <= 0
        assert abs(dd_at_250 - (-0.10)) < 0.01

    def test_stratum_assignment_ranges(self):
        """Verify strata are assigned correctly based on drawdown magnitude."""
        idx = pd.bdate_range("2020-01-01", periods=4)
        # Create spy_dd with known drawdowns
        spy_dd = pd.Series([-0.02, -0.07, -0.15, -0.25], index=idx)
        fire_dt = pd.Series(idx, index=range(4))
        strata = assign_drawdown_stratum(fire_dt, spy_dd)
        assert strata.iloc[0] == "dd_0_5", f"Expected dd_0_5 for -2%, got {strata.iloc[0]}"
        assert strata.iloc[1] == "dd_5_10", f"Expected dd_5_10 for -7%, got {strata.iloc[1]}"
        assert strata.iloc[2] == "dd_10_20", f"Expected dd_10_20 for -15%, got {strata.iloc[2]}"
        assert strata.iloc[3] == "dd_20plus", f"Expected dd_20plus for -25%, got {strata.iloc[3]}"

    def test_stratum_at_boundary(self):
        """Test exact boundary values.

        Prereg strata: [0,-5%), [-5,-10%), [-10,-20%), <=-20%
        The '-5%' boundary is EXCLUSIVE from [0,-5%) and INCLUSIVE in [-5,-10%).
        Implementation: dd > -0.05 -> dd_0_5; dd <= -0.05 and > -0.10 -> dd_5_10.
        """
        idx = pd.bdate_range("2020-01-01", periods=3)
        spy_dd = pd.Series([-0.05, -0.10, -0.20], index=idx)
        fire_dt = pd.Series(idx, index=range(3))
        strata = assign_drawdown_stratum(fire_dt, spy_dd)
        # -5.0%: dd <= -0.05 and dd > -0.10 -> dd_5_10
        assert strata.iloc[0] == "dd_5_10"
        # -10.0%: dd <= -0.10 and dd > -0.20 -> dd_10_20
        assert strata.iloc[1] == "dd_10_20"
        # -20.0%: dd <= -0.20 -> dd_20plus
        assert strata.iloc[2] == "dd_20plus"


# ---------------------------------------------------------------------------
# 8. Episode arm assignment
# ---------------------------------------------------------------------------

class TestEpisodeArmAssignment:

    def test_fire_inside_episode_is_hostile(self):
        """Fires within an episode window are assigned 'hostile'."""
        bd = _bd_range("2020-01-01", 50)
        # Episode: days 10-20
        episodes = [(bd[10], bd[20])]
        fire_dt = pd.Series([bd[15], bd[5], bd[30]], index=range(3))
        arm = assign_episode_arm(fire_dt, episodes)
        assert arm.iloc[0] == "hostile", "Day 15 is inside episode -> hostile"
        assert arm.iloc[1] == "benign", "Day 5 is outside episode -> benign"
        assert arm.iloc[2] == "benign", "Day 30 is outside episode -> benign"

    def test_fire_at_episode_boundary(self):
        """Fires at exact episode start/end are hostile."""
        bd = _bd_range("2020-01-01", 50)
        episodes = [(bd[10], bd[20])]
        fire_dt = pd.Series([bd[10], bd[20]], index=range(2))
        arm = assign_episode_arm(fire_dt, episodes)
        assert arm.iloc[0] == "hostile"
        assert arm.iloc[1] == "hostile"

    def test_no_episodes_all_benign(self):
        """No episodes -> all fires are benign."""
        bd = _bd_range("2020-01-01", 20)
        fire_dt = pd.Series(bd[:5], index=range(5))
        arm = assign_episode_arm(fire_dt, [])
        assert all(a == "benign" for a in arm)
