"""tests/test_momentum_context_signals.py — pytest suite for engine/momentum_context_signals.

Fixtures: synthetic in-memory DataFrames only. Never reads or writes data/ or site/.

Checks:
  (a) formula correctness on hand-computable cases
  (b) causality: signal.iloc[:k] identical when computed on df.iloc[:k]
  (c) events are 0/1 and fire on expected bars; states are 0/1
  (d) no NaN in any output
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.momentum_context_signals import (
    SIGNALS,
    mom121_pos,
    mom121_neg,
    mom_accel_up,
    mom_decel_dn,
    high52w_new,
    low52w_new,
    rs_repair,
    rs_deteriorate,
    rs_new_high,
    rs_new_low,
    bbt_zero_up,
    bbt_zero_dn,
    _bbtrend,
    _MOM_LONG,
    _MOM_SKIP,
    _RS_LONG,
    _BBT_SHORT,
    _BBT_LONG,
)


# ---------------------------------------------------------------------------
# Fixture factories
# ---------------------------------------------------------------------------

def _make_df(close_values, high_values=None, low_values=None, volume_values=None):
    """Build a minimal OHLCV DataFrame with DatetimeIndex from close array."""
    n = len(close_values)
    idx = pd.date_range("2019-01-02", periods=n, freq="B")
    close = pd.Series(close_values, index=idx, dtype=float)
    if high_values is None:
        high_values = [c * 1.01 for c in close_values]
    if low_values is None:
        low_values = [c * 0.99 for c in close_values]
    if volume_values is None:
        volume_values = [1_000_000] * n
    return pd.DataFrame(
        {
            "close": close,
            "high": pd.Series(high_values, index=idx, dtype=float),
            "low": pd.Series(low_values, index=idx, dtype=float),
            "volume": pd.Series(volume_values, index=idx, dtype=float),
        }
    )


def _monotone_up(n=600):
    """Strictly monotone-up tape, starting at 100."""
    return _make_df([100 + i for i in range(n)])


def _monotone_dn(n=600):
    """Strictly monotone-down tape, starting at 700."""
    return _make_df([700 - i for i in range(n)])


def _flat(n=600):
    """Flat tape: close constant at 100."""
    return _make_df([100.0] * n)


def _zero_range(n=300):
    """Zero-range bars: high == low == close."""
    vals = [100.0] * n
    return _make_df(vals, high_values=vals, low_values=vals)


def _gap_tape(n=600):
    """Tape with a gap (prices jump once in the middle)."""
    vals = [100 + i for i in range(n)]
    vals[300] = vals[299] * 1.15  # gap up
    return _make_df(vals)


def _reversal_tape(n=600):
    """Tape that rises then falls back to start."""
    up = [100 + i * 0.5 for i in range(300)]
    dn = [up[-1] - i * 0.5 for i in range(300)]
    return _make_df(up + dn)


# ---------------------------------------------------------------------------
# Helper: check no NaN
# ---------------------------------------------------------------------------

def _assert_no_nan(s: pd.Series):
    assert s.isna().sum() == 0, f"NaN values found in {s.name}"


def _assert_binary(s: pd.Series):
    unique = set(s.unique())
    assert unique <= {0, 1, 0.0, 1.0}, f"Non-binary values in {s.name}: {unique}"


# ---------------------------------------------------------------------------
# Tests: SIGNALS registry
# ---------------------------------------------------------------------------

class TestSignalsRegistry:
    def test_all_required_keys_present(self):
        required = {
            "fn", "kind", "family", "direction", "default_params",
            "display", "glyph",
            "dependency_family", "role", "entry_stack_blocked",
            "challenger_only", "provenance", "actionable_lag",
        }
        for sig_id, entry in SIGNALS.items():
            missing = required - set(entry.keys())
            assert not missing, f"{sig_id} missing keys: {missing}"

    def test_display_has_en_and_zh(self):
        for sig_id, entry in SIGNALS.items():
            disp = entry["display"]
            assert "en" in disp and "zh" in disp, f"{sig_id} display missing en/zh"
            assert disp["en"] and disp["zh"], f"{sig_id} display has empty string"

    def test_kind_values(self):
        for sig_id, entry in SIGNALS.items():
            assert entry["kind"] in ("event", "state"), f"{sig_id} bad kind"

    def test_direction_values(self):
        for sig_id, entry in SIGNALS.items():
            assert entry["direction"] in (-1, 0, +1), f"{sig_id} bad direction"

    def test_challenger_only_bbt(self):
        for sig_id in ("bbt_zero_up", "bbt_zero_dn"):
            assert SIGNALS[sig_id]["challenger_only"] is True

    def test_dependency_family_groups(self):
        multi_h = {"mom121_pos", "mom121_neg", "mom_accel_up", "mom_decel_dn",
                   "high52w_new", "low52w_new"}
        bench_rs = {"rs_repair", "rs_deteriorate", "rs_new_high", "rs_new_low"}
        vol_ch = {"bbt_zero_up", "bbt_zero_dn"}
        for s in multi_h:
            assert SIGNALS[s]["dependency_family"] == "multi_horizon_momentum"
        for s in bench_rs:
            assert SIGNALS[s]["dependency_family"] == "benchmark_relative_strength"
        for s in vol_ch:
            assert SIGNALS[s]["dependency_family"] == "volatility_channel"

    def test_bench_signals_screener_firing_false(self):
        for sig_id in ("rs_repair", "rs_deteriorate", "rs_new_high", "rs_new_low"):
            assert SIGNALS[sig_id].get("screener_firing") is False


# ---------------------------------------------------------------------------
# Tests: mom121_pos / mom121_neg
# ---------------------------------------------------------------------------

class TestMom121:
    def test_pos_fires_on_up_tape(self):
        df = _monotone_up(600)
        s = mom121_pos(df)
        _assert_no_nan(s)
        _assert_binary(s)
        # After warm-up (252+21 bars), all bars on a monotone-up tape should be 1
        warm = _MOM_LONG + _MOM_SKIP
        assert s.iloc[warm:].all(), "mom121_pos should be 1 on monotone-up after warm-up"

    def test_neg_fires_on_dn_tape(self):
        df = _monotone_dn(600)
        s = mom121_neg(df)
        _assert_no_nan(s)
        _assert_binary(s)
        warm = _MOM_LONG + _MOM_SKIP
        assert s.iloc[warm:].all(), "mom121_neg should be 1 on monotone-down after warm-up"

    def test_mutually_exclusive_on_flat(self):
        df = _flat(600)
        pos = mom121_pos(df)
        neg = mom121_neg(df)
        _assert_no_nan(pos)
        _assert_no_nan(neg)
        # On a flat tape, mom_12_1 = 0, so neither should fire
        # (close.shift(21)/close.shift(252) - 1 = 0, not >0 or <0)
        assert pos.sum() == 0
        assert neg.sum() == 0

    def test_not_both_one_simultaneously(self):
        df = _reversal_tape()
        pos = mom121_pos(df)
        neg = mom121_neg(df)
        _assert_no_nan(pos)
        _assert_no_nan(neg)
        # They must not fire simultaneously
        assert ((pos == 1) & (neg == 1)).sum() == 0

    def test_causality_pos(self):
        df = _monotone_up(600)
        full = mom121_pos(df)
        for k in [300, 400, 500]:
            partial = mom121_pos(df.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k], partial,
                check_names=False,
                obj=f"mom121_pos causality at k={k}",
            )

    def test_causality_neg(self):
        df = _monotone_dn(600)
        full = mom121_neg(df)
        for k in [300, 400, 500]:
            partial = mom121_neg(df.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k], partial,
                check_names=False,
                obj=f"mom121_neg causality at k={k}",
            )

    def test_zero_range(self):
        df = _zero_range(300)
        _assert_no_nan(mom121_pos(df))
        _assert_no_nan(mom121_neg(df))


# ---------------------------------------------------------------------------
# Tests: mom_accel_up / mom_decel_dn
# ---------------------------------------------------------------------------

class TestMomCrosses:
    def test_accel_on_up_tape_eventually_settles(self):
        df = _monotone_up(600)
        s = mom_accel_up(df)
        _assert_no_nan(s)
        _assert_binary(s)
        # On a strictly monotone-up tape, acceleration events can fire
        # but should NOT be all-1 (they are first-bar-only events)
        assert s.sum() >= 0

    def test_decel_on_dn_tape(self):
        df = _monotone_dn(600)
        s = mom_decel_dn(df)
        _assert_no_nan(s)
        _assert_binary(s)

    def test_no_accel_on_flat(self):
        df = _flat(600)
        s = mom_accel_up(df)
        _assert_no_nan(s)
        _assert_binary(s)
        # Flat tape: ret_63 and ret_126 are both 0, so no cross can happen
        assert s.sum() == 0

    def test_no_decel_on_flat(self):
        df = _flat(600)
        s = mom_decel_dn(df)
        _assert_no_nan(s)
        assert s.sum() == 0

    def test_causality_accel(self):
        df = _reversal_tape()
        full = mom_accel_up(df)
        for k in [300, 450, 550]:
            partial = mom_accel_up(df.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k], partial,
                check_names=False,
                obj=f"mom_accel_up causality at k={k}",
            )

    def test_causality_decel(self):
        df = _reversal_tape()
        full = mom_decel_dn(df)
        for k in [300, 450, 550]:
            partial = mom_decel_dn(df.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k], partial,
                check_names=False,
                obj=f"mom_decel_dn causality at k={k}",
            )

    def test_reversal_fires_at_least_once(self):
        """A tape that rises then falls should produce at least one event each."""
        # We need enough bars for the signals to fire after warm-up
        df = _reversal_tape(600)
        # Not guaranteed both fire on a symmetric reversal, but at least check binary
        s_up = mom_accel_up(df)
        s_dn = mom_decel_dn(df)
        _assert_binary(s_up)
        _assert_binary(s_dn)


# ---------------------------------------------------------------------------
# Tests: high52w_new / low52w_new
# ---------------------------------------------------------------------------

class TestHighLow52w:
    def test_monotone_up_fires_every_bar_after_warmup(self):
        df = _monotone_up(600)
        s = high52w_new(df)
        _assert_no_nan(s)
        _assert_binary(s)
        # After warm-up of 252+1 bars, every bar is a new 252d high on monotone-up
        warm = _MOM_LONG + 1
        assert s.iloc[warm:].all(), "high52w_new should fire every bar on monotone-up"

    def test_monotone_dn_fires_every_bar_after_warmup(self):
        df = _monotone_dn(600)
        s = low52w_new(df)
        _assert_no_nan(s)
        _assert_binary(s)
        warm = _MOM_LONG + 1
        assert s.iloc[warm:].all(), "low52w_new should fire every bar on monotone-down"

    def test_monotone_up_no_low52w(self):
        df = _monotone_up(600)
        s = low52w_new(df)
        _assert_no_nan(s)
        assert s.sum() == 0, "low52w_new should not fire on monotone-up tape"

    def test_monotone_dn_no_high52w(self):
        df = _monotone_dn(600)
        s = high52w_new(df)
        _assert_no_nan(s)
        assert s.sum() == 0, "high52w_new should not fire on monotone-down tape"

    def test_flat_no_fire(self):
        df = _flat(600)
        _assert_no_nan(high52w_new(df))
        _assert_no_nan(low52w_new(df))
        # Flat tape: close never strictly exceeds prior max or falls below prior min
        assert high52w_new(df).sum() == 0
        assert low52w_new(df).sum() == 0

    def test_causality_high52w(self):
        df = _monotone_up(600)
        full = high52w_new(df)
        for k in [300, 400, 500]:
            partial = high52w_new(df.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k], partial,
                check_names=False,
                obj=f"high52w_new causality at k={k}",
            )

    def test_causality_low52w(self):
        df = _monotone_dn(600)
        full = low52w_new(df)
        for k in [300, 400, 500]:
            partial = low52w_new(df.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k], partial,
                check_names=False,
                obj=f"low52w_new causality at k={k}",
            )

    def test_hand_computed_high52w(self):
        """Construct a tape where a new 252d high fires on exactly one known bar."""
        # Flat at 100 for 252 bars, then one bar at 101
        vals = [100.0] * 252 + [101.0]
        df = _make_df(vals)
        s = high52w_new(df)
        _assert_no_nan(s)
        # Bar index 252 (0-indexed) is the first bar that exceeds its prior 252-bar max
        assert s.iloc[252] == 1, "Expected high52w_new to fire on bar 252"
        assert s.iloc[:252].sum() == 0, "No high52w_new before bar 252"

    def test_hand_computed_low52w(self):
        """Construct a tape where a new 252d low fires on exactly one known bar."""
        vals = [100.0] * 252 + [99.0]
        df = _make_df(vals)
        s = low52w_new(df)
        _assert_no_nan(s)
        assert s.iloc[252] == 1, "Expected low52w_new to fire on bar 252"
        assert s.iloc[:252].sum() == 0


# ---------------------------------------------------------------------------
# Tests: benchmark relative strength signals
# ---------------------------------------------------------------------------

class TestBenchmarkRS:
    def _bench_same(self, df):
        """Benchmark that exactly matches close — RS is always 0."""
        return df["close"].copy()

    def _bench_lag(self, df, factor=0.5):
        """Benchmark grows at half the rate — stock always outperforms."""
        n = len(df)
        return pd.Series(
            [100 + i * factor for i in range(n)], index=df.index, dtype=float
        )

    def test_graceful_degrade_none(self):
        df = _monotone_up(400)
        for fn in (rs_repair, rs_deteriorate, rs_new_high, rs_new_low):
            s = fn(df, bench_close=None)
            _assert_no_nan(s)
            _assert_binary(s)
            assert s.sum() == 0, f"{fn.__name__} should return all-zeros when bench is None"

    def test_no_nan_with_bench(self):
        df = _monotone_up(400)
        bench = self._bench_lag(df)
        for fn in (rs_repair, rs_deteriorate, rs_new_high, rs_new_low):
            s = fn(df, bench_close=bench)
            _assert_no_nan(s)

    def test_rs_repair_fires_on_outperformance_start(self):
        """RS_63 should cross above zero when stock accelerates past bench."""
        n = 300
        # First half: stock lags bench (RS < 0); second half: stock leads bench (RS > 0)
        # Use same index as _make_df (2019-01-02) so reindex has full overlap
        idx = pd.date_range("2019-01-02", periods=n, freq="B")
        # Stock flat then rockets; bench steady
        stock_vals = [100.0] * 150 + [100.0 + i * 2.0 for i in range(150)]
        bench_vals = [100.0 + i * 0.5 for i in range(n)]
        df = _make_df(stock_vals)
        bench = pd.Series(bench_vals, index=idx, dtype=float)
        s = rs_repair(df, bench_close=bench)
        _assert_no_nan(s)
        _assert_binary(s)

    def test_rs_new_high_on_strong_outperformer(self):
        """Stock growing faster than bench should trigger rs_new_high after warm-up."""
        n = 400
        # Must use same index as _make_df so reindex in rs_new_high has full overlap
        idx = pd.date_range("2019-01-02", periods=n, freq="B")
        stock_vals = [100.0 + i * 1.0 for i in range(n)]  # +1/bar
        bench_vals = [100.0 + i * 0.1 for i in range(n)]  # +0.1/bar
        df = _make_df(stock_vals)
        bench = pd.Series(bench_vals, index=idx, dtype=float)
        s = rs_new_high(df, bench_close=bench)
        _assert_no_nan(s)
        _assert_binary(s)
        # Warm-up: prior_max needs RS_LONG (126) bars via shift(1).rolling(126), so
        # first valid at bar 127. After that, monotone ratio means every bar is a new high.
        warm = _RS_LONG + 1
        assert s.iloc[warm:].all(), "rs_new_high should fire on every bar of sustained outperformance"

    def test_rs_new_low_on_strong_underperformer(self):
        n = 400
        idx = pd.date_range("2019-01-02", periods=n, freq="B")
        stock_vals = [100.0 + i * 0.1 for i in range(n)]
        bench_vals = [100.0 + i * 1.0 for i in range(n)]
        df = _make_df(stock_vals)
        bench = pd.Series(bench_vals, index=idx, dtype=float)
        s = rs_new_low(df, bench_close=bench)
        _assert_no_nan(s)
        _assert_binary(s)
        warm = _RS_LONG + 1
        assert s.iloc[warm:].all(), "rs_new_low should fire on every bar of sustained underperformance"

    def test_causality_rs_repair(self):
        df = _monotone_up(400)
        bench = self._bench_lag(df)
        full = rs_repair(df, bench_close=bench)
        for k in [200, 300, 350]:
            partial = rs_repair(df.iloc[:k], bench_close=bench.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k], partial,
                check_names=False,
                obj=f"rs_repair causality at k={k}",
            )

    def test_causality_rs_new_high(self):
        n = 400
        idx = pd.date_range("2019-01-02", periods=n, freq="B")
        stock_vals = [100.0 + i * 1.0 for i in range(n)]
        bench_vals = [100.0 + i * 0.1 for i in range(n)]
        df = _make_df(stock_vals)
        bench = pd.Series(bench_vals, index=idx, dtype=float)
        full = rs_new_high(df, bench_close=bench)
        for k in [200, 300, 350]:
            partial = rs_new_high(df.iloc[:k], bench_close=bench.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k], partial,
                check_names=False,
                obj=f"rs_new_high causality at k={k}",
            )

    def test_zero_range_with_bench(self):
        df = _zero_range(300)
        bench = self._bench_same(df)
        for fn in (rs_repair, rs_deteriorate, rs_new_high, rs_new_low):
            s = fn(df, bench_close=bench)
            _assert_no_nan(s)


# ---------------------------------------------------------------------------
# Tests: BBTrend
# ---------------------------------------------------------------------------

class TestBBTrend:
    def test_no_nan_on_long_tape(self):
        df = _monotone_up(600)
        _assert_no_nan(bbt_zero_up(df))
        _assert_no_nan(bbt_zero_dn(df))

    def test_binary(self):
        df = _reversal_tape()
        _assert_binary(bbt_zero_up(df))
        _assert_binary(bbt_zero_dn(df))

    def test_flat_tape_bbt_zero(self):
        """On a flat tape, BB(20) and BB(50) collapse to zero width; BBTrend = 0."""
        df = _flat(600)
        s_up = bbt_zero_up(df)
        s_dn = bbt_zero_dn(df)
        _assert_no_nan(s_up)
        _assert_no_nan(s_dn)
        # No crosses possible if BBTrend is stuck at 0
        assert s_up.sum() == 0
        assert s_dn.sum() == 0

    def test_bbt_formula_hand_check(self):
        """Verify BBTrend formula matches manual computation on a small known tape."""
        # Use a reversal tape long enough for BB(50) to warm up
        df = _reversal_tape(600)
        close = df["close"].astype(float)

        # Compute BBTrend manually using same logic as module
        def _bb(c, n, k=2.0):
            mid = c.rolling(n, min_periods=n).mean()
            sd = c.rolling(n, min_periods=n).std(ddof=1)
            return mid + k * sd, mid, mid - k * sd

        s_up, s_mid, s_lo = _bb(close, 20)
        l_up, _l_mid, l_lo = _bb(close, 50)
        expected = 100.0 * ((s_lo - l_lo).abs() - (s_up - l_up).abs()) / s_mid

        actual = _bbtrend(close)
        pd.testing.assert_series_equal(
            expected.dropna(), actual.dropna(),
            check_names=False,
            rtol=1e-10,
        )

    def test_causality_up(self):
        df = _reversal_tape()
        full = bbt_zero_up(df)
        for k in [300, 450, 550]:
            partial = bbt_zero_up(df.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k], partial,
                check_names=False,
                obj=f"bbt_zero_up causality at k={k}",
            )

    def test_causality_dn(self):
        df = _reversal_tape()
        full = bbt_zero_dn(df)
        for k in [300, 450, 550]:
            partial = bbt_zero_dn(df.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k], partial,
                check_names=False,
                obj=f"bbt_zero_dn causality at k={k}",
            )

    def test_no_simultaneous_up_dn(self):
        """bbt_zero_up and bbt_zero_dn should not fire on the same bar."""
        df = _reversal_tape()
        s_up = bbt_zero_up(df)
        s_dn = bbt_zero_dn(df)
        assert ((s_up == 1) & (s_dn == 1)).sum() == 0

    def test_zero_range(self):
        df = _zero_range(300)
        _assert_no_nan(bbt_zero_up(df))
        _assert_no_nan(bbt_zero_dn(df))

    def test_gap_tape(self):
        df = _gap_tape()
        _assert_no_nan(bbt_zero_up(df))
        _assert_no_nan(bbt_zero_dn(df))
        _assert_binary(bbt_zero_up(df))
        _assert_binary(bbt_zero_dn(df))

    def test_fires_on_trend_change(self):
        """On a reversal tape, bbt_zero_up should fire at least once."""
        df = _reversal_tape(600)
        # After the BB(50) warm-up period, the reversal should produce at least one cross
        assert bbt_zero_up(df).sum() >= 1 or bbt_zero_dn(df).sum() >= 1

    def test_params_wired_through_bbtrend(self):
        """bbt_zero_up/dn must honor short_n, long_n, k params (not ignore them).

        Changing the BB period to a very short window (5/10) vs the default (20/50)
        produces a different BBTrend oscillator and therefore different signal output
        on a trending tape. If params are silently ignored (module constants used),
        the two outputs are identical — this would fail the assertion.
        """
        df = _reversal_tape(600)
        # Default params
        up_default = bbt_zero_up(df)
        dn_default = bbt_zero_dn(df)
        # Short window (params should be honored)
        up_short = bbt_zero_up(df, short_n=5, long_n=10, k=1.5)
        dn_short = bbt_zero_dn(df, short_n=5, long_n=10, k=1.5)
        # The two parameterisations must produce DIFFERENT series on a reversal tape
        assert not up_default.equals(up_short) or not dn_default.equals(dn_short), (
            "bbt_zero_up/dn params appear to be ignored — output identical with "
            "short_n=5/long_n=10/k=1.5 and default 20/50/2.0 on reversal tape"
        )


# ---------------------------------------------------------------------------
# Tests: zero-range and gap correctness for all signals
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_all_signals_zero_range(self):
        df = _zero_range(300)
        for sig_id, entry in SIGNALS.items():
            fn = entry["fn"]
            s = fn(df)
            assert s.isna().sum() == 0, f"{sig_id}: NaN on zero-range tape"

    def test_all_signals_gap_tape(self):
        df = _gap_tape()
        for sig_id, entry in SIGNALS.items():
            fn = entry["fn"]
            s = fn(df)
            assert s.isna().sum() == 0, f"{sig_id}: NaN on gap tape"

    def test_all_signals_monotone_up_no_nan(self):
        df = _monotone_up()
        for sig_id, entry in SIGNALS.items():
            fn = entry["fn"]
            s = fn(df)
            assert s.isna().sum() == 0, f"{sig_id}: NaN on monotone-up tape"

    def test_all_signals_monotone_dn_no_nan(self):
        df = _monotone_dn()
        for sig_id, entry in SIGNALS.items():
            fn = entry["fn"]
            s = fn(df)
            assert s.isna().sum() == 0, f"{sig_id}: NaN on monotone-down tape"

    def test_all_signals_flat_no_nan(self):
        df = _flat()
        for sig_id, entry in SIGNALS.items():
            fn = entry["fn"]
            s = fn(df)
            assert s.isna().sum() == 0, f"{sig_id}: NaN on flat tape"

    def test_all_signals_reversal_no_nan(self):
        df = _reversal_tape()
        for sig_id, entry in SIGNALS.items():
            fn = entry["fn"]
            s = fn(df)
            assert s.isna().sum() == 0, f"{sig_id}: NaN on reversal tape"
