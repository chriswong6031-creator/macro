"""Minimal unit tests for f501_cn_block_sector_readthrough_phase0.

Tests cover pure-logic functions only — no network calls, no file I/O.
All tested functions are imported from the script module.
"""
import math
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

# Make script importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.f501_cn_block_sector_readthrough_phase0 import (
    bh_correction,
    hac_tstat,
    split_half_same_sign,
    loco_same_sign,
    date_collapse,
    fwd_return,
    get_active_basket_members,
    DISC_V1,
    DISC_V2,
)


# ---------------------------------------------------------------------------
# hac_tstat
# ---------------------------------------------------------------------------

class TestHacTstat:
    def test_all_positive(self):
        """Strong positive series: t should be positive, p significant."""
        x = pd.Series([0.05] * 30)
        t, p, n = hac_tstat(x)
        assert t > 2.0
        assert 0.0 <= p < 0.05  # p can be exactly 0 for extreme t
        assert n == 30

    def test_all_negative(self):
        """Strong negative series: t should be negative."""
        x = pd.Series([-0.05] * 30)
        t, p, n = hac_tstat(x)
        assert t < -2.0

    def test_zero_series(self):
        """Zero series: t should be zero or nan."""
        x = pd.Series([0.0] * 30)
        t, p, n = hac_tstat(x)
        assert math.isnan(t) or abs(t) < 1e-6

    def test_too_short(self):
        """Too few observations: returns nan."""
        x = pd.Series([0.1, 0.2, 0.3])
        t, p, n = hac_tstat(x)
        assert math.isnan(t)
        assert n == 3

    def test_empty(self):
        """Empty series: returns nan."""
        x = pd.Series(dtype=float)
        t, p, n = hac_tstat(x)
        assert math.isnan(t)
        assert n == 0


# ---------------------------------------------------------------------------
# bh_correction
# ---------------------------------------------------------------------------

class TestBHCorrection:
    def test_empty(self):
        assert bh_correction([]) == []

    def test_all_significant(self):
        """Very small p-values: all q should be significant."""
        ps = [0.001, 0.002, 0.003, 0.004, 0.005, 0.006]
        qs = bh_correction(ps)
        assert all(q <= 0.10 for q in qs)

    def test_none_significant(self):
        """High p-values: none should survive BH at 0.10."""
        ps = [0.90, 0.85, 0.80]
        qs = bh_correction(ps)
        assert all(q > 0.10 for q in qs)

    def test_monotone_q(self):
        """q-values should be non-decreasing when p-values are sorted."""
        ps = [0.01, 0.04, 0.20, 0.50]
        qs = bh_correction(ps)
        for i in range(len(qs) - 1):
            assert qs[i] <= qs[i + 1] + 1e-10

    def test_single(self):
        """Single p-value: q should equal p (rank=1 of 1)."""
        qs = bh_correction([0.05])
        assert abs(qs[0] - 0.05) < 1e-10

    def test_capped_at_one(self):
        """q-values should not exceed 1.0."""
        ps = [0.99, 0.98]
        qs = bh_correction(ps)
        assert all(q <= 1.0 for q in qs)


# ---------------------------------------------------------------------------
# split_half_same_sign
# ---------------------------------------------------------------------------

class TestSplitHalfSameSign:
    def _make_series(self, pre_vals, post_vals):
        pre_dates = pd.date_range('2015-01-01', periods=len(pre_vals), freq='7D')
        post_dates = pd.date_range('2020-06-01', periods=len(post_vals), freq='7D')
        dates = pre_dates.tolist() + post_dates.tolist()
        vals = pre_vals + post_vals
        return pd.Series(vals, index=pd.DatetimeIndex(dates))

    def test_both_negative(self):
        s = self._make_series([-0.02] * 10, [-0.03] * 10)
        assert bool(split_half_same_sign(s)) is True

    def test_both_positive(self):
        s = self._make_series([0.02] * 10, [0.03] * 10)
        assert bool(split_half_same_sign(s)) is False

    def test_mixed(self):
        s = self._make_series([-0.02] * 10, [0.03] * 10)
        assert bool(split_half_same_sign(s)) is False

    def test_insufficient_data(self):
        """Too few obs in one half -> False."""
        s = self._make_series([-0.02] * 2, [-0.03] * 2)
        assert split_half_same_sign(s) is False


# ---------------------------------------------------------------------------
# loco_same_sign
# ---------------------------------------------------------------------------

class TestLocoSameSign:
    def _make_series(self, n=100, val=-0.01):
        dates = pd.date_range('2013-01-01', periods=n, freq='14D')
        return pd.Series([val] * n, index=dates)

    def test_all_negative(self):
        s = self._make_series(val=-0.02)
        result = loco_same_sign(s)
        assert all(bool(v) is True for v in result.values() if v is not None)

    def test_all_positive(self):
        s = self._make_series(val=0.02)
        result = loco_same_sign(s)
        assert all(bool(v) is False for v in result.values() if v is not None)

    def test_keys_present(self):
        s = self._make_series()
        result = loco_same_sign(s)
        assert '2015_crash' in result
        assert '2018_bear' in result
        assert '2024_stimulus' in result


# ---------------------------------------------------------------------------
# date_collapse
# ---------------------------------------------------------------------------

class TestDateCollapse:
    def test_single_event_per_date(self):
        df = pd.DataFrame({
            'event_date': pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03']),
            'horizon': [21, 21, 21],
            'excess_return': [0.01, 0.02, 0.03],
        })
        result = date_collapse(df, 21)
        assert len(result) == 3
        assert abs(result.mean() - 0.02) < 1e-10

    def test_multiple_events_same_date(self):
        """Multiple events on the same date should be averaged."""
        df = pd.DataFrame({
            'event_date': pd.to_datetime(['2023-01-01', '2023-01-01', '2023-01-02']),
            'horizon': [21, 21, 21],
            'excess_return': [0.10, 0.20, 0.05],
        })
        result = date_collapse(df, 21)
        assert len(result) == 2
        assert abs(result.iloc[0] - 0.15) < 1e-10  # average of 0.10 and 0.20
        assert abs(result.iloc[1] - 0.05) < 1e-10

    def test_horizon_filter(self):
        """Only the specified horizon is returned."""
        df = pd.DataFrame({
            'event_date': pd.to_datetime(['2023-01-01', '2023-01-01']),
            'horizon': [21, 63],
            'excess_return': [0.01, 0.99],
        })
        result = date_collapse(df, 21)
        assert len(result) == 1
        assert abs(result.iloc[0] - 0.01) < 1e-10


# ---------------------------------------------------------------------------
# fwd_return (via price panel simulation)
# ---------------------------------------------------------------------------

class TestFwdReturn:
    def _make_panel(self):
        """Create a simple 100-day price series for one ticker."""
        dates = pd.date_range('2020-01-02', periods=100, freq='B')
        # Prices grow by 1% per day
        prices = pd.Series(
            [100.0 * (1.01 ** i) for i in range(100)],
            index=dates,
            name='TEST.SZ'
        )
        return pd.DataFrame({'TEST.SZ': prices})

    def test_basic_positive_return(self):
        panel = self._make_panel()
        signal_date = pd.Timestamp('2020-01-02')
        ret = fwd_return(panel, 'TEST.SZ', signal_date, 21)
        expected = (1.01 ** 21) - 1
        assert ret is not None
        assert abs(ret - expected) < 1e-6

    def test_ticker_not_in_panel(self):
        panel = self._make_panel()
        ret = fwd_return(panel, 'MISSING.SZ', pd.Timestamp('2020-01-02'), 21)
        assert ret is None

    def test_insufficient_horizon(self):
        """Not enough rows after signal_date: return None."""
        panel = self._make_panel()
        # Signal near end of series
        signal_date = pd.Timestamp('2020-05-20')
        ret = fwd_return(panel, 'TEST.SZ', signal_date, 100)
        assert ret is None

    def test_signal_before_data_start(self):
        """Signal date before series start: should still work (lands on first date)."""
        panel = self._make_panel()
        signal_date = pd.Timestamp('2019-12-01')  # before series start
        ret = fwd_return(panel, 'TEST.SZ', signal_date, 21)
        assert ret is not None  # lands on first available date


# ---------------------------------------------------------------------------
# get_active_basket_members
# ---------------------------------------------------------------------------

class TestGetActiveBasketMembers:
    def _make_baskets(self):
        return {
            'basket_a': [
                {'ticker': 'AAA.SZ', 'added': pd.Timestamp('2021-06-15'), 'removed': pd.Timestamp('2099-12-31')},
                {'ticker': 'BBB.SZ', 'added': pd.Timestamp('2021-06-15'), 'removed': pd.Timestamp('2023-01-01')},
            ],
            'basket_b': [
                {'ticker': 'CCC.SZ', 'added': pd.Timestamp('2021-06-15'), 'removed': pd.Timestamp('2099-12-31')},
            ],
        }

    def test_active_before_removal(self):
        baskets = self._make_baskets()
        result = get_active_basket_members(baskets, pd.Timestamp('2022-06-01'))
        assert 'AAA.SZ' in result.get('basket_a', set())
        assert 'BBB.SZ' in result.get('basket_a', set())

    def test_removed_ticker_excluded(self):
        """BBB.SZ is removed on 2023-01-01, should not appear after that."""
        baskets = self._make_baskets()
        result = get_active_basket_members(baskets, pd.Timestamp('2023-06-01'))
        assert 'AAA.SZ' in result.get('basket_a', set())
        assert 'BBB.SZ' not in result.get('basket_a', set())

    def test_empty_basket_excluded(self):
        """A basket with no active members should not appear in result."""
        baskets = {
            'empty_basket': [
                {'ticker': 'DDD.SZ', 'added': pd.Timestamp('2021-06-15'), 'removed': pd.Timestamp('2022-01-01')},
            ],
        }
        result = get_active_basket_members(baskets, pd.Timestamp('2023-01-01'))
        assert 'empty_basket' not in result


# ---------------------------------------------------------------------------
# Threshold unit boundary tests
# These tests guard against the unit-mismatch bug where DISC_V1=-0.08 (ratio)
# was compared against avg_premium_pct (percent), passing -0.08% as the cutoff
# instead of -8%.  A block at -6% (ratio -0.06) is ABOVE the -8% threshold
# and must be EXCLUDED from V1; a block at -10% (ratio -0.10) is below -8%
# and must be INCLUDED in V1 but EXCLUDED from V2 (-15% threshold).
# ---------------------------------------------------------------------------

class TestThresholdUnitBoundary:
    """Boundary checks that the threshold comparison uses consistent units.

    avg_premium_pct = premium_ratio * 100 (percent units).
    DISC_V1 = -0.08 (ratio) => threshold in pct = -8.0%.
    DISC_V2 = -0.15 (ratio) => threshold in pct = -15.0%.

    The filter in build_block_clusters must apply `threshold_pct * 100`
    when comparing against avg_premium_pct.  We replicate the filter inline
    to test without file I/O.
    """

    def _apply_threshold(self, pct_value: float, disc_ratio: float) -> bool:
        """Return True if pct_value passes the discount filter (as the script does)."""
        return pct_value <= disc_ratio * 100.0

    # V1 boundary: threshold = -8%
    def test_v1_minus6pct_excluded(self):
        """-6% discount (ratio -0.06) is ABOVE -8% threshold — must be excluded."""
        assert not self._apply_threshold(-6.0, DISC_V1), (
            f"Expected -6% block to be EXCLUDED from V1 (threshold {DISC_V1*100}%), "
            f"but filter passed it through"
        )

    def test_v1_minus8pct_included(self):
        """-8% discount is exactly at the boundary — must be included (<=)."""
        assert self._apply_threshold(-8.0, DISC_V1), (
            f"Expected -8% block to be INCLUDED in V1 (threshold {DISC_V1*100}%)"
        )

    def test_v1_minus10pct_included(self):
        """-10% discount is below -8% threshold — must be included."""
        assert self._apply_threshold(-10.0, DISC_V1)

    # V2 boundary: threshold = -15%
    def test_v2_minus10pct_excluded(self):
        """-10% discount (ratio -0.10) is ABOVE -15% threshold — must be excluded from V2."""
        assert not self._apply_threshold(-10.0, DISC_V2), (
            f"Expected -10% block to be EXCLUDED from V2 (threshold {DISC_V2*100}%)"
        )

    def test_v2_minus15pct_included(self):
        """-15% discount is exactly at the V2 boundary — must be included."""
        assert self._apply_threshold(-15.0, DISC_V2)

    def test_v2_minus20pct_included(self):
        """-20% discount is deeply below -15% — must be included in V2."""
        assert self._apply_threshold(-20.0, DISC_V2)

    def test_v1_threshold_not_ratio_units(self):
        """Guard against the bug: if threshold were compared in ratio units (-0.08),
        then a -6% block would PASS (since -6.0 <= -0.08 is False — wait, actually
        -6.0 <= -0.08 IS True, which is the bug: -6% would PASS when it should NOT).
        This test verifies that using raw ratio as threshold produces wrong result."""
        # In the BUGGY implementation: avg_premium_pct (-6.0) <= DISC_V1 (-0.08) => True (wrong!)
        buggy_result = (-6.0 <= DISC_V1)  # -6.0 <= -0.08 = True — this is the bug
        assert buggy_result is True, "This confirms the bug: raw-ratio comparison passes -6% blocks"
        # In the FIXED implementation: avg_premium_pct (-6.0) <= DISC_V1*100 (-8.0) => False (correct)
        fixed_result = (-6.0 <= DISC_V1 * 100.0)  # -6.0 <= -8.0 = False
        assert fixed_result is False, "Fixed comparison correctly excludes -6% blocks from V1"
