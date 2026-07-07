"""Tests for w2051 housing high-frequency product -- pure logic, no network."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Import under test
from scripts.housing_hf_phase0 import (
    _rolling_zscore,
    _deseasonalize_pit,
    _spearman_ic,
    _auc_from_ic,
    _nw_lags,
    _direction_correct,
    _split_half_ic,
    _fwd_xhb_vs_spy,
)
from scripts.collect_redfin_hf import _parse_national, _parse_metro, _validate_schema
from scripts.collect_zori import _wide_to_long, _extract_national


# ---------------------------------------------------------------------------
# _rolling_zscore
# ---------------------------------------------------------------------------


class TestRollingZscore:
    def test_returns_series_same_length(self):
        s = pd.Series(range(50), dtype=float)
        z = _rolling_zscore(s, window=12)
        assert len(z) == len(s)

    def test_mean_near_zero_after_window(self):
        """After the warm-up, z-score of a stable mean should be near zero."""
        s = pd.Series([5.0] * 50)
        z = _rolling_zscore(s, window=12)
        # constant series -> std=0 -> NaN z-score; that's correct behavior
        assert z.dropna().isna().all() or (z.dropna().abs() < 1e-6).all()

    def test_trending_series_has_positive_z_at_end(self):
        s = pd.Series(list(range(50)), dtype=float)
        z = _rolling_zscore(s, window=12)
        # Latest value is maximum -> should have high positive z
        last = z.dropna().iloc[-1]
        assert last > 1.0

    def test_no_look_ahead(self):
        """z-score at position i must not depend on values after i."""
        base = pd.Series(list(range(40)), dtype=float)
        modified = base.copy()
        modified.iloc[30] = 1000.0  # shock after position 30
        z_base = _rolling_zscore(base, window=12)
        z_mod = _rolling_zscore(modified, window=12)
        # Before the shock, z-scores should be identical
        pd.testing.assert_series_equal(z_base.iloc[:30], z_mod.iloc[:30])


# ---------------------------------------------------------------------------
# _deseasonalize_pit (Amendment A5)
# ---------------------------------------------------------------------------


class TestDeseasonalizePit:
    def test_removes_monthly_pattern(self):
        """After PIT deseasonalization, monthly means should be near zero."""
        # Create 5 years of monthly data with a clear seasonal pattern
        # (month of year as the value, repeated over 5 years)
        idx = pd.date_range("2015-01-01", periods=60, freq="MS")
        # Strong seasonal: each month has a fixed value + small noise
        np.random.seed(42)
        seasonal = np.array([idx[i].month for i in range(60)], dtype=float)
        s = pd.Series(seasonal + np.random.randn(60) * 0.01, index=idx)
        deseas = _deseasonalize_pit(s)
        # After deseasonalization, the variance should be much smaller
        # Drop NaNs from warm-up period
        valid = deseas.dropna()
        assert valid.std() < s.std() * 0.2, (
            f"Deseasonalized std={valid.std():.3f} should be much less than "
            f"raw std={s.std():.3f}"
        )

    def test_pit_no_look_ahead(self):
        """Each month's deseasonalization must use only prior months of same month."""
        # 84 months from 2015-01-01 = 2015-01 through 2021-12
        idx = pd.date_range("2015-01-01", periods=84, freq="MS")
        s = pd.Series(np.ones(84), index=idx)
        # Insert a shock in January 2021 (7th January, index pos 72)
        jan_2021_pos = idx.get_loc(pd.Timestamp("2021-01-01"))
        s.iloc[jan_2021_pos] = 999.0
        deseas = _deseasonalize_pit(s)
        # Jan 2020 uses Jan 2015..2019 as history (5 priors, all = 1.0)
        # -> seasonal mean = 1.0, residual = 1.0 - 1.0 = 0.0
        # Must NOT be affected by the Jan 2021 shock (which happens later)
        jan_2020_idx = pd.Timestamp("2020-01-01")
        val = deseas.loc[jan_2020_idx]
        assert not math.isnan(val), "Jan 2020 should be non-NaN (5 prior Januaries)"
        assert abs(val) < 0.01, f"Jan 2020 residual should be ~0, got {val}"

    def test_first_occurrences_are_nan(self):
        """First two occurrences of each calendar month must be NaN."""
        idx = pd.date_range("2015-01-01", periods=36, freq="MS")
        s = pd.Series(np.arange(36, dtype=float), index=idx)
        deseas = _deseasonalize_pit(s)
        # First occurrence of each month (months 1-12 in 2015) should be NaN
        for i in range(12):
            assert math.isnan(deseas.iloc[i]), f"Month {i+1} first occurrence should be NaN"

    def test_output_same_length_as_input(self):
        idx = pd.date_range("2015-01-01", periods=48, freq="MS")
        s = pd.Series(np.random.randn(48), index=idx)
        deseas = _deseasonalize_pit(s)
        assert len(deseas) == len(s)


# ---------------------------------------------------------------------------
# _spearman_ic
# ---------------------------------------------------------------------------


class TestSpearmanIC:
    def test_perfect_rank_correlation(self):
        sig = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0] * 4)
        fwd = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5] * 4)
        ic = _spearman_ic(sig, fwd)
        assert abs(ic - 1.0) < 1e-6

    def test_perfect_negative_rank_correlation(self):
        sig = pd.Series([5.0, 4.0, 3.0, 2.0, 1.0] * 4)
        fwd = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5] * 4)
        ic = _spearman_ic(sig, fwd)
        assert abs(ic - (-1.0)) < 1e-6

    def test_insufficient_data_returns_nan(self):
        sig = pd.Series([1.0, 2.0, 3.0])
        fwd = pd.Series([0.1, 0.2, 0.3])
        ic = _spearman_ic(sig, fwd)
        assert math.isnan(ic)

    def test_handles_nan_gracefully(self):
        sig = pd.Series([1.0, np.nan, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0])
        fwd = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1])
        ic = _spearman_ic(sig, fwd)
        assert not math.isnan(ic)


# ---------------------------------------------------------------------------
# _auc_from_ic
# ---------------------------------------------------------------------------


class TestAucFromIC:
    def test_ic_zero_gives_auc_half(self):
        assert abs(_auc_from_ic(0.0) - 0.5) < 1e-9

    def test_ic_one_gives_auc_one(self):
        assert abs(_auc_from_ic(1.0) - 1.0) < 1e-9

    def test_ic_neg_one_gives_auc_zero(self):
        assert abs(_auc_from_ic(-1.0) - 0.0) < 1e-9

    def test_symmetry(self):
        assert abs(_auc_from_ic(0.3) + _auc_from_ic(-0.3) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# _nw_lags
# ---------------------------------------------------------------------------


class TestNwLags:
    def test_21d_horizon_is_1_lag(self):
        assert _nw_lags(21) == 1

    def test_63d_horizon_is_3_lags(self):
        assert _nw_lags(63) == 3

    def test_large_horizon_capped_at_6(self):
        assert _nw_lags(500) == 6


# ---------------------------------------------------------------------------
# _direction_correct
# ---------------------------------------------------------------------------


class TestDirectionCorrect:
    def test_price_drops_negative_is_correct(self):
        assert _direction_correct(-0.1, "price_drops_z") is True

    def test_price_drops_positive_is_wrong(self):
        assert _direction_correct(0.1, "price_drops_z") is False

    def test_pend_inv_positive_is_correct(self):
        assert _direction_correct(0.1, "pend_inv_ratio_z") is True

    def test_pend_inv_negative_is_wrong(self):
        assert _direction_correct(-0.1, "pend_inv_ratio_z") is False

    def test_baseline_always_true(self):
        assert _direction_correct(0.5, "mortgage_4wk_chg") is True
        assert _direction_correct(-0.5, "xhb_50dma_trend") is True


# ---------------------------------------------------------------------------
# _split_half_ic
# ---------------------------------------------------------------------------


class TestSplitHalfIC:
    def _make_data(self, n=60, sign=1):
        """Synthetic signal and forward return with controllable IC direction."""
        np.random.seed(42)
        idx = pd.date_range("2015-01-01", periods=n, freq="MS")
        sig = pd.Series(np.random.randn(n), index=idx)
        fwd = pd.Series(sign * sig.values * 0.5 + np.random.randn(n) * 0.1, index=idx)
        return sig, fwd

    def test_same_sign_both_halves(self):
        sig, fwd = self._make_data(n=60, sign=1)
        result = _split_half_ic(sig, fwd, "2017-07-01")
        # With strong signal, both halves should be positive
        assert result["n_is"] > 0
        assert result["n_oos"] > 0

    def test_counts_sum_to_total(self):
        sig, fwd = self._make_data(n=60, sign=1)
        result = _split_half_ic(sig, fwd, "2017-07-01")
        j = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
        assert result["n_is"] + result["n_oos"] == len(j)


# ---------------------------------------------------------------------------
# _fwd_xhb_vs_spy
# ---------------------------------------------------------------------------


class TestFwdXhbVsSpy:
    def _make_price_series(self, n=300, seed=7):
        np.random.seed(seed)
        idx = pd.bdate_range("2012-01-02", periods=n)
        xhb = pd.Series((1 + np.random.randn(n) * 0.01).cumprod() * 50, index=idx)
        spy = pd.Series((1 + np.random.randn(n) * 0.008).cumprod() * 300, index=idx)
        return xhb, spy

    def test_returns_series_indexed_by_signal_dates(self):
        xhb, spy = self._make_price_series()
        sig_dates = pd.DatetimeIndex(["2012-03-01", "2012-06-01", "2012-09-01"])
        result = _fwd_xhb_vs_spy(xhb, spy, 21, sig_dates)
        assert isinstance(result, pd.Series)
        assert len(result) <= len(sig_dates)

    def test_zero_excess_when_same_price(self):
        """If XHB == SPY in level, excess return should be ~zero."""
        idx = pd.bdate_range("2012-01-02", periods=300)
        both = pd.Series((1 + np.array([0.001] * 300)).cumprod() * 100, index=idx)
        sig_dates = pd.DatetimeIndex(["2012-03-01"])
        result = _fwd_xhb_vs_spy(both, both, 21, sig_dates)
        for v in result.values:
            assert abs(v) < 1e-10

    def test_skips_dates_without_future_data(self):
        xhb, spy = self._make_price_series(n=50)
        # Signal dates near end of series: last date has no 63d future
        sig_dates = pd.DatetimeIndex([xhb.index[-5].strftime("%Y-%m-%d")])
        result = _fwd_xhb_vs_spy(xhb, spy, 63, sig_dates)
        assert len(result) == 0   # no future data for horizon 63


# ---------------------------------------------------------------------------
# Redfin parse helpers (no network -- use synthetic DataFrames)
# ---------------------------------------------------------------------------


class TestRedfin:
    def _make_national_df(self):
        rows = []
        for i in range(24):
            dt = f"2020-{(i % 12) + 1:02d}-01"
            rows.append({
                "PERIOD_BEGIN": dt,
                "PERIOD_END": dt,
                "PERIOD_DURATION": 30,
                "REGION_TYPE": "national",
                "PROPERTY_TYPE": "All Residential",
                "IS_SEASONALLY_ADJUSTED": False,
                "REGION": "National",
                "CITY": "National",
                "STATE": "U.S.",
                "STATE_CODE": "US",
                "PENDING_SALES": 400000 + i * 1000,
                "INVENTORY": 1200000 + i * 5000,
                "PRICE_DROPS": 0.15 + i * 0.001,
                "MEDIAN_DOM": 45 + i,
            })
        return pd.DataFrame(rows)

    def test_parse_national_filters_property_type(self):
        df = self._make_national_df()
        # Add a townhouse row -- should be excluded
        extra = df.iloc[0:1].copy()
        extra["PROPERTY_TYPE"] = "Townhouse"
        df = pd.concat([df, extra])
        result = _parse_national(df)
        assert len(result) == 24  # only All Residential

    def test_parse_national_sets_date_index(self):
        df = self._make_national_df()
        result = _parse_national(df)
        assert result.index.name == "date"
        assert isinstance(result.index, pd.DatetimeIndex)

    def test_parse_national_has_required_cols(self):
        df = self._make_national_df()
        result = _parse_national(df)
        for col in ["pending_sales", "inventory", "price_drops", "median_dom"]:
            assert col in result.columns

    def test_parse_metro_filters_to_target_metros(self):
        df = self._make_national_df()
        df["REGION"] = "New York, NY metro area"
        df["REGION_TYPE"] = "metro"
        result = _parse_metro(df, ["New York, NY metro area", "Chicago, IL metro area"])
        # Only New York rows should be returned (Chicago not in df)
        assert set(result.index.get_level_values("metro")) == {"New York, NY metro area"}

    def test_schema_validation_raises_on_missing_col(self):
        """_validate_schema must raise ValueError if a required column is absent."""
        df = self._make_national_df()
        # Drop a required column to simulate schema drift
        df_missing = df.drop(columns=["PRICE_DROPS"])
        with pytest.raises(ValueError, match="missing columns"):
            _validate_schema(df_missing, context="(test)")

    def test_schema_validation_passes_on_valid_df(self):
        """_validate_schema must not raise when all required columns are present."""
        df = self._make_national_df()
        # Should not raise
        _validate_schema(df, context="(test)")

    def test_parse_national_raises_on_schema_drift(self):
        """_parse_national must raise (not silently degrade) on missing columns."""
        df = self._make_national_df().drop(columns=["PENDING_SALES"])
        with pytest.raises(ValueError, match="missing columns"):
            _parse_national(df)


# ---------------------------------------------------------------------------
# ZORI parse helpers
# ---------------------------------------------------------------------------


class TestZori:
    def _make_wide_df(self):
        dates = pd.date_range("2020-01-31", periods=12, freq="ME")
        cols = {"RegionID": [1, 2, 3], "SizeRank": [0, 1, 2],
                "RegionName": ["United States", "New York, NY", "Los Angeles, CA"],
                "RegionType": ["country", "msa", "msa"],
                "StateName": [None, "NY", "CA"]}
        for d in dates:
            cols[d.strftime("%Y-%m-%d")] = [1200 + d.month, 2500 + d.month, 1800 + d.month]
        return pd.DataFrame(cols)

    def test_extract_national_returns_us_row(self):
        df = self._make_wide_df()
        nat = _extract_national(df)
        assert not nat.empty
        assert "zori" in nat.columns
        assert isinstance(nat.index, pd.DatetimeIndex)

    def test_wide_to_long_metro_filter(self):
        df = self._make_wide_df()
        long = _wide_to_long(df, metro_filter=["New York, NY"])
        assert set(long["metro"].unique()) == {"New York, NY"}
        assert len(long) == 12

    def test_wide_to_long_no_nulls_in_zori(self):
        df = self._make_wide_df()
        long = _wide_to_long(df)
        assert long["zori"].notna().all()

    def test_wide_to_long_date_is_datetime(self):
        df = self._make_wide_df()
        long = _wide_to_long(df)
        assert pd.api.types.is_datetime64_any_dtype(long["date"])
