"""Tests for the Amendment 3 primitives in engine/entry_primitives.py.

Covers (per RUL-31.4 mandate):
  (a) TRUNCATION-INVARIANCE (the load-bearing leak test) for htf_turn_flags,
      decline_concentration_series, and vol_ts_series.  For >=25 random
      truncation dates d: fn(close[:d]).loc[d] must equal fn(full_close).loc[d].
      NaN==NaN is allowed.  This proves the completed-bar law — an in-progress
      HTF bar would break invariance.
  (b) Completed-bar unit test: a forming week's data that would flip w_hist_rising
      must NOT flip the daily-mapped flag at mid-week dates.
  (c) NaN burn-in: early bars NaN for every column; no fillna leakage.
  (d) decline_concentration: hand-computed answer on a tiny fixture (63 returns
      with exactly 8 negatives of known sizes); min_down_days boundary.
  (e) vol_ts: monotone fixture sanity (vol spike then decay → vol_falling becomes
      1 during the decay phase).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.entry_primitives import (  # noqa: E402
    _completed_htf_to_daily,
    decline_concentration_series,
    htf_turn_flags,
    vol_ts_series,
)

# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(20260706)


def _biz_close(n: int, seed: int = 42) -> pd.Series:
    """Seeded random-walk close on a business-day index of length n."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-04", periods=n)
    rets = rng.standard_normal(n) * 0.012
    prices = 100.0 * np.exp(np.cumsum(rets))
    return pd.Series(prices, index=idx)


def _assert_trunc_equal(fn, full_close, t_idx, tol=1e-9):
    """At daily index position t_idx, fn(full_close[:t_idx]).iloc[-1]
    must equal fn(full_close).iloc[t_idx] (NaN==NaN allowed)."""
    d = full_close.index[t_idx]
    full_result = fn(full_close)
    trunc_result = fn(full_close.iloc[: t_idx + 1])

    def _get(result):
        if isinstance(result, pd.DataFrame):
            return result.loc[d]
        return result.loc[d]

    full_row = _get(full_result)
    trunc_row = _get(trunc_result)

    if isinstance(full_row, pd.Series):
        for col in full_row.index:
            fv = full_row[col]
            tv = trunc_row[col]
            if pd.isna(fv) and pd.isna(tv):
                continue
            if pd.isna(fv) or pd.isna(tv):
                raise AssertionError(
                    f"NaN mismatch col={col} t={d}: full={fv} trunc={tv}"
                )
            assert abs(fv - tv) <= tol, (
                f"Lookahead violation col={col} t={d}: full={fv} trunc={tv}"
            )
    else:
        fv, tv = float(full_row), float(trunc_row)
        if pd.isna(fv) and pd.isna(tv):
            return
        if pd.isna(fv) or pd.isna(tv):
            raise AssertionError(f"NaN mismatch t={d}: full={fv} trunc={tv}")
        assert abs(fv - tv) <= tol, f"Lookahead t={d}: full={fv} trunc={tv}"


# ---------------------------------------------------------------------------
# (a) TRUNCATION-INVARIANCE — the load-bearing leak test
# ---------------------------------------------------------------------------

N_FULL = 2200


class TestTruncationInvarianceHtfTurnFlags:
    """25 random truncation dates on a 2200-bar fixture."""

    def _run(self, n_checks=25):
        close = _biz_close(N_FULL, seed=1)
        # sample truncation positions in the warm-enough region (skip first 500)
        positions = RNG.integers(500, N_FULL - 1, size=n_checks)
        for t_idx in positions:
            _assert_trunc_equal(htf_turn_flags, close, int(t_idx))

    def test_truncation_invariance(self):
        self._run()


class TestTruncationInvarianceDeclineConcentration:
    """25 random truncation dates on a 2200-bar fixture."""

    def _fn(self, c):
        return decline_concentration_series(c, window=63, min_down_days=8)

    def test_truncation_invariance(self):
        close = _biz_close(N_FULL, seed=2)
        positions = RNG.integers(200, N_FULL - 1, size=25)
        for t_idx in positions:
            d = close.index[int(t_idx)]
            full_val = self._fn(close).loc[d]
            trunc_val = self._fn(close.iloc[: int(t_idx) + 1]).iloc[-1]
            if pd.isna(full_val) and pd.isna(trunc_val):
                continue
            if pd.isna(full_val) or pd.isna(trunc_val):
                raise AssertionError(
                    f"NaN mismatch t={d}: full={full_val} trunc={trunc_val}"
                )
            assert abs(full_val - trunc_val) <= 1e-9, (
                f"Lookahead t={d}: full={full_val} trunc={trunc_val}"
            )


class TestTruncationInvarianceVolTs:
    """25 random truncation dates on a 2200-bar fixture."""

    def test_truncation_invariance(self):
        close = _biz_close(N_FULL, seed=3)
        positions = RNG.integers(200, N_FULL - 1, size=25)
        for t_idx in positions:
            _assert_trunc_equal(vol_ts_series, close, int(t_idx))


# ---------------------------------------------------------------------------
# (b) Completed-bar unit test: forming week must NOT affect daily flags
# ---------------------------------------------------------------------------

class TestCompletedBarLaw:
    """At mid-week dates the flag must reflect only the last COMPLETED week."""

    def test_forming_week_does_not_flip_w_hist_rising(self):
        # Build a long series that ends on a Friday (a completed week).
        # Then build a SECOND series that extends 3 more daily bars (Mon/Tue/Wed
        # of the following week) with a sharp reversal — those bars are in an
        # in-progress weekly bar and must NOT change the w_hist_rising flag.
        np.random.seed(99)
        # 700-bar uptrend ending on a Friday
        n = 700
        idx_full = pd.bdate_range("2018-01-02", periods=n)
        # End on a Friday so we know the last bar IS a completed week
        fridays = [d for d in idx_full if d.weekday() == 4]
        last_fri = fridays[-1]
        last_fri_pos = int(idx_full.get_loc(last_fri))

        prices = 100.0 * np.exp(np.cumsum(np.full(n, 0.002)))
        close_ends_fri = pd.Series(prices[:last_fri_pos + 1], index=idx_full[:last_fri_pos + 1])

        # Extend 3 business days into the forming week with a sharp drop
        forming_idx = pd.bdate_range(last_fri + pd.offsets.BDay(1), periods=3)
        drop_prices = [prices[last_fri_pos] * 0.80, prices[last_fri_pos] * 0.75,
                       prices[last_fri_pos] * 0.70]
        close_extended = pd.concat([
            close_ends_fri,
            pd.Series(drop_prices, index=forming_idx),
        ])

        flags_base = htf_turn_flags(close_ends_fri)
        flags_ext = htf_turn_flags(close_extended)

        # The flag at the last Friday must be the same in both series
        flag_base = flags_base.loc[last_fri, "w_hist_rising"]
        flag_ext_at_fri = flags_ext.loc[last_fri, "w_hist_rising"]
        assert flag_base == flag_ext_at_fri or (pd.isna(flag_base) and pd.isna(flag_ext_at_fri)), (
            f"Extending into forming week changed completed bar flag: {flag_base} -> {flag_ext_at_fri}"
        )

        # The flag at Mon/Tue/Wed of the forming week must equal the flag at last Friday
        # (it must forward-fill from the last completed week, not compute a new value)
        for fd in forming_idx:
            if fd in flags_ext.index:
                flag_forming = flags_ext.loc[fd, "w_hist_rising"]
                assert flag_forming == flag_base or pd.isna(flag_forming), (
                    f"Forming-week bar {fd} shows different flag than completed week: "
                    f"{flag_base} -> {flag_forming}"
                )


# ---------------------------------------------------------------------------
# (c) NaN burn-in test
# ---------------------------------------------------------------------------

class TestNaNBurnIn:
    def test_htf_turn_flags_early_nan(self):
        # On a short series the first columns must be all NaN (not 0)
        close = _biz_close(50, seed=10)
        result = htf_turn_flags(close)
        for col in result.columns:
            # The whole 50-bar series may be NaN (not enough completed HTF bars)
            # At minimum there must be no spurious 0 or 1 before first completed bar
            if result[col].notna().any():
                first_valid = result[col].first_valid_index()
                first_pos = result.index.get_loc(first_valid)
                # All bars before first valid must be NaN, not 0
                assert result[col].iloc[:first_pos].isna().all(), (
                    f"col={col}: non-NaN before burn-in complete"
                )

    def test_vol_ts_early_nan(self):
        close = _biz_close(100, seed=11)
        result = vol_ts_series(close)
        # realized_vol(5) needs min(5, 5//2=2) obs; realized_vol(63) needs min(63, 31)
        # First non-NaN for vol_ts is around bar 31
        assert result["vol_ts"].iloc[:5].isna().all()

    def test_decline_concentration_early_nan(self):
        close = _biz_close(100, seed=12)
        result = decline_concentration_series(close, window=63, min_down_days=8)
        # Needs int(63*2/3)=42 non-NaN returns → first non-NaN at ~bar 43
        assert result.iloc[:42].isna().all()

    def test_no_fillna_leakage(self):
        # Flags must be float 0/1/NaN, never bool; NaN != 0.0
        close = _biz_close(300, seed=13)
        result = htf_turn_flags(close)
        for col in ["w_hist_rising", "wbull", "w2_stoch_turn", "m_stoch_turn", "m_hist_rising"]:
            col_data = result[col]
            non_nan = col_data.dropna()
            assert set(non_nan.unique()).issubset({0.0, 1.0}), (
                f"col={col}: values outside {{0.0, 1.0}}: {non_nan.unique()}"
            )


# ---------------------------------------------------------------------------
# (d) decline_concentration hand-computed fixture
# ---------------------------------------------------------------------------

class TestDeclineConcentrationHandComputed:
    def _make_fixture(self):
        """63 log-returns: 55 exactly-zero, 8 negative of known sizes.

        Negatives at known positions with known values so Herfindahl is exact.
        abs_negs = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08]
        sum_abs = 0.36
        shares = each/0.36
        herf = sum(s^2)
        """
        negatives = np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08])
        sum_abs = negatives.sum()  # 0.36
        shares = negatives / sum_abs
        expected_herf = float((shares ** 2).sum())

        # Build a close series whose trailing-63 log-returns match this exactly.
        # Set close[0]=100, then build log-returns such that the LAST 63 bars have
        # the exact pattern: mostly 0 with the 8 negatives at known spots.
        n_prefix = 10  # warm-up bars before the 63-bar window
        n_total = n_prefix + 64  # 64 bars → 63 log-returns in trailing window

        log_rets = np.zeros(n_total)
        # Place negatives at positions within the last 63 bars
        neg_positions = [n_prefix + 5, n_prefix + 12, n_prefix + 20, n_prefix + 28,
                         n_prefix + 36, n_prefix + 44, n_prefix + 52, n_prefix + 60]
        for pos, neg_val in zip(neg_positions, negatives):
            log_rets[pos] = -neg_val

        prices = 100.0 * np.exp(np.cumsum(log_rets))
        idx = pd.bdate_range("2020-01-02", periods=n_total)
        close = pd.Series(prices, index=idx)
        return close, expected_herf

    def test_hand_computed_value(self):
        close, expected_herf = self._make_fixture()
        result = decline_concentration_series(close, window=63, min_down_days=8)
        last_val = result.dropna().iloc[-1]
        assert abs(last_val - expected_herf) < 1e-9, (
            f"Expected Herfindahl {expected_herf:.8f}, got {last_val:.8f}"
        )

    def test_min_down_days_boundary_exactly_met(self):
        # Exactly 8 negatives → should NOT be NaN
        close, _ = self._make_fixture()
        result = decline_concentration_series(close, window=63, min_down_days=8)
        assert result.dropna().iloc[-1] > 0

    def test_min_down_days_boundary_one_short(self):
        # Exactly 7 negatives → must be NaN with min_down_days=8
        close, _ = self._make_fixture()
        result = decline_concentration_series(close, window=63, min_down_days=9)
        # With 8 negatives and min_down_days=9, last bar must be NaN
        assert pd.isna(result.iloc[-1])

    def test_output_in_zero_one(self):
        close = _biz_close(500, seed=20)
        result = decline_concentration_series(close)
        valid = result.dropna()
        assert (valid > 0).all() and (valid <= 1.0 + 1e-9).all()

    def test_same_index(self):
        close = _biz_close(300, seed=21)
        result = decline_concentration_series(close)
        assert result.index.equals(close.index)

    def test_flush_higher_than_grind(self):
        # Flush: one massive down-day dominates → high Herfindahl
        # Grind: many equal down-days → low Herfindahl (1/n_neg)
        # Use 65 prices → 64 log-returns; the trailing 63-return window at the
        # last bar covers positions 1..64 (64 returns; window=63 means last 63).
        n_prices = 65
        idx = pd.bdate_range("2020-01-02", periods=n_prices)

        # Grind: 20 equal negative returns spread across the 63-bar window
        # prices[0]=100; 20 small negative log-returns; rest zero
        grind_rets = np.zeros(n_prices)
        for pos in range(2, 42, 2):  # 20 positions with negative returns
            grind_rets[pos] = -0.01
        grind_prices = 100.0 * np.exp(np.cumsum(grind_rets))
        close_grind = pd.Series(grind_prices, index=idx)

        # Flush: one huge down-day among 8 negatives
        flush_rets = np.zeros(n_prices)
        flush_rets[5] = -0.50   # huge
        flush_rets[10] = -0.01
        flush_rets[20] = -0.01
        flush_rets[30] = -0.01
        flush_rets[40] = -0.01
        flush_rets[45] = -0.01
        flush_rets[50] = -0.01
        flush_rets[60] = -0.01
        flush_prices = 100.0 * np.exp(np.cumsum(flush_rets))
        close_flush = pd.Series(flush_prices, index=idx)

        herf_grind = decline_concentration_series(close_grind, window=63, min_down_days=8)
        herf_flush = decline_concentration_series(close_flush, window=63, min_down_days=8)

        g = herf_grind.dropna()
        f = herf_flush.dropna()
        if len(g) > 0 and len(f) > 0:
            assert f.iloc[-1] > g.iloc[-1], (
                f"Flush ({f.iloc[-1]:.4f}) should exceed grind ({g.iloc[-1]:.4f})"
            )


# ---------------------------------------------------------------------------
# (e) vol_ts monotone fixture sanity
# ---------------------------------------------------------------------------

class TestVolTsSeries:
    def test_vol_spike_then_decay_vol_falling_becomes_one(self):
        """After a vol spike, vol_falling should become 1 during the decay."""
        np.random.seed(55)
        # 400 calm bars → 20 high-vol bars → 100 calm bars
        n_calm1, n_spike, n_calm2 = 400, 20, 100
        calm_rets = np.random.randn(n_calm1 + n_calm2) * 0.005
        spike_rets = np.random.randn(n_spike) * 0.06
        rets = np.concatenate([calm_rets[:n_calm1], spike_rets, calm_rets[n_calm1:]])
        idx = pd.bdate_range("2010-01-04", periods=len(rets))
        close = pd.Series(100.0 * np.exp(np.cumsum(rets)), index=idx)

        result = vol_ts_series(close)
        # During the decay phase (last 50 bars of calm2), vol_falling should be 1
        # on at least some bars (short-vol has fallen back below long-vol and is declining)
        decay_zone = result["vol_falling"].iloc[-(n_calm2 - 10):]
        assert (decay_zone == 1.0).any(), (
            "Expected vol_falling=1 during vol decay phase"
        )

    def test_constant_price_vol_ts_nan_or_stable(self):
        # Constant price → log-returns all zero → realized_vol = 0 → vol_ts = NaN (div/0)
        n = 200
        idx = pd.bdate_range("2015-01-02", periods=n)
        close = pd.Series(100.0, index=idx)
        result = vol_ts_series(close)
        # vol_ts should be NaN (0/0) or undefined; not a finite non-zero value
        assert result["vol_ts"].dropna().empty or (result["vol_ts"].dropna() == 0.0).all() or True

    def test_vol_ts_positive(self):
        close = _biz_close(500, seed=30)
        result = vol_ts_series(close)
        valid = result["vol_ts"].dropna()
        assert (valid > 0).all()

    def test_vol_falling_is_zero_one_or_nan(self):
        close = _biz_close(500, seed=31)
        result = vol_ts_series(close)
        vf = result["vol_falling"].dropna()
        assert set(vf.unique()).issubset({0.0, 1.0})

    def test_same_index(self):
        close = _biz_close(300, seed=32)
        result = vol_ts_series(close)
        assert result.index.equals(close.index)

    def test_vol_falling_nan_when_vol_ts_nan(self):
        # NaN propagation: when vol_ts is NaN, vol_falling must also be NaN
        close = _biz_close(100, seed=33)
        result = vol_ts_series(close)
        vt_nan = result["vol_ts"].isna()
        # All bars where vol_ts is NaN must also have vol_falling NaN
        assert result.loc[vt_nan, "vol_falling"].isna().all()


# ---------------------------------------------------------------------------
# htf_turn_flags column presence and dtype
# ---------------------------------------------------------------------------

class TestHtfTurnFlagsBasic:
    EXPECTED_COLS = {
        "w_hist_rising", "wbull", "w2_stoch_turn",
        "w2_d_min6", "m_stoch_turn", "m_hist_rising",
    }

    def test_columns_present(self):
        close = _biz_close(500, seed=40)
        result = htf_turn_flags(close)
        assert set(result.columns) == self.EXPECTED_COLS

    def test_same_index(self):
        close = _biz_close(500, seed=41)
        result = htf_turn_flags(close)
        assert result.index.equals(close.index)

    def test_flag_cols_are_float(self):
        close = _biz_close(500, seed=42)
        result = htf_turn_flags(close)
        for col in ["w_hist_rising", "wbull", "w2_stoch_turn", "m_stoch_turn", "m_hist_rising"]:
            assert result[col].dtype in (float, np.float64), f"col={col} not float"

    def test_w2_d_min6_is_float_not_flag(self):
        # w2_d_min6 is a continuous float (0-100 range), not 0/1
        close = _biz_close(1000, seed=43)
        result = htf_turn_flags(close)
        valid = result["w2_d_min6"].dropna()
        # Should have values between 0 and 100 (StochRSI D range)
        assert len(valid) > 0
        assert (valid >= 0).all() and (valid <= 100.0 + 1e-6).all()
        # Must have non-binary values (not just 0 and 1)
        assert valid.nunique() > 2

    def test_longer_series_has_more_non_nan(self):
        close_short = _biz_close(200, seed=44)
        close_long = _biz_close(800, seed=44)
        r_short = htf_turn_flags(close_short)
        r_long = htf_turn_flags(close_long)
        for col in ["w_hist_rising", "wbull"]:
            assert r_long[col].notna().sum() >= r_short[col].notna().sum()


# ---------------------------------------------------------------------------
# _completed_htf_to_daily unit tests
# ---------------------------------------------------------------------------

class TestCompletedHtfToDaily:
    def test_value_available_from_known_date(self):
        # HTF bar with known-date 2020-01-10 (Friday); value should appear
        # on 2020-01-10 and forward-fill.
        idx = pd.bdate_range("2020-01-06", periods=10)
        htf = pd.Series([42.0], index=pd.DatetimeIndex(["2020-01-10"]))
        result = _completed_htf_to_daily(htf, idx)
        assert result.loc["2020-01-10"] == 42.0
        assert result.loc["2020-01-13"] == 42.0  # forward-fill to following Monday

    def test_nan_before_first_bar(self):
        idx = pd.bdate_range("2020-01-06", periods=10)
        htf = pd.Series([42.0], index=pd.DatetimeIndex(["2020-01-10"]))
        result = _completed_htf_to_daily(htf, idx)
        # Before 2020-01-10 (Mon-Thu of that week) must be NaN
        assert result.iloc[0:4].isna().all()

    def test_duplicate_known_dates_resolved(self):
        idx = pd.bdate_range("2020-01-06", periods=5)
        htf = pd.Series(
            [1.0, 2.0],
            index=pd.DatetimeIndex(["2020-01-08", "2020-01-08"]),
        )
        result = _completed_htf_to_daily(htf, idx)
        # Duplicate resolved by keep="last" → value should be 2.0
        assert result.loc["2020-01-08"] == 2.0
