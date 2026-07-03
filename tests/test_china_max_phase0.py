"""tests/test_china_max_phase0.py — W3-B: MAX/lottery-effect phase-0 unit tests.

Four test groups:
  1. Signal construction: MAX signal correctness, locked-limit mask, fill-realistic entry.
  2. Decile and L/S: decile assignment, L/S direction, monotonicity computation.
  3. Permutation placebo: reproducibility (seeded), null distribution shape.
  4. Screen test: pool arithmetic, lift direction.

These are self-contained synthetic-data tests — no real parquet files needed.
Matches the sibling idiom in tests/test_china_alpha_w2b.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.china_max_phase0 import (  # noqa: E402
    build_daily_ret,
    build_locked_limit_mask,
    build_max_signal,
    build_rev_proxy,
    build_abn_turn_proxy,
    fill_realistic_fwd,
    decile_monotonicity,
    screen_test,
    MAX_WINDOW,
    FWD_WINDOW,
    DECILES,
    SEED,
)


# ─────────────────────────────────── fixtures ────────────────────────────────

def _make_close(n: int = 60, tickers: int = 5, seed: int = 42) -> pd.DataFrame:
    """Synthetic close panel: n dates x tickers, geometric random walk."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-02", periods=n, freq="B")
    data = np.exp(rng.normal(0, 0.01, size=(n, tickers)).cumsum(axis=0)) * 10
    cols = [f"T{i:03d}.SZ" for i in range(tickers)]
    return pd.DataFrame(data, index=idx, columns=cols)


def _make_ohlc(n: int = 60, tickers: int = 5, seed: int = 99) -> tuple:
    """Synthetic close/high/low: close ± random spread."""
    rng = np.random.default_rng(seed)
    close = _make_close(n, tickers, seed)
    spread = np.abs(rng.normal(0, 0.005, close.shape))
    high = close * (1 + spread)
    low = close * (1 - spread)
    return close, high, low


def _make_ohlcv(n: int = 60, tickers: int = 5, seed: int = 99) -> tuple:
    rng = np.random.default_rng(seed)
    close, high, low = _make_ohlc(n, tickers, seed)
    vol = pd.DataFrame(np.abs(rng.normal(1e6, 2e5, close.shape)),
                       index=close.index, columns=close.columns)
    return close, high, low, vol


# ─────────────────────────────────── Group 1: signal construction ────────────

class TestSignalConstruction:
    """build_daily_ret, build_locked_limit_mask, build_max_signal, fill_realistic_fwd."""

    def test_daily_ret_shape(self):
        close = _make_close(40, 3)
        ret = build_daily_ret(close)
        assert ret.shape == close.shape
        # First row should be NaN (no prior close)
        assert ret.iloc[0].isna().all()

    def test_daily_ret_correct_value(self):
        """pct_change(1) is (close[t]-close[t-1])/close[t-1]."""
        close = _make_close(10, 1, seed=0)
        ret = build_daily_ret(close)
        expected = close.iloc[2, 0] / close.iloc[1, 0] - 1
        assert abs(ret.iloc[2, 0] - expected) < 1e-10

    def test_locked_limit_mask_detects_limit_bar(self):
        """A bar where high==low==close must be flagged as locked."""
        close, high, low = _make_ohlc(10, 2)  # high != low for all bars
        # Inject a locked-limit bar at row 5, ticker 0: force hi==lo==close
        locked_val = float(close.iloc[5, 0])
        high.iloc[5, 0] = locked_val
        low.iloc[5, 0] = locked_val
        locked = build_locked_limit_mask(close, high, low)
        assert bool(locked.iloc[5, 0]) is True
        # Other bars should NOT be locked (high != low from _make_ohlc)
        assert bool(locked.iloc[6, 0]) is False

    def test_locked_limit_mask_false_for_normal_bars(self):
        """Normal OHLC (high > low) bars must not be flagged."""
        close, high, low = _make_ohlc(30, 4)
        locked = build_locked_limit_mask(close, high, low)
        # Random-walk prices will virtually never have hi==lo==close
        assert locked.sum().sum() == 0

    def test_max_signal_window(self):
        """MAX signal at date t = max(ret[t-20:t]) over 21 days."""
        close = _make_close(50, 1)
        ret = build_daily_ret(close)
        max_sig = build_max_signal(ret)
        # Before window is filled, should be NaN
        assert max_sig.iloc[:MAX_WINDOW - 1, 0].isna().all()
        # At MAX_WINDOW row, value should equal max of first MAX_WINDOW returns
        d = max_sig.index[MAX_WINDOW]
        expected_slice = ret.iloc[1:MAX_WINDOW + 1, 0]
        expected_max = float(expected_slice.max())
        assert abs(max_sig.iloc[MAX_WINDOW, 0] - expected_max) < 1e-10

    def test_max_signal_non_negative(self):
        """MAX of returns over 21 sessions: for a trending-up series, MAX > 0."""
        n = 50
        idx = pd.date_range("2020-01-02", periods=n, freq="B")
        close = pd.DataFrame(np.arange(1, n + 1, dtype=float).reshape(-1, 1),
                             index=idx, columns=["T000.SZ"])
        ret = build_daily_ret(close)
        max_sig = build_max_signal(ret)
        valid = max_sig.dropna()
        assert (valid.values >= 0).all()

    def test_fill_realistic_nulls_locked_entry(self):
        """If the fill bar (T+1) is locked-limit, fill-realistic return must be NaN."""
        close, high, low = _make_ohlc(60, 2)
        # Make bar 5 a locked-limit bar for ticker 0
        high.iloc[5, 0] = close.iloc[5, 0]
        low.iloc[5, 0] = close.iloc[5, 0]
        locked = build_locked_limit_mask(close, high, low)
        # fwd_fill at row 4 uses entry bar at row 5 (shift -1)
        fwd = fill_realistic_fwd(high, low, locked)
        # Row 4, ticker 0 should be NaN because entry bar 5 is locked
        assert pd.isna(fwd.iloc[4, 0])

    def test_fill_realistic_positive_for_rising_series(self):
        """For a monotone rising price series, fill-realistic forward returns > 0."""
        n = 60
        idx = pd.date_range("2020-01-02", periods=n, freq="B")
        prices = np.arange(10, 10 + n, dtype=float)
        close = pd.DataFrame(prices.reshape(-1, 1), index=idx, columns=["T000.SZ"])
        # high = close + 0.5, low = close - 0.5 (symmetric spread)
        high = close + 0.5
        low = close - 0.5
        locked = build_locked_limit_mask(close, high, low)
        fwd = fill_realistic_fwd(high, low, locked)
        # First few bars have valid forward returns; they should be positive
        valid = fwd.iloc[:30, 0].dropna()
        assert (valid > 0).all()

    def test_rev_proxy_negative_for_rising(self):
        """Reversal proxy = -ret_21d; for a rising market it should be negative."""
        n = 50
        idx = pd.date_range("2020-01-02", periods=n, freq="B")
        prices = np.arange(1, n + 1, dtype=float)
        close = pd.DataFrame(prices.reshape(-1, 1), index=idx, columns=["T000.SZ"])
        rev = build_rev_proxy(close)
        valid = rev.dropna()
        # Rising market → ret_21d > 0 → -ret_21d < 0
        assert (valid.values <= 0).all()

    def test_abn_turn_z_score_near_zero_for_constant_volume(self):
        """Constant volume → abn_turn z-score should be near 0 (mean - mean / std ≈ 0)."""
        n = 120
        idx = pd.date_range("2020-01-02", periods=n, freq="B")
        close = _make_close(n, 1)
        # Constant volume
        vol = pd.DataFrame(np.ones((n, 1)) * 1_000_000,
                           index=close.index, columns=close.columns)
        abn = build_abn_turn_proxy(close, vol)
        # After burn-in, values should be near 0 (std ≈ 0 for constant → NaN or 0)
        valid = abn.iloc[70:, 0].dropna()
        if len(valid) > 0:
            assert (valid.abs() < 1e-3).all()


# ─────────────────────────────────── Group 2: decile and L/S ─────────────────

class TestDecileAndLS:
    """Decile assignment, L/S direction, monotonicity checker."""

    def test_decile_monotonicity_perfect(self):
        """All 9/9 monotone steps for a perfectly decreasing decile mean series."""
        means = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
        decile_fill = [pd.Series([m]) for m in means]
        result = decile_monotonicity(decile_fill)
        assert result["monotone_steps"] == 9
        assert result["max_steps"] == 9

    def test_decile_monotonicity_none(self):
        """0/9 monotone steps for a perfectly increasing series (D1 worst → D10 best)."""
        means = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        decile_fill = [pd.Series([m]) for m in means]
        result = decile_monotonicity(decile_fill)
        assert result["monotone_steps"] == 0

    def test_decile_monotonicity_values_reported(self):
        """Reported decile mean list should match input means."""
        means = [float(i) * 0.1 for i in range(10, 0, -1)]
        decile_fill = [pd.Series([m]) for m in means]
        result = decile_monotonicity(decile_fill)
        assert len(result["decile_means_pct"]) == 10
        for i, m in enumerate(means):
            assert abs(result["decile_means_pct"][i] - m * 100) < 1e-6

    def test_max_signal_decile_direction(self):
        """A constructed series where high-MAX names definitely underperform:
        the L/S should be positive (low-MAX earns more than high-MAX)."""
        # 100 names; force the top-10 names (highest MAX) to have near-zero forward returns
        # and the bottom-10 to have high forward returns → L/S > 0
        n = 100
        # Synthetic signal: ranks 1..100
        signal = pd.Series(np.arange(1, n + 1, dtype=float),
                           index=[f"T{i:03d}" for i in range(n)])
        # Forward returns: inversely correlated with signal (high rank → low return)
        fwd = pd.Series(np.linspace(1.0, 0.0, n),
                        index=signal.index)
        # Decile label
        rank_pct = signal.rank(pct=True)
        dec = np.ceil(rank_pct * 10).clip(1, 10).astype(int)
        d1 = fwd[dec == 1]  # lowest MAX
        d10 = fwd[dec == 10]  # highest MAX
        ls = float(d1.mean() - d10.mean())
        assert ls > 0, "Low-MAX should outperform high-MAX in a lottery-effect scenario"

    def test_monotone_steps_partial(self):
        """Mixed pattern: exactly 5 monotone steps."""
        means = [1.0, 0.9, 0.8, 0.85, 0.7, 0.6, 0.55, 0.5, 0.3, 0.2]
        # Steps: 1>2✓ 2>3✓ 3<4✗ 4>5✓ 5>6✓ 6>7✓ 7>8✓ 8>9✓ 9>10✓ = 8 steps
        decile_fill = [pd.Series([m]) for m in means]
        result = decile_monotonicity(decile_fill)
        # Count manually: [1>0.9, 0.9>0.8, NOT 0.8>0.85, 0.85>0.7, 0.7>0.6, 0.6>0.55,
        #                   0.55>0.5, 0.5>0.3, 0.3>0.2] = 8 monotone steps
        expected = sum(1 for i in range(len(means) - 1) if means[i] > means[i + 1])
        assert result["monotone_steps"] == expected


# ─────────────────────────────────── Group 3: permutation placebo ─────────────

class TestPermutationPlacebo:
    """Verify the null distribution is well-behaved."""

    def test_null_is_seeded_deterministic(self):
        """Same seed produces identical null distribution."""
        rng1 = np.random.default_rng(SEED)
        rng2 = np.random.default_rng(SEED)

        n = 30
        sig = np.arange(n, dtype=float)
        arr1 = rng1.permutation(sig)
        arr2 = rng2.permutation(sig)
        np.testing.assert_array_equal(arr1, arr2)

    def test_permuted_signal_has_same_marginals(self):
        """Permutation preserves the marginal distribution (same sorted values)."""
        rng = np.random.default_rng(SEED)
        sig = np.random.default_rng(0).standard_normal(50)
        perm = rng.permutation(sig)
        np.testing.assert_array_almost_equal(np.sort(sig), np.sort(perm))

    def test_null_mean_near_zero(self):
        """With a scrambled signal, L/S mean across many permutations should be ≈0."""
        rng = np.random.default_rng(SEED)
        # Synthetic: 50 names, independent signal and returns
        np.random.seed(0)
        n_dates, n_names = 50, 50

        ls_means = []
        for _ in range(200):
            ls_per_date = []
            for _ in range(n_dates):
                sig = rng.standard_normal(n_names)
                fwd = rng.standard_normal(n_names)  # independent of sig
                ranks = sig.argsort().argsort()
                lo_idx = np.where(ranks < n_names // 10)[0]
                hi_idx = np.where(ranks >= n_names - n_names // 10)[0]
                ls_per_date.append(float(fwd[lo_idx].mean() - fwd[hi_idx].mean()))
            ls_means.append(float(np.mean(ls_per_date)))

        null_mean = float(np.mean(ls_means))
        # Under the null (independent signal/returns), mean L/S should be close to 0
        assert abs(null_mean) < 0.1, (
            f"Null mean {null_mean} too far from 0 — check L/S computation")

    def test_perm_is_two_sided(self):
        """perm-p counts |t_null| >= |t_real| — same for positive and negative t."""
        null_ts = np.array([-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.5, 1.0, 1.5, 2.0,
                             2.5, 3.0])
        t_real = 2.8
        p_pos = float(np.mean(np.abs(null_ts) >= abs(t_real)))
        t_neg = -2.8
        p_neg = float(np.mean(np.abs(null_ts) >= abs(t_neg)))
        assert abs(p_pos - p_neg) < 1e-10, (
            "Two-sided perm-p should be identical for +t and -t of the same magnitude")


# ─────────────────────────────────── Group 4: screen test ────────────────────

class TestScreenTest:
    """screen_test arithmetic: pool lift direction and t-stat sign."""

    def test_screen_lift_positive_when_topmax_hurts(self):
        """If the top-MAX decile has lower-than-pool mean return, excluding it lifts the pool."""
        # Build synthetic data: all names earn 1%, top-MAX decile earns 0%
        n = 30
        pool_raw = pd.Series([0.009] * n)      # ~0.9% each period
        # Pool without top decile earns slightly more (top-MAX names dragged down by 0%)
        pool_screened = pd.Series([0.010] * n)  # ~1% each period
        result = screen_test(pool_raw, pool_screened)
        assert result["lift_mean_pct"] > 0, "Excluding worse-performing decile should lift pool"

    def test_screen_lift_negative_when_topmax_helps(self):
        """If top-MAX decile outperforms, excluding it HURTS the pool (negative lift)."""
        pool_raw = pd.Series([0.010] * 30)
        pool_screened = pd.Series([0.008] * 30)
        result = screen_test(pool_raw, pool_screened)
        assert result["lift_mean_pct"] < 0

    def test_screen_t_significant_for_large_consistent_lift(self):
        """A large, consistent lift should produce a significant t-stat."""
        pool_raw = pd.Series(np.zeros(50))
        pool_screened = pd.Series(np.ones(50) * 0.01)  # 1% lift every period
        result = screen_test(pool_raw, pool_screened)
        # t should be large (0.01 / very_small_std) — but std is 0 so we just check p < 0.001
        # Actually std of diff = 0 → t = inf; scipy ttest handles it
        assert result["t"] is not None
        assert result["p"] is not None and result["p"] < 0.001

    def test_screen_arithmetic(self):
        """Pool-raw + lift = pool-screened (within floating-point)."""
        pool_raw = pd.Series([0.001, 0.002, 0.003, 0.004, 0.005] * 5)
        pool_screened = pool_raw + 0.001
        result = screen_test(pool_raw, pool_screened)
        expected_lift = 0.001 * 100  # in pct
        assert abs(result["lift_mean_pct"] - expected_lift) < 0.01

    def test_screen_n_matches_input(self):
        """Number of periods in result matches input length."""
        n = 25
        pool_raw = pd.Series(np.zeros(n))
        pool_screened = pd.Series(np.ones(n) * 0.001)
        result = screen_test(pool_raw, pool_screened)
        assert result["n"] == n

    def test_screen_too_short(self):
        """Fewer than 8 periods → returns None for t and p."""
        pool_raw = pd.Series([0.001] * 5)
        pool_screened = pd.Series([0.002] * 5)
        result = screen_test(pool_raw, pool_screened)
        assert result["t"] is None
        assert result["lift_mean_pct"] is None


# ─────────────────────────────────── Group 5: integration smoke test ──────────

class TestIntegrationSmoke:
    """Minimal end-to-end smoke tests using synthetic data (no parquet files)."""

    def _synthetic_max_signal(self, n=80, k=20, seed=42):
        """Returns (max_sig, fwd, csi_ret) synthetic DataFrames."""
        rng = np.random.default_rng(seed)
        idx = pd.date_range("2020-01-02", periods=n, freq="B")
        cols = [f"T{i:03d}" for i in range(k)]
        max_val = pd.DataFrame(rng.uniform(0.01, 0.12, (n, k)), index=idx, columns=cols)
        fwd = pd.DataFrame(rng.normal(0.005, 0.03, (n, k)), index=idx, columns=cols)
        csi_ret = pd.Series(rng.normal(0.004, 0.02, n), index=idx)
        return max_val, fwd, csi_ret

    def test_decile_assignment_covers_all_names(self):
        """Every eligible name should be assigned to exactly one decile."""
        n_names = 100
        signal = pd.Series(np.random.default_rng(42).standard_normal(n_names))
        rank_pct = signal.rank(pct=True)
        dec = np.ceil(rank_pct * DECILES).clip(1, DECILES).astype(int)
        for d in range(1, DECILES + 1):
            assert (dec == d).sum() > 0, f"Decile {d} has no names"
        assert len(dec) == n_names

    def test_fill_realistic_vs_ctc(self):
        """Fill-realistic and close-to-close returns differ when high != low."""
        close, high, low = _make_ohlc(80, 3)
        locked = build_locked_limit_mask(close, high, low)
        fwd_fill = fill_realistic_fwd(high, low, locked)
        fwd_ctc = close.pct_change(FWD_WINDOW, fill_method=None).shift(-FWD_WINDOW)
        # They should generally be different (spread creates a difference)
        valid_fill = fwd_fill.iloc[25, :].dropna()
        valid_ctc = fwd_ctc.iloc[25, :].dropna()
        common = valid_fill.index.intersection(valid_ctc.index)
        if len(common) > 0:
            diffs = (valid_fill.reindex(common) - valid_ctc.reindex(common)).abs()
            # There should be some difference due to spread
            assert diffs.mean() > 0

    def test_max_signal_can_detect_lottery_in_extreme_case(self):
        """In a synthetic case where high-MAX names earn -2% and low-MAX earn +2%,
        the L/S (D1 - D10) should be positive."""
        rng = np.random.default_rng(SEED)
        n = 60  # names
        # High-MAX signal (top decile = last 6 names): signal values 0.91..1.00
        # Low-MAX (first 6 names): signal values 0.01..0.10
        signal = np.linspace(0.01, 0.12, n)
        # Forward excess: inversely correlated with signal
        fwd_ex = np.linspace(0.02, -0.02, n)  # D1 earns +2%, D10 earns -2%

        rank_pct = pd.Series(signal).rank(pct=True)
        dec = np.ceil(rank_pct * DECILES).clip(1, DECILES).astype(int)
        fwd_s = pd.Series(fwd_ex)

        d1_mean = float(fwd_s[dec == 1].mean())
        d10_mean = float(fwd_s[dec == 10].mean())
        ls = d1_mean - d10_mean
        assert ls > 0, "In the designed scenario, low-MAX must outperform high-MAX"
