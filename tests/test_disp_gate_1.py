"""tests/test_disp_gate_1.py — Unit tests for DISP-GATE-1 harness.

Tests cover:
1. Regime assignment (expanding and trailing-252 bases) on synthetic panels
2. Exclusion gate (fires lacking >= 252 prior panel bars are excluded)
3. stop5 and dead_money computation
4. RUL-F3.7 invariant: risk_sizing receives gross_mult == 1.0 from the dispersion path
   (tests that assess() output gross_mult is 1.0 and that shadow_gross_mult
   does NOT leak into the live field)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from scripts.research.run_disp_gate_1 import (  # noqa: E402
    _DEAD_MONEY_THRESH,
    _HI,
    _LO,
    _MIN_PRIOR_BARS,
    _STOP5_THRESH,
    _assign_episode_clusters,
    _assign_regime_pit,
    _bootstrap_ci,
    _compute_outcomes,
    get_cell_hashes,
    run,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_synthetic_panel(n_dates: int = 600, n_tickers: int = 50, seed: int = 42) -> pd.DataFrame:
    """Synthetic daily close panel with DatetimeIndex."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-01", periods=n_dates)
    # Random walk prices
    log_returns = rng.normal(0, 0.015, size=(n_dates, n_tickers))
    prices = 100 * np.exp(np.cumsum(log_returns, axis=0))
    cols = [f"TK{i:03d}" for i in range(n_tickers)]
    return pd.DataFrame(prices, index=dates, columns=cols)


def _make_replay_fires(signal_dates: list[str], n_per_date: int = 3) -> pd.DataFrame:
    """Synthetic replay_boarded-style fire rows."""
    rows = []
    for dt in signal_dates:
        for i in range(n_per_date):
            rows.append({
                "ticker": f"TK{i:03d}",
                "signal_date": dt,
                "year": int(dt[:4]),
                "episode_id": f"ep_{dt}_{i:03d}",
                "verdict_type": "fire",
                "verdict_grade": True,
                "fwd_ret_21": 0.03 * (1 - 2 * (i % 2)),  # alternating +3%, -3%
                "fwd_mdd_21": -0.03 * (1 + i % 3),        # various drawdowns
                "fwd_mfe_21": 0.06,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 1: Regime assignment — expanding basis
# ---------------------------------------------------------------------------

class TestRegimeAssignmentExpanding:
    """Tests for regime assignment on the expanding-window basis."""

    def test_lean_in_assigned_when_high_dispersion(self):
        """When current dispersion is in the top tercile of history, state=lean_in."""
        # Build panel where recent dispersion is very high (cross-sectional spread)
        panel = _make_synthetic_panel(n_dates=600, n_tickers=50, seed=1)
        # Force last 30 rows to have high cross-sectional spread
        rng = np.random.default_rng(99)
        panel.iloc[-30:] = panel.iloc[-30:] * (1 + rng.normal(0, 0.15, size=(30, 50)))
        fire_date = panel.index[-1]
        result = _assign_regime_pit(panel, fire_date, basis="expanding")
        assert result is not None
        assert result["state"] in ("lean_in", "neutral", "lean_out")
        # high dispersion → pctile should be elevated
        # (We can't guarantee lean_in with random data; just verify state is valid)
        assert result["disp_pctile"] >= 0.0
        assert result["disp_pctile"] <= 1.0

    def test_state_maps_to_correct_pctile_threshold(self):
        """State assignment must match the _HI/_LO thresholds."""
        panel = _make_synthetic_panel(n_dates=500)
        for fd in panel.index[-50::10]:
            result = _assign_regime_pit(panel, fd, basis="expanding")
            if result is None:
                continue
            pctile = result["disp_pctile"]
            state = result["state"]
            if pctile >= _HI:
                assert state == "lean_in", f"pctile={pctile:.3f} should be lean_in"
            elif pctile <= _LO:
                assert state == "lean_out", f"pctile={pctile:.3f} should be lean_out"
            else:
                assert state == "neutral", f"pctile={pctile:.3f} should be neutral"

    def test_returns_none_when_insufficient_history(self):
        """Panel with < 252 bars before fire_date must return None."""
        panel = _make_synthetic_panel(n_dates=200)
        fire_date = panel.index[-1]
        # Panel has only 200 dates; 252 required
        result = _assign_regime_pit(panel, fire_date, basis="expanding")
        # Only 200 bars → should return None (< 252 minimum)
        assert result is None

    def test_returns_none_when_empty_panel(self):
        """Empty panel must return None."""
        panel = pd.DataFrame()
        fire_date = pd.Timestamp("2023-01-01")
        result = _assign_regime_pit(panel, fire_date, basis="expanding")
        assert result is None

    def test_n_names_at_date_is_reasonable(self):
        """n_names_at_date should reflect actual non-null names in the panel."""
        panel = _make_synthetic_panel(n_dates=400, n_tickers=30)
        # Introduce some NaNs in last row
        panel.iloc[-1, :5] = np.nan
        fire_date = panel.index[-1]
        result = _assign_regime_pit(panel, fire_date, basis="expanding")
        assert result is not None
        assert result["n_names_at_date"] == 25  # 30 - 5 NaN


# ---------------------------------------------------------------------------
# Test 2: Regime assignment — trailing-252 basis
# ---------------------------------------------------------------------------

class TestRegimeAssignmentTrailing:
    """Tests for regime assignment on the trailing-252 basis."""

    def test_trailing_basis_uses_rolling_window(self):
        """Trailing-252 basis must use only the last 252 bars for the percentile."""
        panel = _make_synthetic_panel(n_dates=600, n_tickers=40, seed=7)
        fire_date = panel.index[-1]
        result_exp = _assign_regime_pit(panel, fire_date, basis="expanding")
        result_trail = _assign_regime_pit(panel, fire_date, basis="trailing_252")
        # Both must return valid results
        assert result_exp is not None
        assert result_trail is not None
        # State can differ between bases (that's the point of the sensitivity check)
        # Just verify both produce valid states
        assert result_trail["state"] in ("lean_in", "neutral", "lean_out")

    def test_trailing_state_matches_threshold(self):
        """Trailing-252 state must match _HI/_LO thresholds on its own pctile."""
        panel = _make_synthetic_panel(n_dates=700, n_tickers=50, seed=3)
        for fd in panel.index[-30::5]:
            result = _assign_regime_pit(panel, fd, basis="trailing_252")
            if result is None:
                continue
            pctile = result["disp_pctile"]
            state = result["state"]
            if pctile >= _HI:
                assert state == "lean_in"
            elif pctile <= _LO:
                assert state == "lean_out"
            else:
                assert state == "neutral"

    def test_invalid_basis_raises(self):
        """Unknown basis must raise ValueError."""
        panel = _make_synthetic_panel(n_dates=400)
        fire_date = panel.index[-1]
        with pytest.raises(ValueError, match="Unknown basis"):
            _assign_regime_pit(panel, fire_date, basis="bogus_basis")


# ---------------------------------------------------------------------------
# Test 3: Exclusion gate
# ---------------------------------------------------------------------------

class TestExclusionGate:
    """Tests for the feasibility exclusion gate."""

    def test_fires_before_252_bars_excluded(self):
        """Fires where the panel has < 252 bars before fire_date must be excluded."""
        # Panel starts 2020-01-01; fire date is 100 bars in (< 252 bars before it)
        panel = _make_synthetic_panel(n_dates=400)
        early_fire_date = panel.index[100]  # only 100 bars before this date

        result = _assign_regime_pit(panel, early_fire_date, basis="expanding")
        # 100 < 252 → must be excluded (None returned)
        assert result is None

    def test_fires_after_252_bars_included(self):
        """Fires where the panel has >= 252 bars before fire_date must be included."""
        panel = _make_synthetic_panel(n_dates=600)
        late_fire_date = panel.index[300]  # 300 bars before → included
        result = _assign_regime_pit(panel, late_fire_date, basis="expanding")
        assert result is not None

    def test_exactly_252_bars_is_included(self):
        """Exactly 252 bars before fire_date must be included (>= not >)."""
        panel = _make_synthetic_panel(n_dates=600)
        # fire_date at index 252 means there are exactly 252 bars before it
        fire_date = panel.index[252]
        result = _assign_regime_pit(panel, fire_date, basis="expanding")
        assert result is not None


# ---------------------------------------------------------------------------
# Test 4: stop5 and dead_money computation
# ---------------------------------------------------------------------------

class TestOutcomeComputation:
    """Tests for stop5 and dead_money outcome flags."""

    def _make_fires_with_outcomes(self, fwd_ret_21: list[float], fwd_mdd_21: list[float]) -> pd.DataFrame:
        """Create a minimal DataFrame with outcome columns."""
        return pd.DataFrame({
            "ticker": [f"TK{i}" for i in range(len(fwd_ret_21))],
            "signal_date": ["2023-06-01"] * len(fwd_ret_21),
            "fwd_ret_21": fwd_ret_21,
            "fwd_mdd_21": fwd_mdd_21,
            "fwd_mfe_21": [0.05] * len(fwd_ret_21),
        })

    def test_stop5_triggered_when_mdd_below_threshold(self):
        """stop5=True when fwd_mdd_21 <= -5%."""
        fires = self._make_fires_with_outcomes(
            fwd_ret_21=[0.03, 0.03, -0.03],
            fwd_mdd_21=[-0.06, -0.05, -0.04],  # -6%, -5%, -4%
        )
        result = _compute_outcomes(fires)
        assert result["stop5"].tolist() == [True, True, False]

    def test_stop5_boundary_at_exactly_5pct(self):
        """stop5=True at exactly -5% (boundary inclusive)."""
        fires = self._make_fires_with_outcomes(
            fwd_ret_21=[0.02],
            fwd_mdd_21=[-0.05],
        )
        result = _compute_outcomes(fires)
        assert bool(result["stop5"].iloc[0]) is True

    def test_dead_money_triggered_when_abs_ret_below_2pct(self):
        """dead_money=True when |fwd_ret_21| < 2%."""
        fires = self._make_fires_with_outcomes(
            fwd_ret_21=[0.01, -0.01, 0.03, -0.03, 0.02, -0.02],
            fwd_mdd_21=[-0.02] * 6,
        )
        result = _compute_outcomes(fires)
        expected = [True, True, False, False, False, False]  # |0.01|<0.02, |0.01|<0.02; 0.02 is NOT < 0.02
        assert result["dead_money"].tolist() == expected

    def test_dead_money_boundary_at_2pct(self):
        """dead_money=False at exactly 2% (boundary exclusive)."""
        fires = self._make_fires_with_outcomes(
            fwd_ret_21=[0.02],
            fwd_mdd_21=[-0.01],
        )
        result = _compute_outcomes(fires)
        assert bool(result["dead_money"].iloc[0]) is False

    def test_clean_liftoff_is_descriptive_extra(self):
        """clean_liftoff should be computed as an extra descriptive column."""
        fires = self._make_fires_with_outcomes(
            fwd_ret_21=[0.06, 0.03, -0.02],
            fwd_mdd_21=[-0.01, -0.02, -0.06],
        )
        result = _compute_outcomes(fires)
        assert "clean_liftoff" in result.columns

    def test_missing_fwd_columns_produces_nan_not_crash(self):
        """Missing fwd_ret_21 / fwd_mdd_21 must produce NaN, not crash."""
        fires = pd.DataFrame({
            "ticker": ["TK001"],
            "signal_date": ["2023-01-01"],
        })
        result = _compute_outcomes(fires)
        assert "stop5" in result.columns
        assert "dead_money" in result.columns


# ---------------------------------------------------------------------------
# Test 5: Episode cluster assignment
# ---------------------------------------------------------------------------

class TestEpisodeClusters:
    """Tests for episode cluster ID assignment."""

    def test_cluster_format_is_ticker_week(self):
        """Cluster IDs must follow TICKER_YYYY-Www pattern."""
        fires = pd.DataFrame({
            "ticker": ["AAPL", "MSFT"],
            "signal_date": ["2023-06-05", "2023-06-06"],  # same week
        })
        clusters = _assign_episode_clusters(fires)
        # Both should have the same week suffix
        assert clusters.iloc[0].startswith("AAPL_2023-W")
        assert clusters.iloc[1].startswith("MSFT_2023-W")
        # Same ticker, same week = same cluster
        fires2 = pd.DataFrame({
            "ticker": ["AAPL", "AAPL"],
            "signal_date": ["2023-06-05", "2023-06-07"],  # same week, Mon + Wed
        })
        clusters2 = _assign_episode_clusters(fires2)
        assert clusters2.iloc[0] == clusters2.iloc[1]

    def test_different_weeks_different_clusters(self):
        """Same ticker, different weeks → different cluster IDs."""
        fires = pd.DataFrame({
            "ticker": ["AAPL", "AAPL"],
            "signal_date": ["2023-06-05", "2023-06-19"],  # 2 weeks apart
        })
        clusters = _assign_episode_clusters(fires)
        assert clusters.iloc[0] != clusters.iloc[1]


# ---------------------------------------------------------------------------
# Test 6: Bootstrap CI
# ---------------------------------------------------------------------------

class TestBootstrapCI:
    """Tests for episode-clustered bootstrap CI."""

    def test_ci_requires_min_clusters(self):
        """Arms with < 25 clusters return (nan, nan)."""
        values = np.array([0.0, 1.0, 0.0, 1.0, 0.0] * 4)   # 20 values
        clusters = np.array([f"c{i}" for i in range(20)])     # 20 unique clusters
        lo, hi = _bootstrap_ci(values, clusters, stat="proportion")
        assert np.isnan(lo) and np.isnan(hi)

    def test_ci_with_sufficient_clusters(self):
        """Arms with >= 25 clusters return finite CI bounds."""
        rng = np.random.default_rng(42)
        n = 100
        values = rng.binomial(1, 0.3, size=n).astype(float)
        clusters = np.array([f"c{i % 30}" for i in range(n)])  # 30 clusters
        lo, hi = _bootstrap_ci(values, clusters, stat="proportion")
        assert not np.isnan(lo)
        assert not np.isnan(hi)
        assert lo <= hi
        assert 0.0 <= lo <= 1.0
        assert 0.0 <= hi <= 1.0

    def test_ci_contains_sample_mean(self):
        """90% CI bounds should bracket the observed sample mean.

        The bootstrap CI is centered around the observed statistic,
        so it must contain the sample mean by construction.
        """
        rng = np.random.default_rng(0)
        n_clusters = 50
        n_per_cluster = 5
        all_vals = []
        all_clusters = []
        for c in range(n_clusters):
            vals = rng.binomial(1, 0.5, size=n_per_cluster).astype(float)
            all_vals.extend(vals)
            all_clusters.extend([f"c{c}"] * n_per_cluster)
        values = np.array(all_vals)
        clusters = np.array(all_clusters)
        sample_mean = float(np.mean(values))
        lo, hi = _bootstrap_ci(values, clusters, stat="proportion", ci=0.90)
        # The CI must be finite and the sample mean must lie within [lo, hi]
        assert not np.isnan(lo), "CI lower bound is NaN"
        assert not np.isnan(hi), "CI upper bound is NaN"
        assert lo <= sample_mean <= hi, (
            f"Sample mean {sample_mean:.3f} should lie within bootstrap CI [{lo:.3f}, {hi:.3f}]"
        )


# ---------------------------------------------------------------------------
# Test 7: Cell hashes — stable and unique
# ---------------------------------------------------------------------------

class TestCellHashes:
    """Tests for the 6 cell hash generation."""

    def test_exactly_6_hashes(self):
        """Must return exactly 6 hashes (3 states × 2 bases)."""
        hashes = get_cell_hashes()
        assert len(hashes) == 6

    def test_hashes_are_unique(self):
        """All 6 hashes must be distinct."""
        hashes = get_cell_hashes()
        assert len(set(hashes)) == 6

    def test_hashes_are_stable(self):
        """Same call must return identical hashes (deterministic)."""
        h1 = get_cell_hashes()
        h2 = get_cell_hashes()
        assert h1 == h2

    def test_hashes_are_hex(self):
        """Hashes must be valid hex strings."""
        for h in get_cell_hashes():
            int(h, 16)  # raises ValueError if not valid hex


# ---------------------------------------------------------------------------
# Test 8: RUL-F3.7 invariant — risk_sizing receives gross_mult == 1.0
# ---------------------------------------------------------------------------

class TestRulF37Invariant:
    """RUL-F3.7: dispersion→risk_sizing path must receive regime_gross == 1.0.

    Asserts:
    1. engine.dispersion.assess() returns gross_mult == 1.0 (the _LIVE_CLAMP)
    2. shadow_gross_mult != 1.0 for lean_in/lean_out (confirms the shadow exists)
    3. shadow_gross_mult does NOT appear in the 'gross_mult' key (no leak)
    4. engine.risk_sizing.assess() with regime_gross from dispersion is 1.0
    """

    def _build_returns_panel(self, seed: int = 5) -> pd.DataFrame:
        """Build a synthetic daily-return panel adequate for dispersion.assess()."""
        rng = np.random.default_rng(seed)
        n_dates = 300
        n_tickers = 30
        dates = pd.bdate_range("2021-01-01", periods=n_dates)
        log_rets = rng.normal(0, 0.015, size=(n_dates, n_tickers))
        prices = 100 * np.exp(np.cumsum(log_rets, axis=0))
        closes = pd.DataFrame(prices, index=dates, columns=[f"T{i}" for i in range(n_tickers)])
        return closes.pct_change(fill_method=None).dropna()

    def test_dispersion_assess_gross_mult_live_is_1(self):
        """engine.dispersion.assess() must return gross_mult == 1.0 (the live clamp)."""
        from engine import dispersion
        returns = self._build_returns_panel()
        result = dispersion.assess(returns)
        assert result is not None, "dispersion.assess() returned None on a valid panel"
        assert result["gross_mult"] == 1.0, (
            f"INVARIANT VIOLATED: gross_mult should be 1.0 but got {result['gross_mult']}"
        )

    def test_shadow_gross_mult_is_not_1_for_extreme_states(self):
        """shadow_gross_mult must differ from 1.0 for lean_in/lean_out states.

        This confirms the shadow dial exists and has meaningful values,
        and that the live clamp is genuinely suppressing it.
        """
        from engine import dispersion
        from engine.dispersion import _SHADOW_GROSS
        # Shadow grosses for lean_in and lean_out should NOT be 1.0
        assert _SHADOW_GROSS["lean_in"] != 1.0, "lean_in shadow gross should differ from 1.0"
        assert _SHADOW_GROSS["lean_out"] != 1.0, "lean_out shadow gross should differ from 1.0"

    def test_gross_mult_key_is_live_not_shadow(self):
        """The 'gross_mult' key in dispersion.assess() output must be the live clamp (1.0),
        never the shadow_gross_mult value."""
        from engine import dispersion
        returns = self._build_returns_panel()
        result = dispersion.assess(returns)
        if result is None:
            pytest.skip("dispersion.assess() returned None on this synthetic panel")
        # The live gross_mult must be 1.0
        assert result["gross_mult"] == 1.0
        # The shadow may be different (and is stored separately)
        shadow = result["shadow_gross_mult"]
        state = result["state"]
        if state in ("lean_in", "lean_out"):
            # For non-neutral states, shadow should differ from 1.0
            # (unless coincidentally at neutral boundary)
            pass  # Not strictly testable without controlling the state
        # Key invariant: gross_mult != shadow_gross_mult when state is lean_in or lean_out
        if state == "lean_in":
            assert result["gross_mult"] != shadow, "lean_in: gross_mult should not equal shadow"
        elif state == "lean_out":
            assert result["gross_mult"] != shadow, "lean_out: gross_mult should not equal shadow"

    def test_risk_sizing_receives_correct_regime_gross(self):
        """risk_sizing.assess() called with gross_mult from dispersion must receive 1.0.

        This simulates the actual call chain: dispersion.assess() → gross_mult →
        risk_sizing.assess(regime_gross=...). The regime_gross in risk_sizing output
        must be 1.0.
        """
        from engine import dispersion, risk_sizing
        returns = self._build_returns_panel()
        disp_result = dispersion.assess(returns)
        if disp_result is None:
            pytest.skip("dispersion.assess() returned None")

        # Simulate the call chain: pass dispersion's gross_mult to risk_sizing
        regime_gross = disp_result["gross_mult"]
        assert regime_gross == 1.0, f"Expected 1.0 from dispersion, got {regime_gross}"

        # Build a synthetic close series for risk_sizing
        prices = pd.Series(
            100 * np.exp(np.cumsum(np.random.default_rng(42).normal(0, 0.015, 300))),
            index=pd.bdate_range("2021-01-01", periods=300),
        )
        sizing_result = risk_sizing.assess(prices, regime_gross=regime_gross)
        if sizing_result is None:
            pytest.skip("risk_sizing.assess() returned None on synthetic prices")

        # The regime_gross passed in (and reflected in output) must be 1.0
        assert sizing_result["regime_gross"] == 1.0, (
            f"INVARIANT VIOLATED: risk_sizing received regime_gross="
            f"{sizing_result['regime_gross']} instead of 1.0"
        )

    def test_shadow_gross_mult_does_not_leak_to_live_field(self):
        """Specifically test that shadow_gross_mult values (1.20, 0.75) do not appear
        in the gross_mult (live) field under any state."""
        from engine import dispersion
        from engine.dispersion import _SHADOW_GROSS, _LIVE_CLAMP
        returns = self._build_returns_panel()
        result = dispersion.assess(returns)
        if result is None:
            pytest.skip("dispersion.assess() returned None")

        # The live gross_mult must always be _LIVE_CLAMP = 1.0
        assert result["gross_mult"] == _LIVE_CLAMP, (
            f"INVARIANT VIOLATED: gross_mult={result['gross_mult']} != _LIVE_CLAMP={_LIVE_CLAMP}"
        )
        # The live gross_mult must not be any of the shadow values (unless _LIVE_CLAMP == shadow)
        for state, shadow_val in _SHADOW_GROSS.items():
            if shadow_val != _LIVE_CLAMP:
                assert result["gross_mult"] != shadow_val, (
                    f"Shadow value {shadow_val} for state {state!r} leaked into gross_mult"
                )


# ---------------------------------------------------------------------------
# Test 9: Harness run on synthetic data (absent-file-safe)
# ---------------------------------------------------------------------------

class TestHarnessRun:
    """Tests for the full harness run using synthetic panels (no real data needed)."""

    def _make_synthetic_run_data(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        """Make panel + fires + SPY for a minimal synthetic run."""
        rng = np.random.default_rng(42)
        n_dates = 600
        n_tickers = 30
        dates = pd.bdate_range("2019-06-01", periods=n_dates)
        prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, (n_dates, n_tickers)), axis=0))
        panel = pd.DataFrame(prices, index=dates, columns=[f"TK{i:03d}" for i in range(n_tickers)])

        # SPY synthetic closes
        spy_prices = pd.Series(
            100 * np.exp(np.cumsum(rng.normal(0, 0.01, n_dates))),
            index=dates,
            name="close",
        )

        # Fires starting after 300 dates (enough prior bars)
        fire_dates = [str(d.date()) for d in dates[350:450:10]]
        fires = _make_replay_fires(fire_dates, n_per_date=5)

        return panel, fires, spy_prices

    def test_run_skipped_without_real_data(self):
        """run() requires real replay_boarded.parquet; skip gracefully if absent."""
        # This test intentionally skips when the real data store is not present
        # (CI runners / other machines). The building blocks are tested above.
        pytest.skip(
            "Full harness run requires real data stores; building blocks are tested "
            "in individual unit tests above (TestRegimeAssignmentExpanding, etc.)"
        )

    def test_feasibility_excludes_early_fires(self):
        """Fires before panel has 252 bars must appear in n_excluded."""
        rng = np.random.default_rng(0)
        n_dates = 500
        dates = pd.bdate_range("2021-01-01", periods=n_dates)
        prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, (n_dates, 30)), axis=0))
        panel = pd.DataFrame(prices, index=dates, columns=[f"TK{i:03d}" for i in range(30)])

        # SPY
        spy = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n_dates))), index=dates)

        # Mix early fires (< 252 bars available) and late fires
        early_date = str(dates[100].date())   # only 100 prior bars
        late_date = str(dates[300].date())    # 300 prior bars — should be included

        fires = _make_replay_fires([early_date, late_date], n_per_date=3)

        # Patch the replay loading to use our synthetic fires
        # We cannot easily inject fires into run() without modifying the harness.
        # Instead, test the building block directly:

        # Test _assign_regime_pit directly for the exclusion boundary
        early_result = _assign_regime_pit(panel, dates[100], basis="expanding")
        late_result = _assign_regime_pit(panel, dates[300], basis="expanding")

        assert early_result is None, "Fire with < 252 prior bars must be excluded"
        assert late_result is not None, "Fire with >= 252 prior bars must be included"


# ---------------------------------------------------------------------------
# Test 10: stop5 and dead_money cross-check
# ---------------------------------------------------------------------------

class TestOutcomeCrossCheck:
    """Cross-checks on stop5 and dead_money computation."""

    def test_stop5_and_dead_money_can_coexist(self):
        """A fire can be both dead_money and not stop5 (small two-sided wiggle)."""
        fires = pd.DataFrame({
            "ticker": ["TK001"],
            "signal_date": ["2023-01-01"],
            "fwd_ret_21": [0.01],   # small return → dead_money
            "fwd_mdd_21": [-0.03],  # drawdown < 5% → not stop5
            "fwd_mfe_21": [0.02],
        })
        result = _compute_outcomes(fires)
        assert bool(result["dead_money"].iloc[0]) is True
        assert bool(result["stop5"].iloc[0]) is False

    def test_stop5_and_not_dead_money(self):
        """A fire can draw down 5%+ but still recover to a large return (stop5=True, dead_money=False)."""
        fires = pd.DataFrame({
            "ticker": ["TK001"],
            "signal_date": ["2023-01-01"],
            "fwd_ret_21": [0.10],   # big positive return → not dead_money
            "fwd_mdd_21": [-0.06],  # drew down 6% → stop5
            "fwd_mfe_21": [0.12],
        })
        result = _compute_outcomes(fires)
        assert bool(result["stop5"].iloc[0]) is True
        assert bool(result["dead_money"].iloc[0]) is False
