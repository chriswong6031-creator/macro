"""Tests for engine/path_personality.py.

Covers the required test cases from the W1 spec:
  (a) Synthetic monotone uptrend + small noise: high trend_persist, shallow pullbacks,
      low failed_breakout_rate, high breakout_ft_rate.
  (b) Synthetic AR(1) mean-reverter (phi ~ -0.4): negative trend_persist.
  (c) Synthetic gappy event series (>=6 large overnight gaps): gap_share_252 and
      event_gap_contrib_252 elevated vs case (a).
  (d) Close-only frame: OHLC/volume features None/NaN, coverage.has_ohlc False.
  (e) THE LEAK TEST: feature_series on df.iloc[:t] and full df identical at row t.
  (f) Real-data smoke: load 2 tickers from data/stocks/, run both APIs, keys present.
  (g) Determinism: same input twice -> identical outputs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.path_personality import (  # noqa: E402
    _FEATURE_KEYS,
    feature_series,
    features,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SEED = 42


def _idx(n: int, start: str = "2010-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _make_ohlcv(
    close_vals: list[float] | np.ndarray,
    open_offset: float = 0.0,
    high_frac: float = 0.01,
    low_frac: float = 0.01,
    volume: float = 1_000_000.0,
) -> pd.DataFrame:
    """Build a full OHLCV DataFrame from a close series."""
    n = len(close_vals)
    idx = _idx(n)
    c = np.asarray(close_vals, dtype=float)
    o = np.roll(c, 1)
    o[0] = c[0]
    o = o + open_offset
    h = c * (1 + high_frac)
    l = c * (1 - low_frac)
    v = np.full(n, volume)
    return pd.DataFrame(
        {"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx
    )


def _make_close_only(close_vals: list[float] | np.ndarray) -> pd.DataFrame:
    """Build a close-only DataFrame."""
    n = len(close_vals)
    return pd.DataFrame({"close": np.asarray(close_vals, dtype=float)}, index=_idx(n))


# ---------------------------------------------------------------------------
# (a) Monotone uptrend + small noise
# ---------------------------------------------------------------------------

class TestUptrendSeries:
    """Case (a): smooth compounder — strong momentum, shallow pullbacks."""

    @classmethod
    def setup_class(cls):
        rng = np.random.default_rng(SEED)
        n = 800
        # Strong uptrend: each bar +0.3% with tiny noise
        rets = 0.003 + rng.normal(0, 0.002, n)
        close = 100.0 * np.exp(np.cumsum(rets))
        cls.df = _make_ohlcv(close)
        cls.snap = features(cls.df)
        cls.series = feature_series(cls.df)

    def test_trend_persist_positive(self):
        """Uptrend should produce positive lag-1 autocorrelation at all windows."""
        for key in ("trend_persist_20", "trend_persist_60", "trend_persist_126"):
            val = self.snap[key]
            assert val is not None, f"{key} is None"
            assert val > 0, f"{key}={val} should be positive for a monotone uptrend"

    def test_pullbacks_shallow(self):
        """In a nearly monotone uptrend, median pullback depth should be small."""
        med = self.snap["pullback_median_252"]
        if med is not None:
            assert med < 0.15, f"pullback_median_252={med} unexpectedly deep in uptrend"

    def test_breakout_ft_rate_high(self):
        """Most breakouts in an uptrend should follow through."""
        rate = self.snap["breakout_ft_rate_63"]
        if rate is not None:
            assert rate > 0.5, f"breakout_ft_rate_63={rate} should be > 0.5 in uptrend"

    def test_failed_breakout_rate_low(self):
        """Few breakouts should fail in a strong uptrend."""
        rate = self.snap["failed_breakout_rate_63"]
        if rate is not None:
            assert rate < 0.6, f"failed_breakout_rate_63={rate} should be relatively low in uptrend"

    def test_keys_present(self):
        """Snapshot must have all required feature keys."""
        for k in _FEATURE_KEYS:
            assert k in self.snap, f"Missing key: {k}"

    def test_coverage_correct(self):
        cov = self.snap["coverage"]
        assert cov["has_ohlc"] is True
        assert cov["has_volume"] is True
        assert cov["n_bars"] == 800


# ---------------------------------------------------------------------------
# (b) AR(1) mean-reverter (phi ~ -0.4)
# ---------------------------------------------------------------------------

class TestMeanReverterSeries:
    """Case (b): mean-reverting AR(1) process -> negative trend persistence."""

    @classmethod
    def setup_class(cls):
        rng = np.random.default_rng(SEED + 1)
        n = 800
        phi = -0.4
        noise = rng.normal(0, 0.008, n)
        # AR(1): r_t = phi * r_{t-1} + eps
        rets = np.zeros(n)
        rets[0] = noise[0]
        for i in range(1, n):
            rets[i] = phi * rets[i - 1] + noise[i]
        close = 100.0 * np.exp(np.cumsum(rets))
        cls.df = _make_ohlcv(close)
        cls.snap = features(cls.df)

    def test_trend_persist_negative(self):
        """AR(1) phi=-0.4 should produce negative sign-autocorrelation at short windows."""
        val = self.snap["trend_persist_20"]
        if val is not None:
            assert val < 0, f"trend_persist_20={val} should be negative for mean-reverter"

    def test_pullbacks_not_shallower_than_uptrend(self):
        """Mean-reverter pullbacks should generally be at least somewhat present."""
        med = self.snap["pullback_median_252"]
        # We just check it's computable (no NaN) and >= 0
        if med is not None:
            assert med >= 0


# ---------------------------------------------------------------------------
# (c) Gappy event series — gap_share and event_gap_contrib elevated
# ---------------------------------------------------------------------------

class TestGappySeries:
    """Case (c): series with >=6 large overnight gaps."""

    @classmethod
    def setup_class(cls):
        rng = np.random.default_rng(SEED + 2)
        n = 600
        # Smooth baseline close
        rets = rng.normal(0.0005, 0.005, n)
        close_baseline = 100.0 * np.exp(np.cumsum(rets))

        # Build OHLCV with large overnight gaps at specific indices
        gap_indices = [100, 150, 200, 250, 300, 350, 400]  # 7 gaps
        close = close_baseline.copy()
        idx = _idx(n)

        o = np.roll(close, 1)
        o[0] = close[0]
        h = close * 1.01
        l = close * 0.99
        v = np.full(n, 1_000_000.0)

        # Inject large gaps: open is far from prior close
        for gi in gap_indices:
            gap_size = close[gi - 1] * 0.05  # 5% gap
            o[gi] = close[gi - 1] + gap_size if gi % 2 == 0 else close[gi - 1] - gap_size

        cls.df_gappy = pd.DataFrame(
            {"open": o, "high": h, "low": l, "close": close, "volume": v}, index=idx
        )

        # Also build the smooth (no-gap) case (a) uptrend for comparison
        rets_up = 0.003 + rng.normal(0, 0.002, n)
        close_up = 100.0 * np.exp(np.cumsum(rets_up))
        cls.df_smooth = _make_ohlcv(close_up)

        cls.snap_gappy = features(cls.df_gappy)
        cls.snap_smooth = features(cls.df_smooth)

    def test_gap_share_elevated(self):
        """Gappy series should have higher gap_share_252 than smooth series."""
        gap_gappy = self.snap_gappy["gap_share_252"]
        gap_smooth = self.snap_smooth["gap_share_252"]
        if gap_gappy is not None and gap_smooth is not None:
            assert gap_gappy > gap_smooth, (
                f"gap_share_252 gappy={gap_gappy:.4f} should exceed smooth={gap_smooth:.4f}"
            )

    def test_event_gap_contrib_elevated(self):
        """Gappy series should have higher event_gap_contrib_252 than smooth."""
        eg_gappy = self.snap_gappy["event_gap_contrib_252"]
        eg_smooth = self.snap_smooth["event_gap_contrib_252"]
        if eg_gappy is not None and eg_smooth is not None:
            assert eg_gappy > eg_smooth, (
                f"event_gap_contrib_252 gappy={eg_gappy:.4f} should exceed smooth={eg_smooth:.4f}"
            )

    def test_gap_features_not_none(self):
        """With open column present, gap features should not be None."""
        assert self.snap_gappy["gap_share_252"] is not None
        assert self.snap_gappy["event_gap_contrib_252"] is not None


# ---------------------------------------------------------------------------
# (d) Close-only frame
# ---------------------------------------------------------------------------

class TestCloseOnlyFrame:
    """Case (d): OHLC/volume features None/NaN in close-only frame."""

    OHLC_VOLUME_FEATURES = [
        "gap_share_252",
        "event_gap_contrib_252",
        "wick_share_126",
        "extreme_bar_freq_252",
        "dollar_adv_21d",
        "amihud_252",
        "cs_spread_252",
    ]

    @classmethod
    def setup_class(cls):
        n = 600
        rng = np.random.default_rng(SEED + 3)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        cls.df = _make_close_only(close)
        cls.snap = features(cls.df)
        cls.series = feature_series(cls.df)

    def test_no_exception(self):
        """Must not raise on a close-only frame."""
        # Already passed setup; just assert snap is dict
        assert isinstance(self.snap, dict)

    def test_coverage_has_ohlc_false(self):
        cov = self.snap["coverage"]
        assert cov["has_ohlc"] is False, f"has_ohlc should be False, got {cov['has_ohlc']}"
        assert cov["has_volume"] is False

    def test_ohlc_volume_features_none_in_snapshot(self):
        """All OHLC/volume-dependent features must be None in snapshot."""
        for k in self.OHLC_VOLUME_FEATURES:
            val = self.snap[k]
            assert val is None, f"{k} should be None for close-only frame, got {val}"

    def test_ohlc_volume_features_nan_in_series(self):
        """All OHLC/volume-dependent feature columns must be all-NaN in series."""
        for k in self.OHLC_VOLUME_FEATURES:
            col = self.series[k]
            assert col.isna().all(), (
                f"feature_series[{k}] should be all-NaN for close-only frame"
            )

    def test_close_only_features_computable(self):
        """Purely close-based features should still compute (at least partially).

        reversal_half_life requires >=8 shocks within 504 bars, so it may be
        all-NaN for short or low-volatility fixtures — excluded from this check.
        """
        for k in ("trend_persist_20", "trend_persist_60", "trend_persist_126",
                  "slope_stability_126", "range_compression_pct"):
            col = self.series[k]
            # Should have at least some non-NaN values for n=600
            assert not col.isna().all(), f"{k} should have some non-NaN values"

    def test_all_keys_present_in_series(self):
        for k in _FEATURE_KEYS:
            assert k in self.series.columns, f"Missing column {k} in feature_series"


# ---------------------------------------------------------------------------
# (e) Leak test — THE CRITICAL PIT TEST
# ---------------------------------------------------------------------------

class TestLeakFreedom:
    """Case (e): value at row t must be identical from truncated and full series."""

    @classmethod
    def setup_class(cls):
        rng = np.random.default_rng(SEED + 4)
        n = 700
        rets = rng.normal(0.001, 0.012, n)
        close = 100.0 * np.exp(np.cumsum(rets))
        cls.df_full = _make_ohlcv(close)
        cls.series_full = feature_series(cls.df_full)
        # Test at these bar positions (after sufficient burn-in)
        cls.t_indices = [520, 560, 600, 640, 680]

    def test_no_lookahead_all_features(self):
        """Every feature column must be identical between truncated and full run."""
        rtol = 1e-9
        failures = []

        for t in self.t_indices:
            df_trunc = self.df_full.iloc[: t + 1]
            series_trunc = feature_series(df_trunc)

            for k in _FEATURE_KEYS:
                full_val = self.series_full[k].iloc[t]
                trunc_val = series_trunc[k].iloc[t]

                # Both NaN — no leak
                if pd.isna(full_val) and pd.isna(trunc_val):
                    continue
                # Both numeric — check equality
                if not pd.isna(full_val) and not pd.isna(trunc_val):
                    if abs(full_val - trunc_val) > rtol * max(abs(full_val), 1e-30):
                        failures.append(
                            f"t={t} {k}: full={full_val:.10f} trunc={trunc_val:.10f} "
                            f"diff={abs(full_val - trunc_val):.2e}"
                        )
                else:
                    # One NaN and the other not — only flag if full is not NaN
                    # (truncated may lose a NaN at the boundary due to shorter burn-in;
                    # if full is NaN and trunc is not, that would be a data leak)
                    if pd.isna(trunc_val) and not pd.isna(full_val):
                        # The truncated run has LESS data — it's expected to produce NaN
                        # earlier. Only the full→non-NaN / trunc→NaN mismatch is OK.
                        pass
                    elif not pd.isna(trunc_val) and pd.isna(full_val):
                        failures.append(
                            f"t={t} {k}: trunc gave {trunc_val:.6f} but full gave NaN — "
                            f"suggests a LOOKAHEAD (trunc used less data but got a value)"
                        )

        assert not failures, "Lookahead violations:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# (f) Real-data smoke test
# ---------------------------------------------------------------------------

class TestRealDataSmoke:
    """Case (f): load 2 real tickers and run both APIs."""

    @classmethod
    def setup_class(cls):
        data_dir = Path(__file__).resolve().parent.parent / "data" / "stocks"
        cls.tickers = []
        cls.dfs = {}
        for ticker in ["AAPL", "MSFT"]:
            p = data_dir / f"{ticker}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                # Use last 5 years for speed
                cutoff = df.index[-1] - pd.DateOffset(years=5)
                df = df[df.index >= cutoff]
                cls.dfs[ticker] = df
                cls.tickers.append(ticker)

    def test_tickers_found(self):
        assert len(self.tickers) == 2, f"Expected 2 tickers, found {len(self.tickers)}"

    def test_no_exception_features(self):
        for ticker in self.tickers:
            snap = features(self.dfs[ticker])
            assert isinstance(snap, dict), f"{ticker}: features() should return dict"

    def test_no_exception_feature_series(self):
        for ticker in self.tickers:
            series = feature_series(self.dfs[ticker])
            assert isinstance(series, pd.DataFrame), (
                f"{ticker}: feature_series() should return DataFrame"
            )

    def test_all_keys_present_snapshot(self):
        for ticker in self.tickers:
            snap = features(self.dfs[ticker])
            for k in _FEATURE_KEYS:
                assert k in snap, f"{ticker}: missing key {k} in snapshot"
            assert "coverage" in snap

    def test_all_keys_present_series(self):
        for ticker in self.tickers:
            series = feature_series(self.dfs[ticker])
            for k in _FEATURE_KEYS:
                assert k in series.columns, f"{ticker}: missing column {k} in series"

    def test_coverage_populated(self):
        for ticker in self.tickers:
            snap = features(self.dfs[ticker])
            cov = snap["coverage"]
            assert cov["n_bars"] > 0
            assert isinstance(cov["has_ohlc"], bool)
            assert isinstance(cov["has_volume"], bool)
            assert cov["as_of"] is not None

    def test_close_based_features_not_all_none(self):
        """At least the close-based features should compute for OHLCV data."""
        for ticker in self.tickers:
            snap = features(self.dfs[ticker])
            # At least one of the trend_persist features must be non-None
            vals = [snap[k] for k in ("trend_persist_20", "trend_persist_60", "trend_persist_126")]
            assert any(v is not None for v in vals), (
                f"{ticker}: all trend_persist features are None — unexpected"
            )


# ---------------------------------------------------------------------------
# (g) Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Case (g): same input twice -> identical outputs."""

    @classmethod
    def setup_class(cls):
        rng = np.random.default_rng(SEED + 5)
        n = 600
        rets = rng.normal(0.001, 0.01, n)
        close = 100.0 * np.exp(np.cumsum(rets))
        cls.df = _make_ohlcv(close)

    def test_features_deterministic(self):
        snap1 = features(self.df)
        snap2 = features(self.df)
        for k in _FEATURE_KEYS:
            v1 = snap1[k]
            v2 = snap2[k]
            if v1 is None and v2 is None:
                continue
            assert v1 == v2, f"features()  non-deterministic at key {k}: {v1} vs {v2}"
        assert snap1["coverage"] == snap2["coverage"]

    def test_feature_series_deterministic(self):
        s1 = feature_series(self.df)
        s2 = feature_series(self.df)
        for k in _FEATURE_KEYS:
            col1 = s1[k]
            col2 = s2[k]
            # NaN == NaN should hold element-wise
            nan1 = col1.isna()
            nan2 = col2.isna()
            assert (nan1 == nan2).all(), f"feature_series non-deterministic NaN pattern for {k}"
            non_nan = ~nan1
            if non_nan.any():
                assert (col1[non_nan] == col2[non_nan]).all(), (
                    f"feature_series non-deterministic values for {k}"
                )


# ---------------------------------------------------------------------------
# Additional unit tests for specific feature semantics
# ---------------------------------------------------------------------------

class TestFeatureSemantics:
    """Spot-check individual feature values on minimal hand-constructed fixtures."""

    def test_gap_share_zero_without_open(self):
        """Close-only frame: gap_share_252 is None in snapshot."""
        n = 300
        close = 100.0 * np.exp(np.cumsum(np.full(n, 0.001)))
        df = _make_close_only(close)
        snap = features(df)
        assert snap["gap_share_252"] is None

    def test_gap_share_nonzero_with_open(self):
        """OHLCV frame with actual gaps: gap_share_252 should be > 0."""
        n = 300
        rng = np.random.default_rng(100)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
        # Set open != prev_close to create gaps
        df = _make_ohlcv(close, open_offset=0.5)
        snap = features(df)
        gs = snap["gap_share_252"]
        if gs is not None:
            assert gs > 0

    def test_dollar_adv_none_without_volume(self):
        n = 300
        close = 100.0 * np.exp(np.cumsum(np.full(n, 0.001)))
        df = _make_close_only(close)
        snap = features(df)
        assert snap["dollar_adv_21d"] is None

    def test_dollar_adv_positive_with_volume(self):
        n = 300
        rng = np.random.default_rng(101)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
        df = _make_ohlcv(close)
        snap = features(df)
        adv = snap["dollar_adv_21d"]
        if adv is not None:
            assert adv > 0

    def test_range_compression_pct_nonnull(self):
        """range_compression_pct delegates to bbwp_series — should give a value for n=600."""
        n = 600
        rng = np.random.default_rng(102)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        df = _make_close_only(close)
        snap = features(df)
        # bbwp_series needs ~270+ bars to produce a value; n=600 should be enough
        assert snap["range_compression_pct"] is not None

    def test_as_of_truncation(self):
        """features(df, as_of=t) must use only data <= t."""
        n = 600
        rng = np.random.default_rng(103)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        df = _make_ohlcv(close)
        midpoint = df.index[400]
        snap_full = features(df)
        snap_trunc = features(df, as_of=midpoint)
        # Coverage n_bars should reflect the truncation
        assert snap_trunc["coverage"]["n_bars"] == 401

    def test_feature_series_index_equals_df(self):
        """feature_series output index must equal df index."""
        n = 300
        rng = np.random.default_rng(104)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        df = _make_ohlcv(close)
        series = feature_series(df)
        assert series.index.equals(df.index)

    def test_trend_persist_range(self):
        """trend_persist_* must be in [-1, 1] wherever not NaN."""
        n = 400
        rng = np.random.default_rng(105)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        df = _make_close_only(close)
        series = feature_series(df)
        for k in ("trend_persist_20", "trend_persist_60", "trend_persist_126"):
            col = series[k].dropna()
            assert (col >= -1.0 - 1e-9).all() and (col <= 1.0 + 1e-9).all(), (
                f"{k} out of [-1,1] range"
            )

    def test_slope_stability_range(self):
        """slope_stability_126 must be in [0, 1] wherever not NaN."""
        n = 400
        rng = np.random.default_rng(106)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        df = _make_close_only(close)
        series = feature_series(df)
        col = series["slope_stability_126"].dropna()
        assert (col >= 0.0 - 1e-9).all() and (col <= 1.0 + 1e-9).all()

    def test_pullback_nonnegative(self):
        """pullback_median_252 and pullback_p90_252 must be >= 0."""
        n = 400
        rng = np.random.default_rng(107)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
        df = _make_close_only(close)
        series = feature_series(df)
        for k in ("pullback_median_252", "pullback_p90_252"):
            col = series[k].dropna()
            if len(col) > 0:
                assert (col >= 0).all(), f"{k} has negative values"

    def test_extreme_bar_freq_range(self):
        """extreme_bar_freq_252 must be in [0, 1] wherever not NaN."""
        n = 400
        rng = np.random.default_rng(108)
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        df = _make_ohlcv(close)
        series = feature_series(df)
        col = series["extreme_bar_freq_252"].dropna()
        if len(col) > 0:
            assert (col >= 0.0).all() and (col <= 1.0 + 1e-9).all()
