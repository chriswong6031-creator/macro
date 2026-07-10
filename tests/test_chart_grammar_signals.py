"""tests/test_chart_grammar_signals.py — Tests for the 4 chart-grammar signal families.

Families under test:
  ichimoku         — ichimoku_signals.py (6 signals)
  trend_ribbon     — trend_ribbon_signals.py (4 signals)
  rsi_stack        — rsi_stack_signals.py (4 signals)
  bollinger_events — bollinger_event_signals.py (4 signals)

For each of the 18 signals:
  (a) fires on a constructed pattern that should trigger it
  (b) does not fire on a flat constant series
  (c) displacement check for ichimoku: a price spike must not influence the
      cloud signals in the windows before it lands at +displacement bars
      (fault-injection-verified; see test_ichimoku_displacement_shields_spike_windows)
      plus a warmup check that cloud signals stay 0 until both spans are valid.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# OHLCV fixture builders
# ---------------------------------------------------------------------------

def _flat_df(n: int = 300, price: float = 100.0) -> pd.DataFrame:
    """Flat constant-price OHLCV — no signal should fire after warm-up."""
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 1_000_000.0,
        },
        index=dates,
    )


def _make_ohlcv(
    n: int = 400,
    seed: int = 42,
    start: str = "2020-01-02",
) -> pd.DataFrame:
    """Synthetic OHLCV with random-walk close."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, size=n))
    high = close * (1.0 + rng.uniform(0.0, 0.02, size=n))
    low = close * (1.0 - rng.uniform(0.0, 0.02, size=n))
    open_ = close * (1.0 + rng.normal(0.0, 0.005, size=n))
    volume = rng.uniform(1_000_000, 50_000_000, size=n)
    dates = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


def _as_df(close_arr, high_arr=None, low_arr=None) -> pd.DataFrame:
    """Build an OHLCV DataFrame from explicit arrays."""
    n = len(close_arr)
    close = np.asarray(close_arr, dtype=float)
    high = np.asarray(high_arr, dtype=float) if high_arr is not None else close * 1.01
    low = np.asarray(low_arr, dtype=float) if low_arr is not None else close * 0.99
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1_000_000.0,
        },
        index=dates,
    )


# ============================================================================
# 1 — ICHIMOKU SIGNALS
# ============================================================================

class TestIchimokuSignals:
    """Tests for engine.ichimoku_signals (6 signals)."""

    def _import(self):
        import engine.ichimoku_signals as m
        return m

    def _run(self, fn, df, **kw):
        return fn(df, **kw)

    # ---- ichimoku_above_cloud -----------------------------------------------

    def test_above_cloud_fires_on_strong_uptrend(self):
        """A long sustained uptrend should put price above the cloud."""
        m = self._import()
        # 400 bars of steady uptrend
        close = 100.0 * (1.005 ** np.arange(400))
        df = _as_df(close, close * 1.002, close * 0.998)
        result = m.ichimoku_above_cloud(df)
        # After cloud warm-up (displacement=26 + kijun=26 + padding), should fire
        assert result.sum() > 0, "ichimoku_above_cloud should fire in a sustained uptrend"

    def test_above_cloud_no_fire_flat(self):
        """Flat series: price equals cloud midpoint — never strictly above cloud_top."""
        m = self._import()
        df = _flat_df(n=300)
        result = m.ichimoku_above_cloud(df)
        # For a flat series, span_a = span_b = close, so cloud_top = cloud_bot = close
        # close > cloud_top is False when all are equal; result should be 0 everywhere
        assert result.sum() == 0, "ichimoku_above_cloud must not fire on a flat series"

    # ---- ichimoku_below_cloud -----------------------------------------------

    def test_below_cloud_fires_on_sustained_downtrend(self):
        """A long sustained downtrend should put price below the cloud."""
        m = self._import()
        close = 100.0 * (0.995 ** np.arange(400))
        df = _as_df(close, close * 1.002, close * 0.998)
        result = m.ichimoku_below_cloud(df)
        assert result.sum() > 0, "ichimoku_below_cloud should fire in a sustained downtrend"

    def test_below_cloud_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.ichimoku_below_cloud(df)
        assert result.sum() == 0, "ichimoku_below_cloud must not fire on a flat series"

    # ---- ichimoku_tk_cross_up -----------------------------------------------

    def test_tk_cross_up_fires(self):
        """Construct a V-shaped close that forces tenkan above kijun."""
        m = self._import()
        # 150 bars down then 150 bars up — after the reversal tenkan (9-period)
        # rises before kijun (26-period), creating a TK cross-up
        n = 300
        half = n // 2
        close = np.concatenate([
            100.0 * (0.99 ** np.arange(half)),
            100.0 * (0.99 ** half) * (1.01 ** np.arange(half)),
        ])
        df = _as_df(close, close * 1.01, close * 0.99)
        result = m.ichimoku_tk_cross_up(df)
        assert result.sum() > 0, "ichimoku_tk_cross_up should fire after a V-shaped reversal"

    def test_tk_cross_up_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.ichimoku_tk_cross_up(df)
        assert result.sum() == 0, "ichimoku_tk_cross_up must not fire on a flat series"

    # ---- ichimoku_tk_cross_down ---------------------------------------------

    def test_tk_cross_down_fires(self):
        """Construct an inverted-V close that forces tenkan below kijun."""
        m = self._import()
        n = 300
        half = n // 2
        close = np.concatenate([
            100.0 * (1.01 ** np.arange(half)),
            100.0 * (1.01 ** half) * (0.99 ** np.arange(half)),
        ])
        df = _as_df(close, close * 1.01, close * 0.99)
        result = m.ichimoku_tk_cross_down(df)
        assert result.sum() > 0, "ichimoku_tk_cross_down should fire after an inverted-V"

    def test_tk_cross_down_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.ichimoku_tk_cross_down(df)
        assert result.sum() == 0, "ichimoku_tk_cross_down must not fire on a flat series"

    # ---- ichimoku_cloud_breakout_up -----------------------------------------

    def test_cloud_breakout_up_fires(self):
        """Price that climbs out of a prior range should break above the cloud."""
        m = self._import()
        # 200 bars flat then 200 bars strong uptrend
        n = 400
        mid = 200
        close = np.concatenate([
            np.full(mid, 100.0),
            100.0 * (1.012 ** np.arange(n - mid)),
        ])
        df = _as_df(close, close * 1.01, close * 0.99)
        result = m.ichimoku_cloud_breakout_up(df)
        assert result.sum() > 0, "ichimoku_cloud_breakout_up should fire when price breaks above cloud"

    def test_cloud_breakout_up_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.ichimoku_cloud_breakout_up(df)
        assert result.sum() == 0, "ichimoku_cloud_breakout_up must not fire on a flat series"

    # ---- ichimoku_cloud_breakdown -------------------------------------------

    def test_cloud_breakdown_fires(self):
        """Price that falls out of a prior range should break below the cloud."""
        m = self._import()
        n = 400
        mid = 200
        close = np.concatenate([
            np.full(mid, 100.0),
            100.0 * (0.988 ** np.arange(n - mid)),
        ])
        df = _as_df(close, close * 1.01, close * 0.99)
        result = m.ichimoku_cloud_breakdown(df)
        assert result.sum() > 0, "ichimoku_cloud_breakdown should fire when price breaks below cloud"

    def test_cloud_breakdown_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.ichimoku_cloud_breakdown(df)
        assert result.sum() == 0, "ichimoku_cloud_breakdown must not fire on a flat series"

    # ---- PIT / displacement check -------------------------------------------

    def test_ichimoku_displacement_shields_spike_windows(self):
        """Displacement test: a spike at bar T enters the cloud only at T+displacement.

        The senkou spans are computed from trailing windows and displaced FORWARD
        by `displacement` bars, so data from bar T first appears in the cloud at
        bar T+displacement.  With a huge high/close spike at bar T, the four
        cloud-relative signals must satisfy, versus the spike-free series:

          * null window A (bars T-displacement..T-1): unchanged. A WRONG-SIGNED
            shift(-displacement) would bleed the spike backward into this window.
          * null window B (bars T+1..T+displacement-1): unchanged. A MISSING
            shift would corrupt the cloud immediately after the spike.
          * positive control (bars T+displacement..): at least one cloud signal
            changes once the spike legitimately lands — proving the spike is big
            enough to move signals, so the null windows cannot pass vacuously.

        Verified discriminating by fault injection: deleting .shift(displacement)
        in _ichimoku_components fails window B; using shift(-displacement) fails
        window A.  tk-cross signals are excluded: tenkan/kijun legitimately react
        to the spike at bar T regardless of displacement.
        """
        m = self._import()
        n = 320
        displacement = 26
        spike_bar = 200

        # Gentle deterministic uptrend => above_cloud is 1 through the windows,
        # so a spike-absorbing cloud (~50k vs close ~160) flips it deterministically.
        t = np.arange(n, dtype=float)
        close = 100.0 + 0.3 * t + 2.0 * np.sin(t / 7.0)
        calm = _as_df(close, close + 1.0, close - 1.0)

        spiked = calm.copy()
        spiked.at[spiked.index[spike_bar], "high"] = 99_999.0
        spiked.at[spiked.index[spike_bar], "close"] = 99_999.0

        cloud_signals = [
            m.ichimoku_above_cloud,
            m.ichimoku_below_cloud,
            m.ichimoku_cloud_breakout_up,
            m.ichimoku_cloud_breakdown,
        ]

        # bar `spike_bar` itself is excluded: `close` differs there trivially.
        win_a = (spike_bar - displacement, spike_bar)          # backward-bleed guard
        win_b = (spike_bar + 1, spike_bar + displacement)      # missing-shift guard
        ctrl = (spike_bar + displacement, n)                   # spike has landed

        any_ctrl_diff = False
        for fn in cloud_signals:
            calm_vals = fn(calm).to_numpy()
            spiked_vals = fn(spiked).to_numpy()
            for name, (lo, hi) in (("A (backward-bleed)", win_a), ("B (pre-landing)", win_b)):
                assert (calm_vals[lo:hi] == spiked_vals[lo:hi]).all(), (
                    f"Displacement failure for {fn.__name__} in null window {name} "
                    f"(bars {lo}..{hi - 1}): the spike at bar {spike_bar} changed "
                    "cloud-signal values where the displaced cloud cannot yet (or "
                    "can no longer) contain it — .shift(displacement) is missing "
                    "or wrong-signed."
                )
            if (calm_vals[ctrl[0]:ctrl[1]] != spiked_vals[ctrl[0]:ctrl[1]]).any():
                any_ctrl_diff = True

        assert any_ctrl_diff, (
            "Positive control failed: the spike never changed any cloud signal at "
            f"bars {ctrl[0]}..{ctrl[1] - 1}; the null-window assertions would be vacuous."
        )

    def test_ichimoku_warmup_no_signal_before_both_spans_valid(self):
        """Cloud signals must be 0 until BOTH span_a and span_b are non-NaN.

        Default params: tenkan=9, kijun=26, senkou_b=52, displacement=26.
        span_a first valid at bar kijun+displacement-1 = 51 (0-indexed).
        span_b first valid at bar senkou_b+displacement-1 = 77 (0-indexed).
        All six cloud signals must stay 0 for bars 0..76.
        """
        m = self._import()
        n = 300
        # Use a strong uptrend so that above_cloud would fire if the cloud
        # were (incorrectly) active during the partial span_b window.
        close = 100.0 * (1.005 ** np.arange(n))
        df = _as_df(close, close * 1.002, close * 0.998)

        cloud_signals = [
            m.ichimoku_above_cloud,
            m.ichimoku_below_cloud,
            m.ichimoku_cloud_breakout_up,
            m.ichimoku_cloud_breakdown,
        ]
        # span_b becomes valid at bar senkou_b + displacement - 1 = 77
        warmup_end = 26 + 52 - 1  # = 77 (0-indexed, first valid bar)
        for fn in cloud_signals:
            result = fn(df)
            early = result.iloc[:warmup_end]
            assert early.sum() == 0, (
                f"{fn.__name__} fired during incomplete-cloud warmup "
                f"(bars 0..{warmup_end - 1}): {early[early != 0]}"
            )


# ============================================================================
# 2 — TREND RIBBON SIGNALS
# ============================================================================

class TestTrendRibbonSignals:
    """Tests for engine.trend_ribbon_signals (4 signals)."""

    def _import(self):
        import engine.trend_ribbon_signals as m
        return m

    # ---- ribbon_up ----------------------------------------------------------

    def test_ribbon_up_fires_on_uptrend(self):
        """A sustained uptrend should put the ribbon in up state."""
        m = self._import()
        close = 100.0 * (1.006 ** np.arange(400))
        df = _as_df(close)
        result = m.ribbon_up(df)
        assert result.sum() > 0, "ribbon_up should fire in a sustained uptrend"

    def test_ribbon_up_no_fire_flat(self):
        """Flat series: ribbon slope is zero → not in uptrend."""
        m = self._import()
        df = _flat_df(n=300)
        result = m.ribbon_up(df)
        assert result.sum() == 0, "ribbon_up must not fire on a flat series"

    # ---- ribbon_down --------------------------------------------------------

    def test_ribbon_down_fires_on_downtrend(self):
        """A sustained downtrend should put the ribbon in down state."""
        m = self._import()
        close = 100.0 * (0.994 ** np.arange(400))
        df = _as_df(close)
        result = m.ribbon_down(df)
        assert result.sum() > 0, "ribbon_down should fire in a sustained downtrend"

    def test_ribbon_down_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.ribbon_down(df)
        assert result.sum() == 0, "ribbon_down must not fire on a flat series"

    # ---- ribbon_flip_up -----------------------------------------------------

    def test_ribbon_flip_up_fires_at_trend_reversal(self):
        """After a downtrend → uptrend reversal, ribbon_flip_up should fire."""
        m = self._import()
        half = 200
        close = np.concatenate([
            100.0 * (0.994 ** np.arange(half)),
            100.0 * (0.994 ** half) * (1.006 ** np.arange(half)),
        ])
        df = _as_df(close)
        result = m.ribbon_flip_up(df)
        assert result.sum() > 0, "ribbon_flip_up should fire at uptrend reversal"

    def test_ribbon_flip_up_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.ribbon_flip_up(df)
        assert result.sum() == 0, "ribbon_flip_up must not fire on a flat series"

    # ---- ribbon_flip_down ---------------------------------------------------

    def test_ribbon_flip_down_fires_at_trend_reversal(self):
        """After an uptrend → downtrend reversal, ribbon_flip_down should fire."""
        m = self._import()
        half = 200
        close = np.concatenate([
            100.0 * (1.006 ** np.arange(half)),
            100.0 * (1.006 ** half) * (0.994 ** np.arange(half)),
        ])
        df = _as_df(close)
        result = m.ribbon_flip_down(df)
        assert result.sum() > 0, "ribbon_flip_down should fire at downtrend reversal"

    def test_ribbon_flip_down_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.ribbon_flip_down(df)
        assert result.sum() == 0, "ribbon_flip_down must not fire on a flat series"


# ============================================================================
# 3 — RSI STACK SIGNALS
# ============================================================================

class TestRsiStackSignals:
    """Tests for engine.rsi_stack_signals (4 signals)."""

    def _import(self):
        import engine.rsi_stack_signals as m
        return m

    # ---- rsi_stack_curl_up --------------------------------------------------

    def test_curl_up_fires_on_sustained_rally(self):
        """A rally from depressed prices causes all 3 RSIs to start rising."""
        m = self._import()
        # 100 bars down then 300 bars strong up
        down = 100.0 * (0.98 ** np.arange(100))
        up = down[-1] * (1.02 ** np.arange(300))
        close = np.concatenate([down, up])
        df = _as_df(close)
        result = m.rsi_stack_curl_up(df)
        assert result.sum() > 0, "rsi_stack_curl_up should fire when all 3 RSIs turn upward"

    def test_curl_up_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.rsi_stack_curl_up(df)
        assert result.sum() == 0, "rsi_stack_curl_up must not fire on a flat series"

    # ---- rsi_stack_curl_down ------------------------------------------------

    def test_curl_down_fires_on_sustained_decline(self):
        """A decline from elevated prices causes all 3 RSIs to start falling."""
        m = self._import()
        up = 100.0 * (1.02 ** np.arange(100))
        down = up[-1] * (0.98 ** np.arange(300))
        close = np.concatenate([up, down])
        df = _as_df(close)
        result = m.rsi_stack_curl_down(df)
        assert result.sum() > 0, "rsi_stack_curl_down should fire when all 3 RSIs turn downward"

    def test_curl_down_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.rsi_stack_curl_down(df)
        assert result.sum() == 0, "rsi_stack_curl_down must not fire on a flat series"

    # ---- rsi_stack_oversold -------------------------------------------------

    def test_oversold_fires_after_severe_decline(self):
        """A severe multi-period decline should push all RSIs below 30."""
        m = self._import()
        # 300 bars of strong decline: each bar loses ~3%
        close = 100.0 * (0.97 ** np.arange(300))
        df = _as_df(close)
        result = m.rsi_stack_oversold(df)
        assert result.sum() > 0, "rsi_stack_oversold should fire after a severe decline"

    def test_oversold_no_fire_flat(self):
        """Flat series: all price diffs are zero, so RSI is NaN; signals stay 0.0 via fillna."""
        m = self._import()
        df = _flat_df(n=300)
        result = m.rsi_stack_oversold(df)
        assert result.sum() == 0, "rsi_stack_oversold must not fire on a flat series"

    # ---- rsi_stack_overbought -----------------------------------------------

    def test_overbought_fires_after_strong_rally(self):
        """A strong sustained rally should push all RSIs above 80.

        canon.rsi returns NaN when dn==0 (all-positive diffs), so the fixture
        must include occasional small pullbacks to keep dn > 0.
        """
        m = self._import()
        # Mostly up (+3% each bar) with a small pullback (-1%) every 10th bar
        close_vals = [100.0]
        for i in range(299):
            if i % 10 == 0:
                close_vals.append(close_vals[-1] * 0.99)
            else:
                close_vals.append(close_vals[-1] * 1.03)
        df = _as_df(close_vals)
        result = m.rsi_stack_overbought(df)
        assert result.sum() > 0, "rsi_stack_overbought should fire after a strong rally"

    def test_overbought_no_fire_flat(self):
        """Flat series: all price diffs are zero, so RSI is NaN; signals stay 0.0 via fillna."""
        m = self._import()
        df = _flat_df(n=300)
        result = m.rsi_stack_overbought(df)
        assert result.sum() == 0, "rsi_stack_overbought must not fire on a flat series"


# ============================================================================
# 4 — BOLLINGER EVENT SIGNALS
# ============================================================================

class TestBollingerEventSignals:
    """Tests for engine.bollinger_event_signals (4 signals)."""

    def _import(self):
        import engine.bollinger_event_signals as m
        return m

    # ---- bb_upper_rejection -------------------------------------------------

    def test_upper_rejection_fires_on_spike_high(self):
        """A bar whose high exceeds upper band but close retracts below it fires the signal."""
        m = self._import()
        # Random-walk base with well-defined Bollinger Bands
        rng = np.random.default_rng(7)
        n = 300
        close = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
        high = close + 0.5
        low = close - 0.5
        dates = pd.date_range("2020-01-02", periods=n, freq="B")
        df = pd.DataFrame(
            {"open": close, "high": high, "low": low, "close": close, "volume": 1_000_000.0},
            index=dates,
        ).copy()  # explicit copy to avoid CoW warnings
        # Compute upper band at bar 150 using the prior 20 bars
        win_close = close[130:150]
        upper_est = win_close.mean() + 2 * win_close.std(ddof=1)
        # Force spike: high above upper, close below upper
        df.loc[dates[150], "high"] = upper_est + 5.0
        df.loc[dates[150], "close"] = upper_est - 1.0
        df.loc[dates[150], "low"] = close[150]
        result = m.bb_upper_rejection(df)
        assert result.iloc[150] == 1.0, "bb_upper_rejection should fire on the spike-and-retract bar"

    def test_upper_rejection_no_fire_flat(self):
        """Flat series: std=0, bands collapse to price; close < upper is trivially False."""
        m = self._import()
        df = _flat_df(n=300)
        result = m.bb_upper_rejection(df)
        assert result.sum() == 0, "bb_upper_rejection must not fire on a flat series"

    # ---- bb_lower_reclaim ---------------------------------------------------

    def test_lower_reclaim_fires_on_spike_low(self):
        """A bar whose low dips below the lower band but close recovers above fires the signal."""
        m = self._import()
        rng = np.random.default_rng(13)
        n = 300
        close = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
        high = close + 0.5
        low = close - 0.5
        dates = pd.date_range("2020-01-02", periods=n, freq="B")
        df = pd.DataFrame(
            {"open": close, "high": high, "low": low, "close": close, "volume": 1_000_000.0},
            index=dates,
        ).copy()
        # Compute lower band at bar 150 using the prior 20 bars
        win_close = close[130:150]
        lower_est = win_close.mean() - 2 * win_close.std(ddof=1)
        # Force reclaim: low below lower, close above lower
        df.loc[dates[150], "low"] = lower_est - 5.0
        df.loc[dates[150], "close"] = lower_est + 1.0
        df.loc[dates[150], "high"] = lower_est + 2.0
        result = m.bb_lower_reclaim(df)
        assert result.iloc[150] == 1.0, "bb_lower_reclaim should fire on the dip-and-recover bar"

    def test_lower_reclaim_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.bb_lower_reclaim(df)
        assert result.sum() == 0, "bb_lower_reclaim must not fire on a flat series"

    # ---- bb_band_walk_up ----------------------------------------------------

    def test_band_walk_up_fires_during_strong_uptrend(self):
        """A series with repeated large step-ups generates close > upper on several bars.

        A pure exponential trend doesn't exceed the upper band (the 20-bar std captures
        the full range). Repeated sudden jumps produce clean episodes above the band.
        """
        m = self._import()
        n = 300
        close = np.zeros(n)
        close[0] = 100.0
        for i in range(1, n):
            # jump +20% every 25 bars, else tiny drift
            close[i] = close[i - 1] * (1.20 if i % 25 == 0 else 1.001)
        df = _as_df(close, close * 1.001, close * 0.999)
        result = m.bb_band_walk_up(df)
        assert result.sum() > 0, "bb_band_walk_up should fire after repeated step-up jumps"

    def test_band_walk_up_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.bb_band_walk_up(df)
        assert result.sum() == 0, "bb_band_walk_up must not fire on a flat series"

    # ---- bb_band_walk_down --------------------------------------------------

    def test_band_walk_down_fires_during_strong_downtrend(self):
        """A series with repeated large step-downs generates close < lower on several bars."""
        m = self._import()
        n = 300
        close = np.zeros(n)
        close[0] = 1000.0
        for i in range(1, n):
            # drop -20% every 25 bars, else tiny drift down
            close[i] = close[i - 1] * (0.80 if i % 25 == 0 else 0.999)
        df = _as_df(close, close * 1.001, close * 0.999)
        result = m.bb_band_walk_down(df)
        assert result.sum() > 0, "bb_band_walk_down should fire after repeated step-down drops"

    def test_band_walk_down_no_fire_flat(self):
        m = self._import()
        df = _flat_df(n=300)
        result = m.bb_band_walk_down(df)
        assert result.sum() == 0, "bb_band_walk_down must not fire on a flat series"


# ============================================================================
# 5 — CATALOG INTEGRATION: new families registered
# ============================================================================

class TestCatalogRegistration:
    """Verify all 18 new signals are properly registered in the catalog."""

    NEW_SIGNAL_IDS = [
        # ichimoku
        "ichimoku_above_cloud",
        "ichimoku_below_cloud",
        "ichimoku_tk_cross_up",
        "ichimoku_tk_cross_down",
        "ichimoku_cloud_breakout_up",
        "ichimoku_cloud_breakdown",
        # trend_ribbon
        "ribbon_up",
        "ribbon_down",
        "ribbon_flip_up",
        "ribbon_flip_down",
        # rsi_stack
        "rsi_stack_curl_up",
        "rsi_stack_curl_down",
        "rsi_stack_oversold",
        "rsi_stack_overbought",
        # bollinger_events
        "bb_upper_rejection",
        "bb_lower_reclaim",
        "bb_band_walk_up",
        "bb_band_walk_down",
    ]

    def test_all_new_signals_registered(self):
        from engine.tech_catalog import TECH_SIGNALS
        missing = [sid for sid in self.NEW_SIGNAL_IDS if sid not in TECH_SIGNALS]
        assert not missing, f"Missing signal IDs in catalog: {missing}"

    def test_new_families_present(self):
        from engine.tech_catalog import signal_families
        fams = signal_families()
        for fam in ("ichimoku", "trend_ribbon", "rsi_stack", "bollinger_events"):
            assert fam in fams, f"Family '{fam}' not in catalog families: {fams}"

    def test_new_signals_compute_return_series(self):
        """All 18 new signals return pd.Series of correct length on a sample frame."""
        from engine.tech_catalog import compute
        df = _make_ohlcv(n=400)
        errors = []
        for sid in self.NEW_SIGNAL_IDS:
            try:
                result = compute(sid, df)
                assert isinstance(result, pd.Series), f"{sid} returned {type(result)}"
                assert len(result) == len(df), f"{sid} wrong length"
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{sid}: {exc}")
        if errors:
            pytest.fail("compute() failed for:\n" + "\n".join(errors))

    def test_no_whale_or_danny_in_identifiers(self):
        """Governance: no 'whale' or 'danny' in new signal ids or display strings."""
        from engine.tech_catalog import TECH_SIGNALS
        forbidden = ("whale", "danny", "dannytrades")
        for sid in self.NEW_SIGNAL_IDS:
            desc = TECH_SIGNALS[sid]
            for word in forbidden:
                assert word not in sid.lower(), f"Forbidden word '{word}' in signal id '{sid}'"
                for lang in ("en", "zh"):
                    txt = desc["display"].get(lang, "")
                    assert word not in txt.lower(), (
                        f"Forbidden word '{word}' in {sid} display[{lang}]: {txt}"
                    )

    def test_no_validated_in_display_strings(self):
        """Honesty contract: 'validated' must not appear in any new signal's display text."""
        from engine.tech_catalog import TECH_SIGNALS
        for sid in self.NEW_SIGNAL_IDS:
            desc = TECH_SIGNALS[sid]
            for lang in ("en", "zh"):
                txt = desc["display"].get(lang, "")
                assert "validated" not in txt.lower(), (
                    f"'validated' found in {sid} display[{lang}]: {txt}"
                )
