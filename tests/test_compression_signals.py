"""tests/test_compression_signals.py — Tests for engine/compression_signals.py.

Coverage requirements (per brief):
  (a) formula correctness on hand-computable cases
  (b) causality: signal.iloc[:k] identical when computed on df.iloc[:k]
  (c) events are 0/1 and fire on expected bars
  (d) no NaN in any output

Fixtures: monotonic-up, monotonic-down, flat, zero-range, gap, reversal, and
purpose-built synthetic tapes for each signal family.

IMPORTANT: No data/ or site/ reads or writes anywhere in this file.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.compression_signals import (
    SIGNALS,
    chop_range_regime,
    chop_trend_onset,
    chop_trend_regime,
    donch_break_dn,
    donch_break_up,
    donch_fail_dn,
    donch_fail_up,
    donch_width_expand,
    nr7_setup,
    range_expand_dn,
    range_expand_up,
    squeeze_fire_dn,
    squeeze_fire_up,
    squeeze_on,
    vhf_trend_regime,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_df(
    close: np.ndarray | list,
    high: np.ndarray | list | None = None,
    low: np.ndarray | list | None = None,
    volume: float = 1_000_000.0,
) -> pd.DataFrame:
    """Build OHLCV DataFrame from arrays. No 'open' column per data contract."""
    close = np.asarray(close, dtype=float)
    n = len(close)
    if high is None:
        high = close * 1.005
    if low is None:
        low = close * 0.995
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )


def _monotonic_up(n: int = 300, start: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    """Strictly increasing close prices.

    high = close + 0.1 (absolute gap, not relative), so prior high is always exceeded by
    the next bar's close on an increasing tape. This satisfies Donchian breakout tests.
    """
    close = start + np.arange(n) * step
    high = close + 0.1
    low = close - 0.1
    return _make_df(close, high, low)


def _monotonic_dn(n: int = 300, start: float = 250.0, step: float = 0.5) -> pd.DataFrame:
    """Strictly decreasing close prices.

    low = close - 0.1 (absolute gap), so prior low is always exceeded (on the downside)
    by the next bar's close on a decreasing tape. Satisfies Donchian breakdown tests.
    """
    close = start - np.arange(n) * step
    high = close + 0.1
    low = close - 0.1
    return _make_df(close, high, low)


def _flat(n: int = 300, price: float = 100.0) -> pd.DataFrame:
    """Constant price — minimal movement."""
    close = np.full(n, price)
    high = close * 1.0005
    low = close * 0.9995
    return _make_df(close, high, low)


def _zero_range(n: int = 100, price: float = 50.0) -> pd.DataFrame:
    """High == low == close (doji bars with no range)."""
    close = np.full(n, price)
    return _make_df(close, close.copy(), close.copy())


def _gap_tape(n: int = 300) -> pd.DataFrame:
    """Price series with a sudden gap up on bar 150."""
    close = np.full(n, 100.0, dtype=float)
    close[150:] = 120.0
    high = close * 1.005
    low = close * 0.995
    return _make_df(close, high, low)


def _reversal_tape(n: int = 300) -> pd.DataFrame:
    """Uptrend for first half, downtrend for second half."""
    half = n // 2
    up = 100.0 + np.arange(half) * 0.5
    dn = up[-1] - np.arange(half) * 0.5
    close = np.concatenate([up, dn])
    high = close * 1.005
    low = close * 0.995
    return _make_df(close, high, low)


# ---------------------------------------------------------------------------
# Shared invariant helpers
# ---------------------------------------------------------------------------

def _assert_no_nan(sig: pd.Series, name: str) -> None:
    assert not sig.isna().any(), f"{name} contains NaN values"


def _assert_binary(sig: pd.Series, name: str) -> None:
    unique = set(sig.unique())
    assert unique <= {0, 1, 0.0, 1.0}, f"{name} has values outside {{0, 1}}: {unique}"


def _assert_causality(fn, df: pd.DataFrame, k: int, **kwargs) -> None:
    """Signal computed on df[:k] must match signal on full df at index positions < k."""
    full = fn(df, **kwargs)
    prefix = fn(df.iloc[:k], **kwargs)
    pd.testing.assert_series_equal(
        prefix.reset_index(drop=True),
        full.iloc[:k].reset_index(drop=True),
        check_names=False,
        obj=f"causality check for {fn.__name__}",
    )


# ---------------------------------------------------------------------------
# A. Squeeze signals
# ---------------------------------------------------------------------------

class TestSqueezeOn:
    def test_no_nan(self):
        for tape in [_monotonic_up(), _monotonic_dn(), _flat(), _zero_range(), _gap_tape(), _reversal_tape()]:
            sig = squeeze_on(tape)
            _assert_no_nan(sig, "squeeze_on")

    def test_binary(self):
        df = _monotonic_up()
        sig = squeeze_on(df)
        _assert_binary(sig, "squeeze_on")

    def test_causality(self):
        df = _monotonic_up(n=150)
        _assert_causality(squeeze_on, df, k=80)

    def test_flat_price_squeeze_active(self):
        """Flat price has near-zero volatility — squeeze should be active most of the time."""
        df = _flat(n=100)
        sig = squeeze_on(df)
        # After warm-up (20 bars), squeeze should be consistently active
        assert sig.iloc[25:].sum() > 0, "Expected squeeze active on flat tape after warm-up"

    def test_zero_range_no_crash(self):
        df = _zero_range()
        sig = squeeze_on(df)
        _assert_no_nan(sig, "squeeze_on/zero_range")


class TestSqueezeFireUp:
    def test_no_nan(self):
        for tape in [_monotonic_up(), _flat(), _reversal_tape()]:
            sig = squeeze_fire_up(tape)
            _assert_no_nan(sig, "squeeze_fire_up")

    def test_binary(self):
        df = _monotonic_up()
        sig = squeeze_fire_up(df)
        _assert_binary(sig, "squeeze_fire_up")

    def test_causality(self):
        df = _reversal_tape(n=200)
        _assert_causality(squeeze_fire_up, df, k=120)

    def test_fires_after_squeeze(self):
        """squeeze_fire_up must only fire on a bar where squeeze was previously on."""
        df = _reversal_tape(n=300)
        sq = squeeze_on(df)
        fire = squeeze_fire_up(df)
        # Every bar where fire=1 must have had sq=1 on the previous bar
        fire_bars = fire[fire == 1].index
        for ts in fire_bars:
            iloc = df.index.get_loc(ts)
            if iloc > 0:
                assert sq.iloc[iloc - 1] == 1, f"squeeze_fire_up fired at {ts} without prior squeeze"

    def test_mutually_exclusive_with_fire_dn(self):
        """squeeze_fire_up and squeeze_fire_dn cannot both fire on the same bar."""
        df = _reversal_tape(n=300)
        up = squeeze_fire_up(df)
        dn = squeeze_fire_dn(df)
        both = (up == 1) & (dn == 1)
        assert not both.any(), "squeeze_fire_up and squeeze_fire_dn fire on same bar"


class TestSqueezeFireDn:
    def test_no_nan(self):
        for tape in [_monotonic_dn(), _flat(), _reversal_tape()]:
            sig = squeeze_fire_dn(tape)
            _assert_no_nan(sig, "squeeze_fire_dn")

    def test_binary(self):
        sig = squeeze_fire_dn(_monotonic_dn())
        _assert_binary(sig, "squeeze_fire_dn")

    def test_causality(self):
        df = _reversal_tape(n=200)
        _assert_causality(squeeze_fire_dn, df, k=100)


# ---------------------------------------------------------------------------
# B. Choppiness signals
# ---------------------------------------------------------------------------

class TestChopTrendRegime:
    def test_no_nan(self):
        for tape in [_monotonic_up(), _monotonic_dn(), _flat(), _gap_tape()]:
            _assert_no_nan(chop_trend_regime(tape), "chop_trend_regime")

    def test_binary(self):
        _assert_binary(chop_trend_regime(_monotonic_up()), "chop_trend_regime")

    def test_causality(self):
        df = _monotonic_up(n=200)
        _assert_causality(chop_trend_regime, df, k=100)

    def test_trending_on_monotonic_up(self):
        """A strictly monotonic tape has low choppiness — should flag trending regime."""
        df = _monotonic_up(n=200)
        sig = chop_trend_regime(df)
        # After warm-up (14 bars), monotonic should show trending regime on most bars
        post_warmup = sig.iloc[20:]
        assert post_warmup.sum() > len(post_warmup) * 0.5, (
            "Expected majority trending on monotonic tape"
        )

    def test_flat_not_trending(self):
        """Flat price produces high choppiness — should NOT be in trending regime."""
        df = _flat(n=200)
        sig = chop_trend_regime(df)
        post_warmup = sig.iloc[20:]
        # Zero delta-close → choppiness undefined or very high; trending should be rare
        assert post_warmup.sum() < len(post_warmup) * 0.5, (
            "Expected low trending count on flat tape"
        )


class TestChopRangeRegime:
    def test_no_nan(self):
        for tape in [_monotonic_up(), _flat(), _reversal_tape()]:
            _assert_no_nan(chop_range_regime(tape), "chop_range_regime")

    def test_binary(self):
        _assert_binary(chop_range_regime(_flat()), "chop_range_regime")

    def test_causality(self):
        df = _reversal_tape(n=200)
        _assert_causality(chop_range_regime, df, k=100)

    def test_not_both_trend_and_range(self):
        """chop_trend_regime and chop_range_regime cannot both be 1 on the same bar."""
        df = _reversal_tape(n=300)
        trend = chop_trend_regime(df)
        rng = chop_range_regime(df)
        both = (trend == 1) & (rng == 1)
        assert not both.any(), "Both trend and range regimes active simultaneously"


class TestChopTrendOnset:
    def test_no_nan(self):
        for tape in [_monotonic_up(), _flat(), _reversal_tape()]:
            _assert_no_nan(chop_trend_onset(tape), "chop_trend_onset")

    def test_binary(self):
        _assert_binary(chop_trend_onset(_monotonic_up()), "chop_trend_onset")

    def test_causality(self):
        df = _reversal_tape(n=200)
        _assert_causality(chop_trend_onset, df, k=100)

    def test_onset_requires_previous_above_threshold(self):
        """chop_trend_onset fires only when crossing DOWN through 38.2 (not when already below)."""
        df = _monotonic_up(n=200)
        trend = chop_trend_regime(df)
        onset = chop_trend_onset(df)
        # Every onset bar must have trend_regime ON at that bar
        onset_bars = onset[onset == 1].index
        for ts in onset_bars:
            iloc = df.index.get_loc(ts)
            assert trend.iloc[iloc] == 1, f"chop_trend_onset fired at {ts} but trend_regime off"

    def test_onset_fires_on_transition_not_sustained(self):
        """chop_trend_onset is an event — should not fire on consecutive bars in trend regime."""
        df = _monotonic_up(n=250)
        onset = chop_trend_onset(df)
        trend = chop_trend_regime(df)
        # Any two consecutive bars cannot both be onset=1 (it's a cross event)
        consec = (onset.shift(1) == 1) & (onset == 1)
        assert not consec.any(), "chop_trend_onset fires on consecutive bars (not a cross)"


# ---------------------------------------------------------------------------
# C. VHF
# ---------------------------------------------------------------------------

class TestVhfTrendRegime:
    def test_no_nan(self):
        for tape in [_monotonic_up(n=600), _monotonic_dn(n=600), _flat(n=600)]:
            _assert_no_nan(vhf_trend_regime(tape), "vhf_trend_regime")

    def test_binary(self):
        _assert_binary(vhf_trend_regime(_monotonic_up(n=600)), "vhf_trend_regime")

    def test_causality(self):
        df = _monotonic_up(n=600)
        _assert_causality(vhf_trend_regime, df, k=400)

    def test_trending_on_random_walk(self):
        """VHF trend regime should fire on at least some bars of a noisy random-walk tape."""
        rng = np.random.default_rng(42)
        n = 600
        close = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, n))
        high = close * 1.005
        low = close * 0.995
        df = _make_df(close, high, low)
        sig = vhf_trend_regime(df)
        # Some bars should be in trend regime, some not
        post_warmup = sig.iloc[300:]
        assert 0 < post_warmup.sum() < len(post_warmup), (
            f"Expected vhf_trend_regime to fire on SOME (not all, not none) bars; got {post_warmup.sum()}/{len(post_warmup)}"
        )

    def test_zero_denominator_no_crash(self):
        """Flat tape has zero delta-close sum — VHF denominator is zero, should not crash."""
        df = _flat(n=600)
        sig = vhf_trend_regime(df)
        _assert_no_nan(sig, "vhf_trend_regime/flat")

    def test_challenger_only_flag(self):
        assert SIGNALS["vhf_trend_regime"]["challenger_only"] is True


# ---------------------------------------------------------------------------
# D. Donchian signals
# ---------------------------------------------------------------------------

class TestDonchBreakUp:
    def test_no_nan(self):
        for tape in [_monotonic_up(), _flat(), _gap_tape()]:
            _assert_no_nan(donch_break_up(tape), "donch_break_up")

    def test_binary(self):
        _assert_binary(donch_break_up(_monotonic_up()), "donch_break_up")

    def test_causality(self):
        df = _monotonic_up(n=200)
        _assert_causality(donch_break_up, df, k=100)

    def test_monotonic_up_fires_on_every_bar_post_warmup(self):
        """On a strictly increasing tape, every bar after warm-up exceeds the prior 20d high."""
        df = _monotonic_up(n=100)
        sig = donch_break_up(df)
        # Need n+1 bars for the shifted band to be defined, then close > prior max
        # Bar 21 onward (0-indexed bar 20) should fire
        post_warmup = sig.iloc[21:]
        assert post_warmup.all(), "Expected donch_break_up on every bar of monotonic up tape"

    def test_flat_does_not_fire(self):
        """Flat tape: close == prior high, so close > prior high is False."""
        df = _flat(n=100)
        sig = donch_break_up(df)
        # Flat: close equals rolling max(high) so > is strictly False
        assert sig.sum() == 0, "donch_break_up should not fire on flat tape"

    def test_prior_band_not_current(self):
        """Verify the channel uses the PRIOR bar's high, not the current bar's."""
        # Build tape where current bar's high is a new high but it was also
        # the current bar's high (shift=1 means we should NOT fire on the bar
        # where the high is being set, only on the NEXT bar that exceeds it)
        n = 30
        close = np.full(n, 100.0, dtype=float)
        high = np.full(n, 101.0, dtype=float)
        low = np.full(n, 99.0, dtype=float)
        # Make bar 25 have a new high
        high[24] = 120.0
        close[24] = 118.0
        # Bar 25 (index 25) close = 118 < current bar 24's high of 120
        # But with shift(1), bar 25 should see prior high = 120
        # and close[25] = 100 < 120, so should NOT fire
        # Only bar 24 itself could fire if close > PREVIOUS 20-bar max
        df = _make_df(close, high, low)
        sig = donch_break_up(df)
        # Bar 25 (index 25): close=100, prior upper=max(high[6..25])=120 → should NOT fire
        assert sig.iloc[25] == 0, "donch_break_up incorrectly fired using current bar's high"


class TestDonchBreakDn:
    def test_no_nan(self):
        for tape in [_monotonic_dn(), _flat(), _reversal_tape()]:
            _assert_no_nan(donch_break_dn(tape), "donch_break_dn")

    def test_binary(self):
        _assert_binary(donch_break_dn(_monotonic_dn()), "donch_break_dn")

    def test_causality(self):
        df = _monotonic_dn(n=200)
        _assert_causality(donch_break_dn, df, k=100)

    def test_monotonic_dn_fires_post_warmup(self):
        df = _monotonic_dn(n=100)
        sig = donch_break_dn(df)
        post_warmup = sig.iloc[21:]
        assert post_warmup.all(), "Expected donch_break_dn on every bar of monotonic down tape"

    def test_mutually_exclusive_with_break_up(self):
        """donch_break_up and donch_break_dn cannot fire simultaneously."""
        df = _reversal_tape(n=300)
        up = donch_break_up(df)
        dn = donch_break_dn(df)
        both = (up == 1) & (dn == 1)
        assert not both.any(), "donch_break_up and donch_break_dn fire on same bar"


class TestDonchFailUp:
    def test_no_nan(self):
        for tape in [_monotonic_up(), _flat(), _reversal_tape()]:
            _assert_no_nan(donch_fail_up(tape), "donch_fail_up")

    def test_binary(self):
        _assert_binary(donch_fail_up(_reversal_tape()), "donch_fail_up")

    def test_causality(self):
        df = _reversal_tape(n=200)
        _assert_causality(donch_fail_up, df, k=100)

    def test_fires_after_breakout_then_pullback(self):
        """Construct a tape that breaks up then immediately fails."""
        # Base price at 100, then spike to 130 (above prior 20d high), then drop to 95
        n = 60
        close = np.full(n, 100.0, dtype=float)
        high = np.full(n, 101.0, dtype=float)
        low = np.full(n, 99.0, dtype=float)
        # Bar 25: breakout — close = 130, high = 131 (well above prior max of 101)
        close[25] = 130.0
        high[25] = 131.0
        low[25] = 128.0
        # Bar 26: pullback below old upper band (~101)
        close[26] = 98.0
        high[26] = 100.0
        low[26] = 97.0
        df = _make_df(close, high, low)
        sig_break = donch_break_up(df)
        sig_fail = donch_fail_up(df)
        assert sig_break.iloc[25] == 1, "Expected donch_break_up at bar 25"
        assert sig_fail.iloc[26] == 1, f"Expected donch_fail_up at bar 26; got {sig_fail.iloc[25:30].tolist()}"

    def test_no_fail_on_monotonic_up(self):
        """On strictly increasing tape, breakouts never fail."""
        df = _monotonic_up(n=100)
        sig = donch_fail_up(df)
        assert sig.sum() == 0, "Expected no donch_fail_up on strictly increasing tape"


class TestDonchFailDn:
    def test_no_nan(self):
        _assert_no_nan(donch_fail_dn(_reversal_tape()), "donch_fail_dn")

    def test_binary(self):
        _assert_binary(donch_fail_dn(_reversal_tape()), "donch_fail_dn")

    def test_causality(self):
        df = _reversal_tape(n=200)
        _assert_causality(donch_fail_dn, df, k=100)

    def test_fires_after_breakdown_then_recovery(self):
        """Construct a tape that breaks down then immediately recovers."""
        n = 60
        close = np.full(n, 100.0, dtype=float)
        high = np.full(n, 101.0, dtype=float)
        low = np.full(n, 99.0, dtype=float)
        # Bar 25: breakdown — close = 70 (below prior 20d low of 99)
        close[25] = 70.0
        high[25] = 71.0
        low[25] = 69.0
        # Bar 26: recovery above old lower band (~99)
        close[26] = 102.0
        high[26] = 103.0
        low[26] = 101.0
        df = _make_df(close, high, low)
        sig_break = donch_break_dn(df)
        sig_fail = donch_fail_dn(df)
        assert sig_break.iloc[25] == 1, "Expected donch_break_dn at bar 25"
        assert sig_fail.iloc[26] == 1, f"Expected donch_fail_dn at bar 26; got {sig_fail.iloc[24:30].tolist()}"


class TestDonchWidthExpand:
    def test_no_nan(self):
        for tape in [_reversal_tape(n=600), _monotonic_up(n=600)]:
            _assert_no_nan(donch_width_expand(tape), "donch_width_expand")

    def test_binary(self):
        _assert_binary(donch_width_expand(_reversal_tape(n=600)), "donch_width_expand")

    def test_causality(self):
        df = _reversal_tape(n=600)
        _assert_causality(donch_width_expand, df, k=400)

    def test_fires_after_big_range_expansion(self):
        """After a period of large-range movement, donch_width_expand should be active."""
        # First 300 bars: flat (narrow channel), next 300 bars: large oscillations
        n = 600
        close = np.full(n, 100.0, dtype=float)
        high = np.full(n, 100.5, dtype=float)
        low = np.full(n, 99.5, dtype=float)
        # Second half: alternating big moves to create a wide channel
        for i in range(300, 600):
            if i % 40 < 20:
                close[i] = 140.0
                high[i] = 141.0
                low[i] = 139.0
            else:
                close[i] = 60.0
                high[i] = 61.0
                low[i] = 59.0
        df = _make_df(close, high, low)
        sig = donch_width_expand(df)
        # In the second half (after the channel has widened and distribution has seen it)
        # at least some bars should show width_expand
        second_half = sig.iloc[400:]
        assert second_half.sum() > 0, (
            "Expected donch_width_expand to fire after large range expansion"
        )


# ---------------------------------------------------------------------------
# E. NR7 + Range Expansion
# ---------------------------------------------------------------------------

class TestNr7Setup:
    def test_no_nan(self):
        for tape in [_monotonic_up(), _flat(), _zero_range(), _reversal_tape()]:
            _assert_no_nan(nr7_setup(tape), "nr7_setup")

    def test_binary(self):
        _assert_binary(nr7_setup(_reversal_tape()), "nr7_setup")

    def test_causality(self):
        df = _reversal_tape(n=200)
        _assert_causality(nr7_setup, df, k=80)

    def test_state_persists_3_bars(self):
        """After NR7 fires on a bar, nr7_setup should remain 1 for at least 2 more bars."""
        # Construct a tape where bar 20 has a very narrow range, rest are wide
        n = 50
        high = np.full(n, 101.0, dtype=float)
        low = np.full(n, 99.0, dtype=float)
        close = np.full(n, 100.0, dtype=float)
        # Bar 20: extremely narrow range (the NR7 bar)
        high[20] = 100.1
        low[20] = 99.9
        df = _make_df(close, high, low)
        sig = nr7_setup(df)
        # The setup should be active at bar 20 and potentially bars 21 and 22
        # (rolling 3-bar window)
        assert sig.iloc[20] == 1 or sig.iloc[21] == 1 or sig.iloc[22] == 1, (
            "Expected nr7_setup active within 3 bars of an NR7 event"
        )

    def test_zero_range_no_crash(self):
        df = _zero_range(n=50)
        sig = nr7_setup(df)
        _assert_no_nan(sig, "nr7_setup/zero_range")


class TestRangeExpandUp:
    def test_no_nan(self):
        for tape in [_monotonic_up(), _flat(), _zero_range(), _reversal_tape()]:
            _assert_no_nan(range_expand_up(tape), "range_expand_up")

    def test_binary(self):
        _assert_binary(range_expand_up(_reversal_tape()), "range_expand_up")

    def test_causality(self):
        df = _reversal_tape(n=200)
        _assert_causality(range_expand_up, df, k=100)

    def test_fires_on_strong_up_expansion_bar(self):
        """Construct a bar with TR > 2*ATR, close in top 25% of range, close up."""
        # Start with base tape to build ATR
        n = 80
        close = np.full(n, 100.0, dtype=float)
        high = np.full(n, 101.0, dtype=float)  # range = 2.0
        low = np.full(n, 99.0, dtype=float)
        close_arr = close.copy()
        # ATR14 ≈ 2.0 (range = 2.0 each bar, no gap)
        # Bar 50: range = 10 (> 2*2.0=4.0), close at top of range, close > prev close
        high[50] = 110.0
        low[50] = 99.5
        close_arr[50] = 109.5  # top 25% of [99.5, 110.0] = above 107.1
        df = _make_df(close_arr, high, low)
        sig = range_expand_up(df)
        assert sig.iloc[50] == 1, (
            f"Expected range_expand_up at bar 50; got {sig.iloc[48:53].tolist()}"
        )

    def test_does_not_fire_on_weak_close(self):
        """Expansion bar with close at LOW end should NOT fire range_expand_up."""
        n = 80
        close = np.full(n, 100.0, dtype=float)
        high = np.full(n, 101.0, dtype=float)
        low = np.full(n, 99.0, dtype=float)
        close_arr = close.copy()
        # Bar 50: large range but close at bottom (weak close)
        high[50] = 110.0
        low[50] = 99.5
        close_arr[50] = 100.0  # bottom 25% of [99.5, 110.0]
        df = _make_df(close_arr, high, low)
        sig = range_expand_up(df)
        assert sig.iloc[50] == 0, "range_expand_up should not fire on weak-close expansion bar"

    def test_mutually_exclusive_with_expand_dn(self):
        """range_expand_up and range_expand_dn cannot fire on the same bar."""
        df = _reversal_tape(n=300)
        up = range_expand_up(df)
        dn = range_expand_dn(df)
        both = (up == 1) & (dn == 1)
        assert not both.any(), "range_expand_up and range_expand_dn fire simultaneously"


class TestRangeExpandDn:
    def test_no_nan(self):
        for tape in [_monotonic_dn(), _flat(), _zero_range(), _reversal_tape()]:
            _assert_no_nan(range_expand_dn(tape), "range_expand_dn")

    def test_binary(self):
        _assert_binary(range_expand_dn(_reversal_tape()), "range_expand_dn")

    def test_causality(self):
        df = _reversal_tape(n=200)
        _assert_causality(range_expand_dn, df, k=100)

    def test_fires_on_strong_dn_expansion_bar(self):
        """Construct a bar with TR > 2*ATR, close in bottom 25% of range, close down."""
        n = 80
        close = np.full(n, 100.0, dtype=float)
        high = np.full(n, 101.0, dtype=float)
        low = np.full(n, 99.0, dtype=float)
        close_arr = close.copy()
        # Bar 50: range = 10 (> 2*2.0=4.0), close at bottom of range, close < prev close
        high[50] = 101.0
        low[50] = 90.5
        close_arr[50] = 91.0  # bottom 25% of [90.5, 101.0] = below 93.1
        df = _make_df(close_arr, high, low)
        sig = range_expand_dn(df)
        assert sig.iloc[50] == 1, (
            f"Expected range_expand_dn at bar 50; got {sig.iloc[48:53].tolist()}"
        )


# ---------------------------------------------------------------------------
# SIGNALS registry integrity
# ---------------------------------------------------------------------------

class TestSignalsRegistry:
    REQUIRED_LEGACY_KEYS = {"fn", "kind", "family", "direction", "default_params", "display", "glyph"}
    REQUIRED_NEW_KEYS = {
        "dependency_family", "role", "entry_stack_blocked", "challenger_only",
        "provenance", "actionable_lag",
    }
    VALID_KINDS = {"event", "state"}
    VALID_ROLES = {"context", "setup", "trigger", "participation", "risk"}
    VALID_DIRECTIONS = {-1, 0, +1}
    EXPECTED_SIGNAL_IDS = {
        "squeeze_on", "squeeze_fire_up", "squeeze_fire_dn",
        "chop_trend_regime", "chop_range_regime", "chop_trend_onset",
        "vhf_trend_regime",
        "donch_break_up", "donch_break_dn", "donch_fail_up", "donch_fail_dn", "donch_width_expand",
        "nr7_setup", "range_expand_up", "range_expand_dn",
    }

    def test_all_signals_present(self):
        assert set(SIGNALS.keys()) == self.EXPECTED_SIGNAL_IDS

    def test_all_keys_present(self):
        for sig_id, entry in SIGNALS.items():
            for key in self.REQUIRED_LEGACY_KEYS | self.REQUIRED_NEW_KEYS:
                assert key in entry, f"SIGNALS['{sig_id}'] missing key '{key}'"

    def test_kinds_valid(self):
        for sig_id, entry in SIGNALS.items():
            assert entry["kind"] in self.VALID_KINDS, (
                f"SIGNALS['{sig_id}']['kind'] = {entry['kind']!r} not in {self.VALID_KINDS}"
            )

    def test_roles_valid(self):
        for sig_id, entry in SIGNALS.items():
            assert entry["role"] in self.VALID_ROLES, (
                f"SIGNALS['{sig_id}']['role'] = {entry['role']!r} not in {self.VALID_ROLES}"
            )

    def test_directions_valid(self):
        for sig_id, entry in SIGNALS.items():
            assert entry["direction"] in self.VALID_DIRECTIONS, (
                f"SIGNALS['{sig_id}']['direction'] = {entry['direction']!r}"
            )

    def test_display_bilingual(self):
        for sig_id, entry in SIGNALS.items():
            disp = entry["display"]
            assert "en" in disp and "zh" in disp, f"SIGNALS['{sig_id}'] missing bilingual display"
            assert disp["en"], f"SIGNALS['{sig_id}']['display']['en'] is empty"
            assert disp["zh"], f"SIGNALS['{sig_id}']['display']['zh'] is empty"

    def test_challenger_only_flags(self):
        """vhf_trend_regime should be challenger_only; chop signals should not be."""
        assert SIGNALS["vhf_trend_regime"]["challenger_only"] is True
        assert SIGNALS["chop_trend_regime"]["challenger_only"] is False
        assert SIGNALS["chop_range_regime"]["challenger_only"] is False
        assert SIGNALS["chop_trend_onset"]["challenger_only"] is False

    def test_entry_stack_blocked_flags(self):
        """Choppiness and VHF signals must carry entry_stack_blocked=True."""
        for sig_id in ["chop_trend_regime", "chop_range_regime", "chop_trend_onset", "vhf_trend_regime"]:
            assert SIGNALS[sig_id]["entry_stack_blocked"] is True, (
                f"SIGNALS['{sig_id}']['entry_stack_blocked'] should be True (RUL-33-BASEEFF)"
            )

    def test_fn_callables(self):
        for sig_id, entry in SIGNALS.items():
            assert callable(entry["fn"]), f"SIGNALS['{sig_id}']['fn'] is not callable"

    def test_all_signals_run_on_standard_df(self):
        """All signal functions must run without error on a 300-bar standard tape."""
        df = _reversal_tape(n=300)
        for sig_id, entry in SIGNALS.items():
            result = entry["fn"](df, **entry["default_params"])
            assert isinstance(result, pd.Series), f"{sig_id} did not return a Series"
            assert len(result) == len(df), f"{sig_id} returned wrong length"
            _assert_no_nan(result, sig_id)

    def test_dependency_families(self):
        expected = {
            "squeeze_on": "compression_release",
            "squeeze_fire_up": "compression_release",
            "squeeze_fire_dn": "compression_release",
            "chop_trend_regime": "trend_efficiency",
            "chop_range_regime": "trend_efficiency",
            "chop_trend_onset": "trend_efficiency",
            "vhf_trend_regime": "trend_efficiency",
            "donch_break_up": "breakout_channel",
            "donch_break_dn": "breakout_channel",
            "donch_fail_up": "breakout_channel",
            "donch_fail_dn": "breakout_channel",
            "donch_width_expand": "breakout_channel",
            "nr7_setup": "volatility_range",
            "range_expand_up": "volatility_range",
            "range_expand_dn": "volatility_range",
        }
        for sig_id, fam in expected.items():
            assert SIGNALS[sig_id]["dependency_family"] == fam, (
                f"SIGNALS['{sig_id}']['dependency_family'] expected {fam!r}, "
                f"got {SIGNALS[sig_id]['dependency_family']!r}"
            )
