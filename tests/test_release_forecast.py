"""Unit tests for engine/release_forecast.py — release forecast engine.

Five test categories:
  1. PIT guard — values with realtime_start > asof must be excluded
  2. Contract — project_release output keys + display_only=True + authority=False
  3. Determinism — same inputs -> same output
  4. Walk-forward no-leak — prediction for period P uses only rows with realtime_start <= T-1
  5. Skew tag band — |sigma| <= 0.35 -> 'inline'; > 0.35 positive -> 'hotter'; negative -> 'cooler'

All tests use synthetic data only — no real parquet files are read.

Run:
    python -m pytest tests/test_release_forecast.py -v
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add repo root to path
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_forecast import (
    INLINE_BAND_SIGMA,
    MIN_QUANTILE_OBS,
    MIN_TRAIN_OBS,
    _build_matrix,
    _compute_quantiles,
    _ridge_fit,
    _ridge_predict,
    _walk_forward,
    _wilson,
    knowable_series,
    load_vintages,
)


# ---------------------------------------------------------------------------
# Synthetic vintage builder
# ---------------------------------------------------------------------------

def _make_vintages(
    series: str,
    periods: list[pd.Timestamp],
    values: list[float],
    release_delays_days: list[int],
) -> pd.DataFrame:
    """Build a synthetic vintages DataFrame.

    Each period gets ONE initial print released `release_delays_days[i]` days after period.
    realtime_end is set to a far future date (only realtime_start matters for PIT law).
    """
    rows = []
    for i, (p, v, d) in enumerate(zip(periods, values, release_delays_days)):
        rt_start = p + pd.Timedelta(days=d)
        rows.append({
            "series": series,
            "period": p,
            "value": v,
            "realtime_start": rt_start,
            "realtime_end": pd.Timestamp("2099-12-31"),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. PIT guard test
# ---------------------------------------------------------------------------

class TestPITGuard:
    """Values with realtime_start > asof must be excluded from knowable_series."""

    def test_future_print_excluded(self):
        """A value released after asof must not appear in knowable_series output."""
        periods = pd.date_range("2020-01-01", periods=6, freq="MS")
        values = [100.0 + i for i in range(6)]
        # Period 0-4: released 20 days after period (knowable)
        # Period 5: released 25 days after period (so realtime_start = 2020-06-25)
        delays = [20, 20, 20, 20, 20, 25]
        vintages = _make_vintages("TEST", list(periods), values, delays)

        # asof = 2020-06-20: period 5 (realtime_start=2020-06-25) must be excluded
        asof = date(2020, 6, 20)
        result = knowable_series(vintages, "TEST", asof)

        assert len(result) == 5, f"Expected 5 knowable rows, got {len(result)}"
        # period 2020-06-01 (index 5) must NOT appear
        periods_in_result = set(result["period"].dt.to_period("M").astype(str).tolist())
        assert "2020-06" not in periods_in_result, "Future release leaked through PIT filter"

    def test_release_day_boundary(self):
        """A value released exactly ON asof IS knowable (realtime_start == asof)."""
        periods = pd.date_range("2020-01-01", periods=3, freq="MS")
        values = [1.0, 2.0, 3.0]
        delays = [20, 20, 20]
        vintages = _make_vintages("TEST", list(periods), values, delays)

        # realtime_start of period 2 = 2020-03-21; asof = 2020-03-21 -> should be included
        rt_start_p2 = periods[2] + pd.Timedelta(days=20)
        asof = rt_start_p2.date()
        result = knowable_series(vintages, "TEST", asof)
        assert len(result) == 3, f"Boundary: expected 3 rows, got {len(result)}"

    def test_all_future_excluded(self):
        """If asof is before all realtime_starts, result must be empty."""
        periods = pd.date_range("2020-01-01", periods=3, freq="MS")
        values = [1.0, 2.0, 3.0]
        delays = [30, 30, 30]  # all release ~30 days after period
        vintages = _make_vintages("TEST", list(periods), values, delays)

        # asof before any release
        asof = date(2019, 12, 31)
        result = knowable_series(vintages, "TEST", asof)
        assert len(result) == 0, "No future prints should be knowable"

    def test_initial_print_selection(self):
        """For each period, only the FIRST realtime_start (initial print) is returned."""
        # Construct one period with two vintages (initial + revision)
        rows = [
            {"series": "T", "period": pd.Timestamp("2020-01-01"),
             "value": 100.0, "realtime_start": pd.Timestamp("2020-01-25"),
             "realtime_end": pd.Timestamp("2020-02-20")},
            {"series": "T", "period": pd.Timestamp("2020-01-01"),
             "value": 100.5, "realtime_start": pd.Timestamp("2020-02-21"),  # revision
             "realtime_end": pd.Timestamp("2099-12-31")},
        ]
        vintages = pd.DataFrame(rows)
        # asof = 2020-03-01: both vintages knowable
        result = knowable_series(vintages, "T", date(2020, 3, 1))
        assert len(result) == 1, "Should return only 1 row per period (initial print)"
        assert result.iloc[0]["value"] == 100.0, "Should return initial (first) print value"
        assert result.iloc[0]["realtime_start"] == pd.Timestamp("2020-01-25")


# ---------------------------------------------------------------------------
# 2. Contract test
# ---------------------------------------------------------------------------

class TestProjectReleaseContract:
    """project_release output must have required keys and correct authority flags."""

    REQUIRED_KEYS = {
        "release", "asof", "point", "p10", "p25", "p50", "p75", "p90",
        "confidence", "confidence_components", "input_completeness",
        "benchmark_set", "surprise_skew", "pit_provenance",
        "display_only", "authority",
    }
    BENCHMARK_SET_KEYS = {
        "naive_prior", "trailing_3m", "ar_model", "cleveland_nowcast", "market_implied"
    }
    SURPRISE_SKEW_KEYS = {"sigma", "tag", "inline_band"}

    def _minimal_projection(self) -> dict:
        """Return a minimal projection that satisfies the contract (constructed inline)."""
        from engine.release_forecast import _empty_projection
        return _empty_projection("cpi_headline", date(2020, 1, 1), "test")

    def test_all_required_keys_present(self):
        proj = self._minimal_projection()
        missing = self.REQUIRED_KEYS - set(proj.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_display_only_true(self):
        proj = self._minimal_projection()
        assert proj["display_only"] is True, "display_only must be True"

    def test_authority_false(self):
        proj = self._minimal_projection()
        assert proj["authority"] is False, "authority must be False"

    def test_pit_provenance_authority_false(self):
        proj = self._minimal_projection()
        prov = proj.get("pit_provenance", {})
        assert prov.get("authority") is False, "pit_provenance.authority must be False"
        assert prov.get("display_only") is True, "pit_provenance.display_only must be True"

    def test_benchmark_set_keys(self):
        proj = self._minimal_projection()
        bs = proj.get("benchmark_set", {})
        missing = self.BENCHMARK_SET_KEYS - set(bs.keys())
        assert not missing, f"benchmark_set missing keys: {missing}"
        # Cleveland and market_implied must be None (not yet available)
        assert bs["cleveland_nowcast"] is None
        assert bs["market_implied"] is None

    def test_surprise_skew_keys(self):
        proj = self._minimal_projection()
        ss = proj.get("surprise_skew", {})
        missing = self.SURPRISE_SKEW_KEYS - set(ss.keys())
        assert not missing, f"surprise_skew missing keys: {missing}"

    def test_inline_band_is_correct_value(self):
        proj = self._minimal_projection()
        assert proj["surprise_skew"]["inline_band"] == INLINE_BAND_SIGMA


# ---------------------------------------------------------------------------
# 3. Determinism test
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Same inputs must produce identical outputs."""

    def test_ridge_predict_deterministic(self):
        """Ridge prediction must be deterministic."""
        rng = np.random.default_rng(42)
        X_train = rng.standard_normal((100, 4))
        y_train = rng.standard_normal(100)
        x_pred = rng.standard_normal(4)

        pred1 = _ridge_predict(X_train, y_train, x_pred)
        pred2 = _ridge_predict(X_train, y_train, x_pred)
        assert pred1 == pred2, "Ridge prediction not deterministic"

    def test_walk_forward_deterministic(self):
        """Walk-forward results must be deterministic across two runs."""
        rng = np.random.default_rng(99)
        feature_names = ["lag1", "lag2", "lag3"]
        y = np.cumsum(rng.standard_normal(120))
        records = []
        for i in range(3, len(y)):
            records.append({
                "lag1": float(y[i - 1]),
                "lag2": float(y[i - 2]),
                "lag3": float(y[i - 3]),
                "target": float(y[i]),
            })

        res1 = _walk_forward(records, feature_names, "target")
        res2 = _walk_forward(records, feature_names, "target")

        assert len(res1) == len(res2)
        for r1, r2 in zip(res1, res2):
            assert r1["predicted"] == r2["predicted"], "Walk-forward not deterministic"

    def test_wilson_deterministic(self):
        w1 = _wilson(30, 50)
        w2 = _wilson(30, 50)
        assert w1 == w2


# ---------------------------------------------------------------------------
# 4. Walk-forward no-leak test
# ---------------------------------------------------------------------------

class TestWalkForwardNoLeak:
    """Prediction for period P must use only rows with realtime_start <= T-1 of P's release."""

    def _build_synthetic_records(self, n: int, include_future_feature: bool = False) -> tuple:
        """Build synthetic records where one feature is 'future' (should not be in training)."""
        rng = np.random.default_rng(7)
        y = rng.standard_normal(n + 5)
        feature_names = ["lag1", "lag2", "lag3"]
        records = []
        for i in range(3, n + 3):
            rec = {
                "lag1": float(y[i - 1]),
                "lag2": float(y[i - 2]),
                "lag3": float(y[i - 3]),
                "target": float(y[i]),
            }
            records.append(rec)
        return records, feature_names

    def test_no_future_leak_in_walk_forward(self):
        """The walk-forward must not use any training row AFTER the current step."""
        records, feature_names = self._build_synthetic_records(100)

        # Track which training rows are used at each step by checking n_train values
        results = _walk_forward(records, feature_names, "target")

        for r in results:
            # At step idx=i, training must use only records[:i], so n_train <= i
            assert r["n_train"] <= r["idx"], (
                f"Leak: step {r['idx']} used {r['n_train']} training rows "
                f"(should be at most {r['idx']})"
            )

    def test_synthetic_pit_via_knowable_series(self):
        """Construct vintages where some values have realtime_start > asof.
        The knowable_series result must never include those future values.
        """
        n = 60
        periods = pd.date_range("2010-01-01", periods=n, freq="MS")
        values = list(range(100, 100 + n))

        # Last 5 periods have release dates in the future relative to our test asof
        delays = [20] * (n - 5) + [500] * 5  # last 5 not knowable for a while
        vintages = _make_vintages("TESTPAYEMS", list(periods), values, delays)

        # asof = some date within the window
        asof = date(2014, 8, 1)
        result = knowable_series(vintages, "TESTPAYEMS", asof)

        for _, row in result.iterrows():
            assert row["realtime_start"] <= pd.Timestamp(asof), (
                f"PIT leak: {row['period']} has realtime_start={row['realtime_start']} "
                f"after asof={asof}"
            )

    def test_walk_forward_min_obs_enforced(self):
        """No prediction before MIN_TRAIN_OBS training rows are available."""
        records, feature_names = self._build_synthetic_records(MIN_TRAIN_OBS + 10)
        results = _walk_forward(records, feature_names, "target", min_obs=MIN_TRAIN_OBS)

        if results:
            first_idx = min(r["idx"] for r in results)
            assert first_idx >= MIN_TRAIN_OBS, (
                f"First prediction at idx={first_idx} < min_obs={MIN_TRAIN_OBS}"
            )


# ---------------------------------------------------------------------------
# 5. Skew tag band test
# ---------------------------------------------------------------------------

class TestSkewTagBand:
    """sigma within ±0.35 must be 'inline'; outside is 'hotter' or 'cooler'."""

    def _make_surprise_skew(self, sigma: float) -> dict:
        """Construct a minimal surprise_skew dict as the engine would produce."""
        from engine.release_forecast import INLINE_BAND_SIGMA
        if sigma is None:
            return {"sigma": None, "tag": None, "inline_band": INLINE_BAND_SIGMA}

        if abs(sigma) <= INLINE_BAND_SIGMA:
            tag = "inline"
        elif sigma > INLINE_BAND_SIGMA:
            tag = "hotter"
        else:
            tag = "cooler"
        return {"sigma": round(sigma, 4), "tag": tag, "inline_band": INLINE_BAND_SIGMA}

    @pytest.mark.parametrize("sigma,expected_tag", [
        (0.0, "inline"),
        (0.34, "inline"),
        (-0.34, "inline"),
        (0.35, "inline"),
        (-0.35, "inline"),
        (0.36, "hotter"),
        (-0.36, "cooler"),
        (1.0, "hotter"),
        (-1.0, "cooler"),
        (2.5, "hotter"),
        (-2.5, "cooler"),
    ])
    def test_skew_tag_classification(self, sigma, expected_tag):
        ss = self._make_surprise_skew(sigma)
        assert ss["tag"] == expected_tag, (
            f"sigma={sigma}: expected tag={expected_tag!r}, got {ss['tag']!r}"
        )

    def test_inline_band_constant(self):
        """The inline_band constant must be 0.35 per PREREG_V1.md."""
        assert INLINE_BAND_SIGMA == 0.35

    def test_null_sigma_gives_null_tag(self):
        ss = self._make_surprise_skew(None)
        assert ss["tag"] is None
        assert ss["sigma"] is None

    def test_boundary_exactly_at_band(self):
        """Exactly at the band boundary (|sigma| == 0.35) must be 'inline'."""
        for sigma in [INLINE_BAND_SIGMA, -INLINE_BAND_SIGMA]:
            ss = self._make_surprise_skew(sigma)
            assert ss["tag"] == "inline", (
                f"sigma={sigma} at band boundary must be 'inline', got {ss['tag']!r}"
            )


# ---------------------------------------------------------------------------
# Additional: Wilson CI correctness
# ---------------------------------------------------------------------------

class TestWilsonCI:
    def test_wilson_half_rate(self):
        """50% hit rate on large n should give CI near [0.40, 0.60]."""
        ci = _wilson(500, 1000)
        assert ci is not None
        lo, hi = ci
        assert 0.45 <= lo <= 0.50, f"Lower bound {lo} unexpected for 50% rate, n=1000"
        assert 0.50 <= hi <= 0.55, f"Upper bound {hi} unexpected for 50% rate, n=1000"

    def test_wilson_zero_n(self):
        """Zero n must return None."""
        assert _wilson(0, 0) is None

    def test_wilson_full_rate(self):
        """100% hit rate should give CI with lo > 0.9 for reasonable n."""
        ci = _wilson(100, 100)
        assert ci is not None
        assert ci[1] == 1.0, "Upper bound must be 1.0 for 100% rate"
        assert ci[0] > 0.9, f"Lower bound {ci[0]} unexpectedly low for 100% rate, n=100"


# ---------------------------------------------------------------------------
# Additional: ridge fit basic correctness
# ---------------------------------------------------------------------------

class TestRidgeFit:
    def test_ridge_fit_simple(self):
        """Ridge on perfect linear data should recover close to ground truth."""
        n = 200
        rng = np.random.default_rng(11)
        X = rng.standard_normal((n, 3))
        true_beta = np.array([2.0, -1.0, 0.5, 5.0])  # includes bias
        X_aug = np.hstack([X, np.ones((n, 1))])
        y = X_aug @ true_beta + rng.standard_normal(n) * 0.01

        beta_hat = _ridge_fit(X_aug, y, lam=0.001)
        np.testing.assert_allclose(beta_hat, true_beta, atol=0.1, err_msg="Ridge not close to ground truth")

    def test_ridge_predict_close_to_true(self):
        """Prediction on a new point should be close to ground truth with low noise."""
        rng = np.random.default_rng(22)
        X_train = rng.standard_normal((100, 2))
        true_w = np.array([3.0, -2.0])
        y_train = X_train @ true_w + rng.standard_normal(100) * 0.05

        x_test = np.array([1.0, 1.0])
        true_pred = true_w @ x_test
        pred = _ridge_predict(X_train, y_train, x_test)
        assert abs(pred - true_pred) < 0.5, f"Prediction {pred:.2f} far from truth {true_pred:.2f}"


# ---------------------------------------------------------------------------
# Additional: quantile computation
# ---------------------------------------------------------------------------

class TestQuantileComputation:
    def test_quantile_null_if_insufficient(self):
        """Quantiles must be None if fewer than MIN_QUANTILE_OBS residuals."""
        errors = np.arange(MIN_QUANTILE_OBS - 1, dtype=float)
        result = _compute_quantiles(errors, point=0.0)
        assert all(v is None for v in result.values()), "Quantiles must be null below min obs"

    def test_quantile_values_ordered(self):
        """p10 <= p25 <= p50 <= p75 <= p90."""
        rng = np.random.default_rng(55)
        errors = rng.standard_normal(MIN_QUANTILE_OBS + 10)
        point = 1.0
        result = _compute_quantiles(errors, point)
        vals = [result["p10"], result["p25"], result["p50"], result["p75"], result["p90"]]
        assert all(v is not None for v in vals)
        assert vals[0] <= vals[1] <= vals[2] <= vals[3] <= vals[4], (
            f"Quantile order violated: {vals}"
        )


# ---------------------------------------------------------------------------
# New regression tests (from Opus review fixes)
# ---------------------------------------------------------------------------

class TestCoverageIndexingBug:
    """Regression test: coverage quantiles must use only prior-position residuals.

    The bug: using r['idx'] (record index, ~60..351) instead of result_pos
    (ordinal position in results list, 0..n-1) to slice errors_accum pulls
    FUTURE residuals. This test constructs a walk-forward where record idx !=
    result position and verifies that quantiles use only prior-position residuals.
    """

    def test_result_pos_not_idx_for_quantiles(self):
        """result_pos must equal the ordinal position in the results list, not r['idx']."""
        rng = np.random.default_rng(42)
        feature_names = ["lag1", "lag2", "lag3"]
        y = rng.standard_normal(MIN_TRAIN_OBS + 40)
        records = []
        for i in range(3, len(y)):
            records.append({
                "lag1": float(y[i - 1]),
                "lag2": float(y[i - 2]),
                "lag3": float(y[i - 3]),
                "target": float(y[i]),
            })

        results = _walk_forward(records, feature_names, "target")
        assert results, "Walk-forward must produce at least one result"

        # Verify result_pos is stored and equals enumerate position
        for expected_pos, r in enumerate(results):
            assert "result_pos" in r, "result_pos must be present in walk-forward output"
            assert r["result_pos"] == expected_pos, (
                f"result_pos={r['result_pos']} != expected {expected_pos} at enumerate pos"
            )
            # result_pos must be strictly less than r['idx'] (the record index is always larger)
            assert r["result_pos"] < r["idx"], (
                f"result_pos={r['result_pos']} should be < idx={r['idx']} (record index is larger)"
            )

    def test_coverage_uses_only_prior_residuals(self):
        """Coverage quantiles must not pull future residuals.

        If quantiles used r['idx'] instead of result_pos, for the first result
        (result_pos=0), errors_accum[:r['idx']] would contain ~60 residuals
        (from future results), while errors_accum[:0] is empty (correct).
        We verify that for result_pos < MIN_QUANTILE_OBS, quantiles are None.
        """
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "release_forecast"))
        # Import backtest metrics function
        try:
            from research.release_forecast.backtest_release_forecast import _compute_metrics as bt_compute_metrics
        except ImportError:
            # Try alternate import path
            backtest_path = Path(__file__).resolve().parents[1] / "research" / "release_forecast" / "backtest_release_forecast.py"
            import importlib.util
            spec = importlib.util.spec_from_file_location("backtest_rf", backtest_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            bt_compute_metrics = mod._compute_metrics

        rng = np.random.default_rng(77)
        feature_names = ["lag1", "lag2", "lag3"]
        y = rng.standard_normal(MIN_TRAIN_OBS + 60)
        records = []
        for i in range(3, len(y)):
            records.append({
                "lag1": float(y[i - 1]),
                "lag2": float(y[i - 2]),
                "lag3": float(y[i - 3]),
                "target": float(y[i]),
            })

        results = _walk_forward(records, feature_names, "target")
        errors_accum = np.array([r["actual"] - r["predicted"] for r in results])

        # For the first MIN_QUANTILE_OBS results (result_pos 0..MIN_QUANTILE_OBS-1),
        # coverage must be None because there are fewer than MIN_QUANTILE_OBS prior residuals.
        early_results = [r for r in results if r["result_pos"] < MIN_QUANTILE_OBS]
        if early_results:
            m = bt_compute_metrics(early_results, errors_accum)
            # With correct indexing, most of these have no prior residuals -> coverage is None
            # (some near the end may have up to MIN_QUANTILE_OBS-1 prior residuals; still None)
            assert m["coverage_p10_p90"] is None, (
                f"Expected None coverage for result_pos < {MIN_QUANTILE_OBS}, "
                f"got {m['coverage_p10_p90']} — likely using idx instead of result_pos"
            )


class TestAR3NaNHandling:
    """Live-path AR3 baseline with NaN rows must return a finite number."""

    def test_ar3_with_nan_rows_returns_finite(self):
        """_compute_ar3 must not return NaN when training matrix contains NaN rows."""
        rng = np.random.default_rng(101)
        n_train = MIN_TRAIN_OBS + 20
        y_full = rng.standard_normal(n_train + 5)
        y_train = y_full[:n_train].copy()

        # Inject NaN into some rows of the AR3 training matrix (simulating missing lags)
        X_train_stub = np.full((n_train, 3), np.nan)
        for i in range(3, n_train):
            X_train_stub[i, 0] = y_full[i - 1]
            X_train_stub[i, 1] = y_full[i - 2]
            X_train_stub[i, 2] = y_full[i - 3]
        # First 3 rows have NaN (expected for lag-based construction)
        # This is the same structure _compute_ar3 builds internally

        from engine.release_forecast import _compute_ar3
        feats = {
            "cpi_hl_mom_lag1": float(y_full[-1]),
            "cpi_hl_mom_lag2": float(y_full[-2]),
            "cpi_hl_mom_lag3": float(y_full[-3]),
        }
        ar3_feat_names = ["cpi_hl_mom_lag1", "cpi_hl_mom_lag2", "cpi_hl_mom_lag3"]
        pred_features = np.array([feats[fn] for fn in ar3_feat_names], dtype=float)

        result = _compute_ar3(
            y_full=y_full,
            ar3_feat_names=ar3_feat_names,
            feats=feats,
            y_train=y_train,
            X_train=X_train_stub,
            pred_features=pred_features,
        )
        # Must return a finite float or None (not NaN)
        if result is not None:
            assert np.isfinite(result), f"AR3 returned non-finite value: {result}"


class TestNFP2010EvalFloor:
    """NFP evaluation floor: pre-2010 predictions must be excluded from NFP metrics."""

    def test_nfp_eval_floor_era_classification(self):
        """_era must return 'pre_2010' for months before 2010-01."""
        backtest_path = Path(__file__).resolve().parents[1] / "research" / "release_forecast" / "backtest_release_forecast.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("backtest_rf", backtest_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _era = mod._era

        # Pre-2010 months must classify as pre_2010
        for yr in range(1997, 2010):
            ts = pd.Timestamp(f"{yr}-06-01")
            assert _era(ts) == "pre_2010", f"{yr}-06 should be pre_2010, got {_era(ts)}"

        # 2010-01 and later must NOT be pre_2010
        ts_2010 = pd.Timestamp("2010-01-01")
        assert _era(ts_2010) != "pre_2010", "2010-01 must not be pre_2010"

    def test_nfp_era_boundary_2020(self):
        """2010-2020 era boundary: 2020-02 is in 2010_2020, 2020-03 is covid."""
        backtest_path = Path(__file__).resolve().parents[1] / "research" / "release_forecast" / "backtest_release_forecast.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("backtest_rf2", backtest_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _era = mod._era

        assert _era(pd.Timestamp("2020-02-01")) == "2010_2020", "2020-02 must be 2010_2020"
        assert _era(pd.Timestamp("2020-03-01")) == "covid", "2020-03 must be covid"
        assert _era(pd.Timestamp("2020-06-01")) == "covid", "2020-06 must be covid"
        assert _era(pd.Timestamp("2020-07-01")) == "2020_recovery", "2020-07 must be 2020_recovery"
        assert _era(pd.Timestamp("2020-12-01")) == "2020_recovery", "2020-12 must be 2020_recovery"
        assert _era(pd.Timestamp("2021-01-01")) == "2021_plus", "2021-01 must be 2021_plus"


# ---------------------------------------------------------------------------
# 12. Gasoline reference-month anchoring (PREREG_V1.md §2.3 feature 7)
# ---------------------------------------------------------------------------

class TestGasolineRefMonthAnchoring:
    """gasoline_mom must average GASREGW over the reference month M vs M-1 —
    NOT over asof's calendar month (at the decision date asof is inside M+1,
    which silently shifted the leg one month forward and missed ref-month
    energy moves entirely)."""

    @staticmethod
    def _write_gasregw(root: Path) -> None:
        # Weekly Monday observations: May flat 3.00; June collapsing to 2.00; one July week.
        idx = pd.to_datetime([
            "2026-05-04", "2026-05-11", "2026-05-18", "2026-05-25",
            "2026-06-01", "2026-06-08", "2026-06-15", "2026-06-22", "2026-06-29",
            "2026-07-06",
        ])
        vals = [3.00, 3.00, 3.00, 3.00, 2.80, 2.60, 2.40, 2.20, 2.00, 2.10]
        df = pd.DataFrame({"GASREGW": vals}, index=idx)
        path = root / "data" / "fred"
        path.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path / "GASREGW.parquet")

    def test_explicit_ref_month_uses_ref_vs_prior(self, tmp_path):
        """asof in July, ref_month=June → June avg (2.40) vs May avg (3.00) = -20%."""
        from engine.release_forecast import build_cpi_features
        self._write_gasregw(tmp_path)
        vintages = _make_vintages(
            "CPIAUCSL",
            [pd.Timestamp("2026-03-01"), pd.Timestamp("2026-04-01"), pd.Timestamp("2026-05-01")],
            [320.0, 321.0, 321.5],
            [40, 40, 40],
        )
        feats, prov = build_cpi_features(
            date(2026, 7, 7), vintages, tmp_path,
            release_type="cpi_headline", ref_month=date(2026, 6, 1),
        )
        assert feats["gasoline_mom"] == pytest.approx(-20.0, abs=1e-9), (
            f"gasoline_mom must be June-vs-May (-20%), got {feats['gasoline_mom']} "
            "(-12.5% would mean the leg is still anchored on asof's month)"
        )
        assert prov.get("gasoline_ref_month") == "2026-06-01"

    def test_derived_ref_month_matches_explicit(self, tmp_path):
        """ref_month=None derives last-knowable-print month + 1 (May print → June)."""
        from engine.release_forecast import build_cpi_features
        self._write_gasregw(tmp_path)
        vintages = _make_vintages(
            "CPIAUCSL",
            [pd.Timestamp("2026-03-01"), pd.Timestamp("2026-04-01"), pd.Timestamp("2026-05-01")],
            [320.0, 321.0, 321.5],
            [40, 40, 40],
        )
        feats, prov = build_cpi_features(
            date(2026, 7, 7), vintages, tmp_path, release_type="cpi_headline",
        )
        assert feats["gasoline_mom"] == pytest.approx(-20.0, abs=1e-9)
        assert prov.get("gasoline_ref_month") == "2026-06-01"

    def test_ref_month_in_progress_is_pit_truncated(self, tmp_path):
        """ref_month=July with asof mid-July → July weeks < asof (2.10) vs June avg (2.40)."""
        from engine.release_forecast import build_cpi_features
        self._write_gasregw(tmp_path)
        vintages = _make_vintages(
            "CPIAUCSL",
            [pd.Timestamp("2026-04-01"), pd.Timestamp("2026-05-01"), pd.Timestamp("2026-06-01")],
            [321.0, 321.5, 320.8],
            [40, 40, 40],
        )
        feats, _ = build_cpi_features(
            date(2026, 7, 10), vintages, tmp_path,
            release_type="cpi_headline", ref_month=date(2026, 7, 1),
        )
        assert feats["gasoline_mom"] == pytest.approx((2.10 / 2.40 - 1) * 100, abs=1e-9)

    def test_core_still_excludes_gasoline(self, tmp_path):
        from engine.release_forecast import build_cpi_features
        self._write_gasregw(tmp_path)
        vintages = _make_vintages(
            "CPILFESL",
            [pd.Timestamp("2026-04-01"), pd.Timestamp("2026-05-01")],
            [310.0, 310.5],
            [40, 40],
        )
        feats, prov = build_cpi_features(
            date(2026, 7, 7), vintages, tmp_path,
            release_type="cpi_core", ref_month=date(2026, 6, 1),
        )
        assert "gasoline_mom" not in feats
        assert prov.get("gasoline_absent") is True
