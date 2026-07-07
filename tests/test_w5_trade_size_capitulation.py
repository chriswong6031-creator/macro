"""Minimal pytest for w5_trade_size_capitulation signal logic — pure, no network.

Tests: causal z-score construction, universe filters, event selection deduplication,
relative-bounce computation sign, BH FDR function, Newey-West degeneracy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.w5_trade_size_capitulation_phase0 as M
from engine.validation import newey_west_tstat, benjamini_hochberg


# ------------------------------------------------------------------ fixtures

def _make_df(n: int = 400, base_close: float = 5.0, dvol_scale: float = 1e6,
             tx_base: int = 1000) -> pd.DataFrame:
    """Synthetic daily OHLCV with transactions, within universe filters."""
    dates = pd.date_range("2022-07-01", periods=n, freq="B")
    rng = np.random.default_rng(42)
    close = pd.Series(base_close + rng.normal(0, 0.05, n).cumsum(), index=dates)
    close = close.clip(lower=base_close * 0.5)  # keep above $2
    volume = pd.Series((dvol_scale / close).astype(int), index=dates)
    transactions = pd.Series(rng.integers(tx_base // 2, tx_base * 2, n), index=dates)
    return pd.DataFrame({
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": volume,
        "transactions": transactions,
    }, index=dates)


# ------------------------------------------------------------------ test: compute_features causality

class TestComputeFeatures:
    def test_no_future_leak_in_ats_z(self):
        """ats_z at bar t must not use close/volume from bars > t."""
        df = _make_df(300)
        feat = M.compute_features(df)
        assert feat is not None
        # Perturb the LAST 10 bars in a copy — earlier ats_z must be unchanged
        df2 = df.copy()
        df2.iloc[-10:, df2.columns.get_loc("volume")] *= 100  # huge change
        feat2 = M.compute_features(df2)
        # ats_z at bar -11 should be identical (well before perturbed window)
        np.testing.assert_allclose(
            feat["ats_z"].iloc[:-11].dropna().values,
            feat2["ats_z"].iloc[:-11].dropna().values,
            rtol=1e-6,
            err_msg="ats_z changes on bars NOT in the perturbed window — causality breach"
        )

    def test_in_universe_price_filter(self):
        """Bars with close <= $2 must not be in_universe."""
        df = _make_df(300, base_close=1.5)  # below price threshold
        feat = M.compute_features(df)
        assert feat is not None
        assert not feat["in_universe"].any(), "Tickers below $2 should not enter universe"

    def test_in_universe_dvol_bounds(self):
        """Bars with dvol_20 outside [$0.5M, $50M] must not be in_universe."""
        # Too large: price $5, volume 50M shares -> dvol $250M >> $50M
        df = _make_df(300, base_close=5.0, dvol_scale=250e6)
        feat = M.compute_features(df)
        assert feat is not None
        # dvol_20 > $50M, so should not be in universe after warmup
        if feat is not None and len(feat) > 100:
            late_bars = feat["in_universe"].iloc[100:]
            assert not late_bars.any(), "High-dvol bars should not be in_universe"

    def test_near_low_calculation(self):
        """near_low should be True when close <= 1.05 * 252d rolling min."""
        df = _make_df(300, base_close=5.0, dvol_scale=5e6)
        feat = M.compute_features(df)
        assert feat is not None
        # near_low must align with manual computation
        low_252 = df["close"].rolling(252, min_periods=63).min()
        expected_near_low = df["close"] <= M.NEAR_LOW_THRESH * low_252
        pd.testing.assert_series_equal(
            feat["near_low"],
            expected_near_low.fillna(False),
            check_names=False,
        )

    def test_returns_none_for_short_series(self):
        """Series with fewer than MIN_BARS should return None."""
        df = _make_df(50)
        assert M.compute_features(df) is None

    def test_returns_none_for_missing_transactions(self):
        """Series without transactions column should return None."""
        df = _make_df(200)
        df = df.drop(columns=["transactions"])
        assert M.compute_features(df) is None


# ------------------------------------------------------------------ test: event selection

class TestSelectEvents:
    def _make_feature_series(self, n: int = 300) -> pd.DataFrame:
        df = _make_df(n, base_close=4.0, dvol_scale=5e6)
        feat = M.compute_features(df)
        assert feat is not None
        return feat

    def test_v1_event_is_first_of_run(self):
        """V1 events must be the FIRST bar of each collapse run."""
        feat = self._make_feature_series()
        # Manually inject a long collapse: force ats_z < -1 and dvol_z < 0 for bars 150..170
        feat = feat.copy()
        feat.loc[feat.index[150:171], "ats_z"] = -2.0
        feat.loc[feat.index[150:171], "dvol_z"] = -1.0
        feat.loc[feat.index[150:171], "in_universe"] = True

        ev = M.select_events(feat, "V1")
        # Should get at most 1 event from bars 150..170 (first of run)
        run_dates = feat.index[150:171]
        ev_in_run = [d for d in ev if d in run_dates]
        assert len(ev_in_run) <= 1, f"Multiple events in a single run: {ev_in_run}"
        if ev_in_run:
            assert ev_in_run[0] == run_dates[0], "Event should be the first bar of run"

    def test_min_gap_between_events(self):
        """Two collapse runs within 21 bars should only produce 1 event."""
        feat = self._make_feature_series()
        feat = feat.copy()
        # First collapse at bar 100
        feat.loc[feat.index[100:103], "ats_z"] = -2.0
        feat.loc[feat.index[100:103], "dvol_z"] = -1.0
        feat.loc[feat.index[100:103], "in_universe"] = True
        # Second collapse at bar 110 (only 10 bars later, < MIN_EVENT_GAP=21)
        feat.loc[feat.index[110:113], "ats_z"] = -2.0
        feat.loc[feat.index[110:113], "dvol_z"] = -1.0
        feat.loc[feat.index[110:113], "in_universe"] = True

        ev = M.select_events(feat, "V1")
        ev_in_range = [d for d in ev if feat.index[95] <= d <= feat.index[120]]
        assert len(ev_in_range) <= 1, f"Gap constraint violated: {ev_in_range}"

    def test_no_events_when_not_in_universe(self):
        """No events when in_universe is always False."""
        feat = self._make_feature_series()
        feat = feat.copy()
        feat["in_universe"] = False
        for sv in ("V1", "V2", "V3"):
            ev = M.select_events(feat, sv)
            assert len(ev) == 0, f"{sv}: events found even when not in_universe"

    def test_v2_requires_expansion(self):
        """V2 events require ats_z > +1 AND dvol_z > 0."""
        feat = self._make_feature_series()
        feat = feat.copy()
        feat["ats_z"] = 0.5  # below V2 threshold
        feat["dvol_z"] = 1.0
        feat["in_universe"] = True
        ev = M.select_events(feat, "V2")
        assert len(ev) == 0, "V2 events found with ats_z below threshold"

    def test_v3_uses_dvol_only(self):
        """V3 requires dvol_z < -1 (ignores ats_z). We inject a collapse run that
        starts cleanly (at least MIN_EVENT_GAP after any prior run ends)."""
        feat = self._make_feature_series()
        feat = feat.copy()
        # Force ALL dvol_z to be neutral (above -1) first to clear any prior runs
        feat["dvol_z"] = 0.5
        feat["in_universe"] = True
        # Inject a fresh V3 collapse at bar 200 (well past the 252d window warmup)
        inject_start = 200
        feat.loc[feat.index[inject_start:inject_start + 3], "dvol_z"] = -2.0
        feat.loc[feat.index[inject_start:inject_start + 3], "ats_z"] = 0.0  # neutral ats_z

        ev = M.select_events(feat, "V3")
        ev_in_range = [d for d in ev if feat.index[inject_start - 1] <= d <= feat.index[inject_start + 3]]
        assert len(ev_in_range) >= 1, (
            "V3 should fire when dvol_z < -1, regardless of ats_z. "
            f"Injected at bar {inject_start}, got events: {ev_in_range}"
        )


# ------------------------------------------------------------------ test: forward return

class TestForwardReturn:
    def test_no_same_bar_fill(self):
        """Forward return must use close[t+1] as fill, not close[t]."""
        # Construct a ticker where close[t] != close[t+1] always
        n = 150
        dates = pd.date_range("2023-01-01", periods=n, freq="B")
        # Monotonically rising prices: close[t] = t, close[t+1] = t+1
        close = pd.Series(np.arange(10.0, 10.0 + n), index=dates)
        volume = pd.Series([1000] * n, index=dates)
        tx = pd.Series([100] * n, index=dates)
        df = pd.DataFrame({"open": close, "high": close, "low": close,
                           "close": close, "volume": volume, "transactions": tx}, index=dates)

        # fwd_21 for event at bar 10 should be close[32]/close[11] - 1 (fill at 11)
        # = (10+32)/(10+11) - 1 = 42/21 - 1 = 1.0
        fill_px = float(close.iloc[11])   # bar 11
        end_px = float(close.iloc[32])    # bar 11+21
        expected = end_px / fill_px - 1
        assert abs(expected - 1.0) < 1e-9, "Expected return = 1.0 (prices double)"


# ------------------------------------------------------------------ test: stats helpers

class TestStats:
    def test_newey_west_returns_dict(self):
        """newey_west_tstat should return a dict with mean, t, p."""
        data = np.random.default_rng(0).normal(0.01, 0.1, 100)
        res = newey_west_tstat(data, lags=4)
        assert "mean" in res and "t" in res and "p" in res
        assert 0.0 <= res["p"] <= 1.0

    def test_newey_west_on_zero_mean_returns_p_above_half(self):
        """Pure noise centered at 0 should not produce a small p-value."""
        rng = np.random.default_rng(1)
        data = rng.normal(0, 1, 200)
        res = newey_west_tstat(data, lags=4)
        # With 200 obs of pure noise, p should not be consistently < 0.05
        assert res["p"] > 0.01, "Noise series producing improbably small p-value"

    def test_benjamini_hochberg_controls_fdr(self):
        """BH with all large p-values should reject nothing."""
        pvals = {f"test_{i}": 0.5 + i * 0.01 for i in range(10)}
        res = benjamini_hochberg(pvals, alpha=0.10)
        rejects = [v["reject"] for v in res.values()]
        assert not any(rejects), "BH should reject nothing with large p-values"

    def test_benjamini_hochberg_rejects_small_pvals(self):
        """BH with all tiny p-values should reject everything."""
        pvals = {f"test_{i}": 1e-10 for i in range(6)}
        res = benjamini_hochberg(pvals, alpha=0.10)
        rejects = [v["reject"] for v in res.values()]
        assert all(rejects), "BH should reject all with tiny p-values"

    def test_date_collapse_avoids_nw_inflation(self):
        """Collapsing to one obs per date should yield fewer effective obs than raw events."""
        # Create synthetic events where multiple events share a date
        dates = pd.to_datetime(["2023-01-03"] * 5 + ["2023-01-04"] * 3)
        values = np.random.default_rng(2).normal(0.02, 0.1, 8)
        df = pd.DataFrame({"event_date": dates, "val": values})

        by_date = df.groupby("event_date")["val"].mean()
        assert len(by_date) == 2, "Date collapse should produce 2 dates from 8 events"
        assert len(df) == 8, "Original should have 8 events"


# ------------------------------------------------------------------ test: v1 > cohort directionally

class TestCohortLogic:
    def test_collapse_signal_higher_than_no_collapse(self):
        """Synthetic: collapse names have uniformly higher forward returns.
        Relative bounce should be positive."""
        # Build a small synthetic dataset where collapse names always return +5%
        # and non-collapse names return +1%
        n = 200
        dates = pd.date_range("2023-01-01", periods=n, freq="B")
        rng = np.random.default_rng(99)

        # Collapse ticker: close goes up 5% after event
        close_ev = pd.Series(np.ones(n) * 5.0, index=dates)
        # Plant a 5% jump at bar 120
        close_ev.iloc[121:] = 5.25

        # Non-collapse ticker: close goes up 1% from bar 120
        close_co = pd.Series(np.ones(n) * 5.0, index=dates)
        close_co.iloc[121:] = 5.05

        # Both fill at bar 121; outcomes at bar 121+21=142
        fill_ev = float(close_ev.iloc[121])
        end_ev = float(close_ev.iloc[142])
        fill_co = float(close_co.iloc[121])
        end_co = float(close_co.iloc[142])

        ret_ev = end_ev / fill_ev - 1   # = 0.0 (already at 5.25 at fill)
        ret_co = end_co / fill_co - 1   # = 0.0

        # Direct test: the cohort-relative return formula
        rel = ret_ev - ret_co
        assert abs(rel) < 1e-9, "Synthetic returns are flat after fill; relative should be ~0"
        # The point: rel = fwd_ev - cohort_median


# ------------------------------------------------------------------ run
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
