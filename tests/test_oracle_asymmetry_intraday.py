"""Tests for scripts/oracle_asymmetry_intraday.py — synthetic OHLC fixtures.

Spec §4.3:
  - long stop-touch via low with close above stop (case close-only misses)
  - short-side mirrored touches
  - straddle → stop wins
  - coverage exclusion
  - frozen-σ reuse

All tests use synthetic in-memory data; no network/data-store deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.oracle_asymmetry_intraday import (
    terminal_state_hl,
    has_ohlc_coverage,
    grade_row_intraday,
    compute_concordance,
    run_fidelity_gate,
    COVERAGE_STARTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlc(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    start: str = "2020-01-02",
) -> pd.DataFrame:
    """Build a synthetic OHLC DataFrame with a business-day DatetimeIndex."""
    n = len(closes)
    assert len(opens) == n and len(highs) == n and len(lows) == n
    dates = pd.bdate_range(start=start, periods=n)
    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1_000] * n},
        index=dates,
    )
    df.index.name = "date"
    return df


def _make_ohlc_flat(price: float, n: int = 30, start: str = "2020-01-02") -> pd.DataFrame:
    """All-flat OHLC — useful as a background where we inject one critical bar."""
    prices = [price] * n
    return _make_ohlc(prices, prices, prices, prices, start=start)


# ---------------------------------------------------------------------------
# Test 1: Long stop-touch via LOW with close ABOVE stop (spec §4.3, first case)
#
# Close-only misses this: close stays above stop_barrier throughout.
# But the daily LOW dips below stop_barrier on bar+1 → STOPPED intraday.
# ---------------------------------------------------------------------------

class TestLongStopViaLow:
    """The critical case close-only misses: low touches stop, close stays above."""

    def test_low_touches_stop_close_above(self):
        """direction='in': LOW <= stop_barrier on first forward bar but close stays above → STOPPED.

        Layout (next-bar fill convention):
          bar 0 = signal bar (close=100; this is the TRIGGER bar)
          bar 1 = fill bar  (close=100; entry_price=100 → stop_barrier=95)
          bar 2 = first forward bar: low=94 (< 95 = stop), close=96 (> 95)  ← the H/L-only case
          bars 3..23: flat at 100
        """
        ohlc = _make_ohlc(
            #           sig   fill  fwd1      fwd2..22
            opens  = [100,  100,   96]  + [100] * 22,
            highs  = [100,  100,   97]  + [100] * 22,
            lows   = [100,  100,   94.0]+ [100] * 22,   # fwd bar1 low=94 < stop=95
            closes = [100,  100,   96.0]+ [100] * 22,   # fwd bar1 close=96 > stop=95
            start  = "2020-01-02",
        )
        # signal_date = bar 0 → fill = bar 1 (close=100) → first fwd = bar 2 (low=94)
        signal_date = ohlc.index[0]

        result = terminal_state_hl(
            ohlc=ohlc,
            signal_date=signal_date,
            stop_mult=0.95,
            cushion_mult=1.05,
            liftoff_mult=1.05,   # k=1 (rot21 style)
            liftoff_horizon=21,
            dead_band=0.05,
            dead_cap=0.025,
            direction="in",
        )

        assert result["state_hl"] == "STOPPED", (
            f"Expected STOPPED (fwd_low=94 <= stop_barrier=95), "
            f"got {result['state_hl']}. note={result.get('note_hl')}"
        )
        assert result["stopped_at_bar_hl"] == 1, (
            f"Expected stopped at bar 1 of forward (first bar after fill), "
            f"got {result['stopped_at_bar_hl']}"
        )
        # entry price should be 100 (fill bar close, bar 1)
        assert result["entry_price_hl"] == pytest.approx(100.0)

    def test_close_only_would_miss_stop(self):
        """Confirm the close series alone wouldn't trigger stop for the same fixture.

        The fixture has low=94 but close=96 on the critical bar.
        Close-only barrier race: fwd close=96 > stop_barrier=95 → NOT STOPPED.
        Intraday H/L race: fwd low=94 < stop_barrier=95 → STOPPED.
        This is the semantic gap W0.2 measures.
        """
        # close series: bar0=100 (signal), bar1=100 (fill, entry=100, stop=95),
        # bar2=96 (close > 95 → close-only does NOT stop), bars 3..23=100
        closes = [100.0, 100.0, 96.0] + [100.0] * 22
        close_series = pd.Series(
            closes,
            index=pd.bdate_range(start="2020-01-02", periods=len(closes)),
        )
        signal_date = close_series.index[0]
        entry = float(close_series.iloc[1])  # next-bar fill = bar 1 close = 100
        stop_barrier = entry * 0.95           # = 95

        # All forward closes (bars 2..22): 96, 100, ... → all > 95
        fwd = close_series.iloc[2:23]  # bars fill+1..fill+21
        close_would_stop = bool((fwd <= stop_barrier).any())
        assert not close_would_stop, f"Close-only should NOT stop (min={fwd.min()} > {stop_barrier})"

    def test_no_stop_when_low_above_barrier(self):
        """direction='in': low stays above stop_barrier → NOT STOPPED."""
        ohlc = _make_ohlc_flat(100.0, n=30)
        signal_date = ohlc.index[0]
        result = terminal_state_hl(
            ohlc=ohlc,
            signal_date=signal_date,
            stop_mult=0.95,
            cushion_mult=1.05,
            liftoff_mult=1.05,
            liftoff_horizon=21,
            dead_band=0.08,
            dead_cap=0.04,
            direction="in",
        )
        assert result["state_hl"] != "STOPPED"


# ---------------------------------------------------------------------------
# Test 2: Short-side mirrored touches (spec §3, §4.3)
#
# direction='out': stop = HIGH >= entry/stop_mult; target = LOW <= entry/liftoff_mult
# NO series inversion (spec: "no series inversion for H/L")
# ---------------------------------------------------------------------------

class TestShortSideDirectionExplicit:
    """Spec §3: short side uses high for stop, low for target — no inversion."""

    def test_short_stop_via_high(self):
        """direction='out': HIGH >= stop_barrier → STOPPED on short side.

        Layout:
          bar 0 = signal bar (close=100)
          bar 1 = fill bar   (close=100; entry=100; short stop_barrier=100/0.95≈105.26)
          bar 2 = first fwd:  high=106 (> 105.26 → STOPPED short), close=99
          bars 3..23: flat at 100
        """
        ohlc = _make_ohlc(
            #           sig  fill  fwd1         fwd2..22
            opens  = [100, 100,  100]  + [100] * 22,
            highs  = [100, 100,  106.0]+ [100] * 22,  # high=106 > 105.26
            lows   = [100, 100,   99.0]+ [100] * 22,
            closes = [100, 100,   99.0]+ [100] * 22,
            start  = "2020-01-02",
        )
        signal_date = ohlc.index[0]
        result = terminal_state_hl(
            ohlc=ohlc,
            signal_date=signal_date,
            stop_mult=0.95,
            cushion_mult=1.05,
            liftoff_mult=1.10,
            liftoff_horizon=21,
            dead_band=0.05,
            dead_cap=0.025,
            direction="out",
        )
        # stop_barrier = 100 / 0.95 ≈ 105.26; bar_high=106 > 105.26 → STOPPED
        assert result["state_hl"] == "STOPPED", (
            f"Expected STOPPED on short (high=106 >= {100/0.95:.2f}), "
            f"got {result['state_hl']}. note={result.get('note_hl')}"
        )

    def test_short_liftoff_via_low(self):
        """direction='out': LOW <= liftoff_barrier → CLEAN_LIFTOFF on short side.

        Layout:
          bar 0 = signal bar (close=100)
          bar 1 = fill bar   (close=100; entry=100; short liftoff_barrier=100/1.10≈90.91)
          bar 2 = first fwd:  low=90 (< 90.91 → CLEAN_LIFTOFF short), high stays below stop
          bars 3..23: flat at 100
        """
        ohlc = _make_ohlc(
            #           sig  fill  fwd1          fwd2..22
            opens  = [100, 100,  91]   + [100] * 22,
            highs  = [100, 100,  101.0]+ [100] * 22,  # high=101 < 105.26 (no short stop)
            lows   = [100, 100,   90.0]+ [100] * 22,  # low=90 < 90.91 → liftoff
            closes = [100, 100,   91.0]+ [100] * 22,
            start  = "2020-01-02",
        )
        signal_date = ohlc.index[0]
        result = terminal_state_hl(
            ohlc=ohlc,
            signal_date=signal_date,
            stop_mult=0.95,
            cushion_mult=1.05,
            liftoff_mult=1.10,
            liftoff_horizon=21,
            dead_band=0.05,
            dead_cap=0.025,
            direction="out",
        )
        # liftoff_barrier = 100/1.10 ≈ 90.91; bar_low=90 < 90.91 → CLEAN_LIFTOFF
        assert result["state_hl"] == "CLEAN_LIFTOFF", (
            f"Expected CLEAN_LIFTOFF on short (low=90 <= {100/1.10:.2f}), "
            f"got {result['state_hl']}. note={result.get('note_hl')}"
        )

    def test_long_and_short_use_different_columns(self):
        """Long uses LOW for stop; short uses HIGH for stop — verify asymmetry.

        Layout:
          bar 0 = signal bar (close=100)
          bar 1 = fill bar   (close=100; entry=100)
          bar 2 = first fwd:  low=94 (stops long, 94<95), high=101 (ok for short, 101<105.26)
          bars 3..24: flat at 100
        """
        ohlc = _make_ohlc(
            #           sig  fill  fwd1      fwd2..23
            opens  = [100, 100, 100]  + [100] * 23,
            highs  = [100, 100, 101.0]+ [100] * 23,
            lows   = [100, 100,  94.0]+ [100] * 23,  # low=94 < 95 → stops long
            closes = [100, 100,  97.0]+ [100] * 23,
            start  = "2020-01-02",
        )
        signal_date = ohlc.index[0]

        long_result = terminal_state_hl(
            ohlc=ohlc, signal_date=signal_date,
            stop_mult=0.95, cushion_mult=1.05, liftoff_mult=1.05,
            liftoff_horizon=21, dead_band=0.08, dead_cap=0.04,
            direction="in",
        )
        short_result = terminal_state_hl(
            ohlc=ohlc, signal_date=signal_date,
            stop_mult=0.95, cushion_mult=1.05, liftoff_mult=1.10,
            liftoff_horizon=21, dead_band=0.08, dead_cap=0.04,
            direction="out",
        )
        # Long: low=94 <= stop=95 → STOPPED
        assert long_result["state_hl"] == "STOPPED"
        # Short: high=101 < stop_barrier=100/0.95≈105.26 → NOT STOPPED
        assert short_result["state_hl"] != "STOPPED"


# ---------------------------------------------------------------------------
# Test 3: Straddle → stop wins (spec §3, house tie law)
# ---------------------------------------------------------------------------

class TestStraddleStopWins:
    """Same-bar straddle: LOW <= stop_barrier AND HIGH >= liftoff_barrier → STOP WINS."""

    def test_straddle_long_stop_wins(self):
        """direction='in': same bar low=94 AND high=106 → stop (conservative).

        Layout:
          bar 0 = signal bar (close=100)
          bar 1 = fill bar   (close=100; entry=100; stop=95, cushion/liftoff=105)
          bar 2 = first fwd:  low=94 (< 95=stop) AND high=106 (> 105=liftoff) → STRADDLE
          bars 3..23: flat at 100
        House tie law: stop wins.
        """
        ohlc = _make_ohlc(
            #           sig  fill  fwd1         fwd2..22
            opens  = [100, 100,  100]  + [100] * 22,
            highs  = [100, 100,  106.0]+ [100] * 22,  # high=106 > 105 (liftoff)
            lows   = [100, 100,   94.0]+ [100] * 22,  # low=94 < 95 (stop)
            closes = [100, 100,  100.0]+ [100] * 22,
            start  = "2020-01-02",
        )
        signal_date = ohlc.index[0]
        result = terminal_state_hl(
            ohlc=ohlc,
            signal_date=signal_date,
            stop_mult=0.95,
            cushion_mult=1.05,
            liftoff_mult=1.05,   # cushion == liftoff (rot21)
            liftoff_horizon=21,
            dead_band=0.05,
            dead_cap=0.025,
            direction="in",
        )
        assert result["state_hl"] == "STOPPED", (
            f"Straddle tie rule: stop should win, got {result['state_hl']}. "
            f"note={result.get('note_hl')}"
        )
        assert result["stopped_at_bar_hl"] == 1

    def test_straddle_short_stop_wins(self):
        """direction='out': same bar HIGH >= stop_barrier AND LOW <= liftoff_barrier → STOPPED.

        Layout:
          bar 0 = signal bar (close=100)
          bar 1 = fill bar   (close=100; short stop_barrier≈105.26, liftoff_barrier≈90.91)
          bar 2 = first fwd:  high=106 (>105.26=stop) AND low=90 (<90.91=liftoff) → STRADDLE
          bars 3..23: flat at 100
        House tie law: stop wins.
        """
        ohlc = _make_ohlc(
            #           sig  fill  fwd1          fwd2..22
            opens  = [100, 100,  100]  + [100] * 22,
            highs  = [100, 100,  106.0]+ [100] * 22,  # > 105.26 = short stop
            lows   = [100, 100,   90.0]+ [100] * 22,  # < 90.91 = short liftoff
            closes = [100, 100,   98.0]+ [100] * 22,
            start  = "2020-01-02",
        )
        signal_date = ohlc.index[0]
        result = terminal_state_hl(
            ohlc=ohlc,
            signal_date=signal_date,
            stop_mult=0.95,
            cushion_mult=1.05,
            liftoff_mult=1.10,
            liftoff_horizon=21,
            dead_band=0.05,
            dead_cap=0.025,
            direction="out",
        )
        assert result["state_hl"] == "STOPPED", (
            f"Short straddle tie: stop should win, got {result['state_hl']}. "
            f"note={result.get('note_hl')}"
        )


# ---------------------------------------------------------------------------
# Test 4: Coverage exclusion (spec §1)
# ---------------------------------------------------------------------------

class TestCoverageExclusion:
    """Rows before OHLC coverage starts → ohlc_coverage=False; excluded from intraday tables."""

    def _make_store_with_ticker(self, ticker: str, start: str) -> dict:
        ohlc = _make_ohlc_flat(50.0, n=40, start=start)
        return {ticker: ohlc}

    def test_xlc_before_coverage_start(self):
        """XLC trigger 2018-09-01 < 2018-09-19 cutoff → ohlc_coverage=False."""
        store = self._make_store_with_ticker("XLC", "2018-09-19")
        ticker = "XLC"
        trigger = pd.Timestamp("2018-09-01")  # before cutoff
        assert not has_ohlc_coverage(ticker, trigger, store)

    def test_xlc_at_coverage_start(self):
        """XLC trigger == 2018-09-19 → ohlc_coverage=True."""
        store = self._make_store_with_ticker("XLC", "2018-09-01")
        ticker = "XLC"
        trigger = pd.Timestamp("2018-09-19")  # exactly at cutoff
        assert has_ohlc_coverage(ticker, trigger, store)

    def test_xlre_before_coverage_start(self):
        """XLRE trigger 2015-10-01 < 2015-10-07 cutoff → ohlc_coverage=False."""
        store = self._make_store_with_ticker("XLRE", "2015-10-07")
        ticker = "XLRE"
        trigger = pd.Timestamp("2015-10-01")
        assert not has_ohlc_coverage(ticker, trigger, store)

    def test_xlre_at_coverage_start(self):
        """XLRE trigger == 2015-10-07 → ohlc_coverage=True."""
        store = self._make_store_with_ticker("XLRE", "2015-10-01")
        ticker = "XLRE"
        trigger = pd.Timestamp("2015-10-07")
        assert has_ohlc_coverage(ticker, trigger, store)

    def test_missing_ticker_coverage_false(self):
        """Ticker not in store → ohlc_coverage=False."""
        store = {}
        assert not has_ohlc_coverage("XLK", pd.Timestamp("2020-01-02"), store)

    def test_trigger_after_store_end_coverage_false(self):
        """Trigger date after last row in OHLC → no fill bar → coverage=False."""
        store = self._make_store_with_ticker("XLK", "2020-01-02")
        # OHLC ends ~2020-02-21 (40 bdays from 2020-01-02)
        trigger = pd.Timestamp("2025-01-01")  # far future
        assert not has_ohlc_coverage("XLK", trigger, store)

    def test_grade_row_intraday_excluded_row(self):
        """grade_row_intraday for an excluded row → ohlc_coverage=False, state_hl=None."""
        row = pd.Series({
            "node": "XLC",
            "trigger_date": "2017-01-02",  # way before XLC cutoff
            "direction": "in",
            "parameterization": "rot21",
            "sigma20": 0.05,
        })
        store = self._make_store_with_ticker("XLC", "2018-09-19")
        result = grade_row_intraday(row, store)
        assert result["ohlc_coverage"] is False
        assert result["state_hl"] is None


# ---------------------------------------------------------------------------
# Test 5: Frozen-σ reuse (spec §3)
# ---------------------------------------------------------------------------

class TestFrozenSigmaReuse:
    """W0.2 must reuse σ20 from the W0_1 row (not recompute it)."""

    def test_sigma_from_row_used_in_barriers(self):
        """Verify that the entry_price × stop_mult uses the provided σ20.

        Layout:
          bar 0 = signal bar (close=100) → trigger_date
          bar 1 = fill bar   (close=100; entry=100; σ=0.10 → stop_mult=0.90 → stop=90)
          bar 2 = first fwd:  low=89 (< 90 → STOPPED), close=92 (> 90: close-only misses)
          bars 3..23: flat at 100
        """
        ohlc = _make_ohlc(
            #           sig  fill  fwd1       fwd2..22
            opens  = [100, 100,  100]  + [100] * 22,
            highs  = [100, 100,  100]  + [100] * 22,
            lows   = [100, 100,   89.0]+ [100] * 22,  # 89 < 90 = stop
            closes = [100, 100,   92.0]+ [100] * 22,  # 92 > 90: close-only misses
            start  = "2020-01-02",
        )
        row = pd.Series({
            "node": "XLK",
            "trigger_date": str(ohlc.index[0].date()),
            "direction": "in",
            "parameterization": "rot21",
            "sigma20": 0.10,  # 10% σ → stop_mult=0.90 → stop_barrier=90
        })
        store = {"XLK": ohlc}
        result = grade_row_intraday(row, store)

        assert result["ohlc_coverage"] is True
        assert result["state_hl"] == "STOPPED", (
            f"σ20=0.10 → stop=90; low=89 → STOPPED. Got {result['state_hl']}. "
            f"note={result.get('note_hl')}"
        )

    def test_wrong_sigma_would_not_stop(self):
        """σ20=0.001 (very tight) → stop_barrier=99.9, low=99.5 → STOPPED.

        Layout:
          bar 0 = signal bar (close=100)
          bar 1 = fill bar   (close=100; σ=0.001 → stop_mult=0.999 → stop=99.9)
          bar 2 = first fwd:  low=99.5 (< 99.9 → STOPPED)
          bars 3..23: flat at 100
        """
        ohlc = _make_ohlc(
            #           sig  fill  fwd1       fwd2..22
            opens  = [100, 100,  100]  + [100] * 22,
            highs  = [100, 100,  100]  + [100] * 22,
            lows   = [100, 100,   99.5]+ [100] * 22,  # 99.5 < 99.9
            closes = [100, 100,   99.8]+ [100] * 22,
            start  = "2020-01-02",
        )
        row = pd.Series({
            "node": "XLK",
            "trigger_date": str(ohlc.index[0].date()),
            "direction": "in",
            "parameterization": "rot21",
            "sigma20": 0.001,  # σ=0.1% → stop_mult=0.999 → stop_barrier=99.9
        })
        store = {"XLK": ohlc}
        result = grade_row_intraday(row, store)
        assert result["state_hl"] == "STOPPED", (
            f"σ=0.001 → stop=99.9; low=99.5 < 99.9 → STOPPED. Got {result['state_hl']}"
        )

    def test_pos63_uses_2sigma_liftoff(self):
        """pos63 parameterization: liftoff_mult = 1 + 2*σ (k=2).

        Layout:
          bar 0 = signal bar (close=100)
          bar 1 = fill bar   (close=100; σ=0.08 → liftoff_mult=1.16 → barrier=116)
          bar 2 = first fwd:  high=116.5 (> 116 → CLEAN_LIFTOFF)
          bars 3..65: flat at 100 (64 more bars to satisfy horizon=63)
        """
        sigma = 0.08  # 8% σ → liftoff_mult = 1+2*0.08 = 1.16 → barrier = 116.0
        ohlc = _make_ohlc(
            #           sig  fill  fwd1          fwd2..64
            opens  = [100, 100,  100]   + [100] * 64,
            highs  = [100, 100,  116.5] + [100] * 64,  # high=116.5 > 116 → liftoff
            lows   = [100, 100,   99.0] + [100] * 64,
            closes = [100, 100,  110.0] + [100] * 64,
            start  = "2020-01-02",
        )
        row = pd.Series({
            "node": "XLK",
            "trigger_date": str(ohlc.index[0].date()),
            "direction": "in",
            "parameterization": "pos63",
            "sigma20": sigma,
        })
        store = {"XLK": ohlc}
        result = grade_row_intraday(row, store)
        assert result["ohlc_coverage"] is True
        assert result["state_hl"] == "CLEAN_LIFTOFF", (
            f"σ=0.08→liftoff_mult=1.16→barrier=116; high=116.5 > 116. "
            f"Got {result['state_hl']}. note={result.get('note_hl')}"
        )


# ---------------------------------------------------------------------------
# Test 6: MFE/MAE from H/L extremes in R units
# ---------------------------------------------------------------------------

class TestMfeMaeHL:
    """MFE/MAE computed from H/L extremes (not close-only)."""

    def test_mfe_from_high(self):
        """MFE_HL should reflect the highest high in the forward window.

        Layout:
          bar 0 = signal bar (close=100)
          bar 1 = fill bar   (close=100; entry=100; σ=0.10 → R unit = 10%)
          bar 2..6 = fwd bars 1-5: flat at 100
          bar 7 = fwd bar 6: high=120 (MFE=+20% = 2.0R)
          bars 8..23: flat at 100
        """
        ohlc = _make_ohlc(
            #           sig  fill  fwd1..5        fwd6       fwd7..21
            opens  = [100, 100] + [100] * 5 + [100, 100] + [100] * 16,
            highs  = [100, 100] + [100] * 5 + [120.0, 100] + [100] * 16,
            lows   = [100, 100] + [100] * 5 + [99,    100] + [100] * 16,
            closes = [100, 100] + [100] * 5 + [110,   100] + [100] * 16,
            start  = "2020-01-02",
        )
        row = pd.Series({
            "node": "XLK",
            "trigger_date": str(ohlc.index[0].date()),
            "direction": "in",
            "parameterization": "rot21",
            "sigma20": 0.10,
        })
        store = {"XLK": ohlc}
        result = grade_row_intraday(row, store)
        assert result["ohlc_coverage"] is True
        # mfe_R_hl_21 = +20% / 10% = 2.0R
        mfe = result.get("mfe_R_hl_21")
        assert mfe is not None
        assert mfe == pytest.approx(2.0, abs=0.05), f"Expected ≈2.0R, got {mfe}"

    def test_mae_from_low(self):
        """MAE_HL should reflect the worst low in the forward window.

        Layout:
          bar 0 = signal bar (close=100)
          bar 1 = fill bar   (close=100; entry=100; σ=0.10 → R unit = 10%)
          bar 2..6 = fwd bars 1-5: flat at 100
          bar 7 = fwd bar 6: low=85 (MAE=-15% = -1.5R)
          bars 8..23: flat at 100
        """
        ohlc = _make_ohlc(
            #           sig  fill  fwd1..5        fwd6          fwd7..21
            opens  = [100, 100] + [100] * 5 + [100,  100] + [100] * 16,
            highs  = [100, 100] + [100] * 5 + [100,  100] + [100] * 16,
            lows   = [100, 100] + [100] * 5 + [85.0, 100] + [100] * 16,  # low=85
            closes = [100, 100] + [100] * 5 + [92,   100] + [100] * 16,
            start  = "2020-01-02",
        )
        row = pd.Series({
            "node": "XLK",
            "trigger_date": str(ohlc.index[0].date()),
            "direction": "in",
            "parameterization": "rot21",
            "sigma20": 0.10,
        })
        store = {"XLK": ohlc}
        result = grade_row_intraday(row, store)
        assert result["ohlc_coverage"] is True
        # mae_R_hl_21 = -15% / 10% = -1.5R
        mae = result.get("mae_R_hl_21")
        assert mae is not None
        assert mae == pytest.approx(-1.5, abs=0.05), f"Expected ≈-1.5R, got {mae}"


# ---------------------------------------------------------------------------
# Test 7: Concordance computation (structural / smoke test)
# ---------------------------------------------------------------------------

class TestConcordance:
    """Smoke tests for compute_concordance — verifies structure without real data."""

    def _make_merged(
        self,
        n: int = 30,
        close_states: list[str] | None = None,
        hl_states: list[str] | None = None,
    ) -> pd.DataFrame:
        """Build a minimal merged DataFrame for concordance testing."""
        if close_states is None:
            close_states = ["STOPPED"] * 10 + ["DEAD_MONEY"] * 10 + ["CLEAN_LIFTOFF"] * 10
        if hl_states is None:
            hl_states = ["STOPPED"] * 15 + ["DEAD_MONEY"] * 5 + ["CLEAN_LIFTOFF"] * 10

        df = pd.DataFrame({
            "family": ["ep_onset_in"] * n,
            "node": ["XLK"] * n,
            "trigger_date": ["2020-01-02"] * n,
            "parameterization": ["rot21"] * n,
            "direction": ["in"] * n,
            "dedup_variant": ["single"] * n,
            "sigma20": [0.08] * n,
            "state": close_states[:n],
            "state_hl": hl_states[:n],
            "ohlc_coverage": [True] * n,
            "state_immature": [False] * n,
            "policy_R_rot21": [0.5] * 10 + [-1.0] * 10 + [1.5] * 10,
            "mae_R_21": [-0.5] * n,
            "mae_R_hl_21": [-0.7] * n,
        })
        return df

    def test_concordance_keys_present(self):
        """Concordance dict should have expected keys."""
        merged = self._make_merged()
        conc = compute_concordance(merged)
        assert "ep_onset_in|rot21" in conc
        entry = conc["ep_onset_in|rot21"]
        for key in (
            "n_both", "pct_state_changed", "pct_close_dead_clean_to_stopped",
            "delta_stop_pct", "delta_win_pct", "delta_median_R",
            "mae_delta_median", "mae_delta_p25", "mae_delta_p75",
        ):
            assert key in entry, f"Missing key: {key}"

    def test_concordance_stop_delta_correct(self):
        """Concordance correctly computes Δ stop-touch rate."""
        # 10/30 = 33.3% STOPPED in close; 15/30 = 50% STOPPED in HL
        merged = self._make_merged(
            n=30,
            close_states=["STOPPED"] * 10 + ["DEAD_MONEY"] * 10 + ["CLEAN_LIFTOFF"] * 10,
            hl_states=["STOPPED"] * 15 + ["DEAD_MONEY"] * 5 + ["CLEAN_LIFTOFF"] * 10,
        )
        conc = compute_concordance(merged)
        entry = conc["ep_onset_in|rot21"]
        assert entry["stop_pct_close"] == pytest.approx(33.3, abs=0.2)
        assert entry["stop_pct_intraday"] == pytest.approx(50.0, abs=0.2)
        assert entry["delta_stop_pct"] == pytest.approx(50.0 - 33.3, abs=0.3)

    def test_concordance_mae_delta(self):
        """MAE delta = mae_R_hl_21 - mae_R_21; should be negative (HL shows deeper MAE)."""
        merged = self._make_merged()
        conc = compute_concordance(merged)
        entry = conc["ep_onset_in|rot21"]
        # mae_R_hl_21=-0.7, mae_R_21=-0.5 → delta=-0.2
        assert entry["mae_delta_median"] == pytest.approx(-0.2, abs=0.01)

    def test_concordance_pct_to_stopped(self):
        """% non-STOPPED→STOPPED: events where close != STOPPED but state_hl = STOPPED."""
        # 10 are DEAD_MONEY in close but STOPPED in HL → 10/30 = 33.3%
        close_states = ["STOPPED"] * 5 + ["DEAD_MONEY"] * 15 + ["CLEAN_LIFTOFF"] * 10
        hl_states    = ["STOPPED"] * 5 + ["STOPPED"] * 10 + ["DEAD_MONEY"] * 5 + ["CLEAN_LIFTOFF"] * 10
        merged = self._make_merged(n=30, close_states=close_states, hl_states=hl_states)
        conc = compute_concordance(merged)
        entry = conc["ep_onset_in|rot21"]
        # 10 DEAD_MONEY→STOPPED out of 30 = 33.3%
        assert entry["pct_close_dead_clean_to_stopped"] == pytest.approx(33.3, abs=0.5)

    def test_concordance_empty_coverage_excluded(self):
        """Rows with ohlc_coverage=False are excluded from concordance."""
        merged = self._make_merged(n=30)
        merged.loc[:9, "ohlc_coverage"] = False  # exclude 10 rows
        conc = compute_concordance(merged)
        entry = conc["ep_onset_in|rot21"]
        assert entry["n_both"] == 20  # only 20 covered rows


# ---------------------------------------------------------------------------
# Test 8: Immature rows (not enough forward data)
# ---------------------------------------------------------------------------

class TestImmatureRows:
    """state_hl=None when fewer than liftoff_horizon forward bars available."""

    def test_immature_when_insufficient_forward_bars(self):
        """OHLC has fill bar but only 5 forward bars; horizon=21 → not matured.

        Total bars needed: 1 (signal) + 1 (fill) + 21 (forward) = 23.
        With only 7 bars: 1 signal + 1 fill + 5 fwd → not matured.
        """
        ohlc = _make_ohlc_flat(100.0, n=7)  # 7 bars: signal=0, fill=1, fwd=[2..6]=5 bars
        signal_date = ohlc.index[0]
        result = terminal_state_hl(
            ohlc=ohlc,
            signal_date=signal_date,
            stop_mult=0.95, cushion_mult=1.05, liftoff_mult=1.05,
            liftoff_horizon=21, dead_band=0.05, dead_cap=0.025,
            direction="in",
        )
        assert result["state_hl"] is None
        assert "not yet matured" in result.get("note_hl", "").lower()

    def test_matured_with_exact_forward_bars(self):
        """Exactly liftoff_horizon forward bars → matured → state assigned.

        Need: 1 (signal) + 1 (fill) + 21 (forward) = 23 bars total.
        """
        ohlc = _make_ohlc_flat(100.0, n=23)  # exactly 23 bars
        signal_date = ohlc.index[0]
        result = terminal_state_hl(
            ohlc=ohlc,
            signal_date=signal_date,
            stop_mult=0.95, cushion_mult=1.05, liftoff_mult=1.05,
            liftoff_horizon=21, dead_band=0.08, dead_cap=0.04,
            direction="in",
        )
        assert result["state_hl"] is not None


# ---------------------------------------------------------------------------
# Test 9: CLEAN_LIFTOFF on long side via HIGH
# ---------------------------------------------------------------------------

class TestLongLiftoffViaHigh:
    """Long side: target-touch = HIGH >= liftoff_barrier."""

    def test_high_touches_liftoff_close_below(self):
        """direction='in': HIGH >= liftoff_barrier on fwd bar 3, close below liftoff.

        Layout:
          bar 0 = signal bar (close=100)
          bar 1 = fill bar   (close=100; entry=100; liftoff_barrier=105)
          bar 2 = fwd bar 1:  high=100 (no liftoff), flat
          bar 3 = fwd bar 2:  high=100, flat
          bar 4 = fwd bar 3:  high=106 (> 105 → CLEAN_LIFTOFF), close=104
          bars 5..23: flat at 100
        """
        ohlc = _make_ohlc(
            #           sig  fill  fwd1  fwd2   fwd3         fwd4..22
            opens  = [100, 100, 100,  100,  100]  + [100] * 20,
            highs  = [100, 100, 100,  100,  106.0]+ [100] * 20,  # fwd bar 3 high=106
            lows   = [100, 100, 100,  100,  100]  + [100] * 20,
            closes = [100, 100, 100,  100,  104.0]+ [100] * 20,  # close=104 < 105 liftoff
            start  = "2020-01-02",
        )
        signal_date = ohlc.index[0]
        result = terminal_state_hl(
            ohlc=ohlc,
            signal_date=signal_date,
            stop_mult=0.95,
            cushion_mult=1.05,
            liftoff_mult=1.05,   # k=1 (rot21): cushion == liftoff
            liftoff_horizon=21,
            dead_band=0.05,
            dead_cap=0.025,
            direction="in",
        )
        assert result["state_hl"] == "CLEAN_LIFTOFF", (
            f"Expected CLEAN_LIFTOFF (high=106 >= 105), got {result['state_hl']}. "
            f"note={result.get('note_hl')}"
        )
        assert result["liftoff_at_bar_hl"] == 3  # 1-indexed: 3rd bar of forward window


# ---------------------------------------------------------------------------
# Test 10: Fidelity Gate G1 enforcement
# Spec §5: "same event count per family; abort on any unmatched row"
# After fix-round: G1 actually checks, not just prints.
# ---------------------------------------------------------------------------

class TestFidelityGateG1:
    """G1 must ENFORCE row-for-row join — not merely print a PASS."""

    def _make_w01_df(
        self,
        families: list[str] | None = None,
        n_per_family: int = 5,
        add_dupes: bool = False,
    ) -> pd.DataFrame:
        """Build a minimal W0_1 DataFrame for gate testing."""
        if families is None:
            families = ["ep_onset_in", "ep_onset_out", "routing_6"]
        rows = []
        for fam in families:
            for i in range(n_per_family):
                rows.append({
                    "family": fam,
                    "node": "XLK",
                    "trigger_date": f"2020-01-0{i + 2}",
                    "parameterization": "rot21",
                    "dedup_variant": "raw",
                    "direction": "in",
                    "sigma20": 0.08,
                    "state": "STOPPED",
                })
        df = pd.DataFrame(rows)
        if add_dupes:
            # Append a duplicate of the first row
            df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        return df

    def _make_ohlc_store_with_massive_close(self, tmp_path: Path) -> tuple[dict, Path]:
        """Build a minimal OHLC store and a matching massive_stock_day dir."""
        ohlc_store = {}
        massive_dir = tmp_path / "massive_stock_day"
        massive_dir.mkdir(parents=True)

        # Single ticker with matching prices (same unadjusted basis)
        tickers = ["XLK", "XLV", "XLF", "XLY", "XLI", "XLP", "XLE", "XLU", "XLB", "SPY"]
        dates = pd.bdate_range("2020-01-02", periods=50)
        for t in tickers:
            prices = np.ones(50) * 100.0
            ohlc_df = pd.DataFrame(
                {"open": prices, "high": prices, "low": prices,
                 "close": prices, "volume": np.ones(50) * 1000},
                index=dates,
            )
            ohlc_store[t] = ohlc_df

            # Matching massive_stock_day (same prices → returns match within 0.001)
            mass_df = pd.DataFrame(
                {"open": prices, "high": prices, "low": prices,
                 "close": prices, "volume": np.ones(50) * 1000},
                index=dates,
            )
            mass_df.to_parquet(massive_dir / f"{t}.parquet")

        data_dir = tmp_path
        return ohlc_store, data_dir

    def test_g1_passes_clean_population(self, tmp_path):
        """G1 passes when W0_1 has non-empty unique rows and non-empty family set."""
        w01_df = self._make_w01_df()
        ohlc_store, data_dir = self._make_ohlc_store_with_massive_close(tmp_path)
        # Should not raise SystemExit
        run_fidelity_gate(w01_df, ohlc_store, data_dir)

    def test_g1_aborts_on_empty_csv(self, tmp_path):
        """G1 must abort (sys.exit) when W0_1 CSV is empty."""
        empty_df = pd.DataFrame(columns=["family", "node", "trigger_date"])
        ohlc_store, data_dir = self._make_ohlc_store_with_massive_close(tmp_path)
        with pytest.raises(SystemExit):
            run_fidelity_gate(empty_df, ohlc_store, data_dir)

    def test_g1_aborts_on_duplicate_keys(self, tmp_path):
        """G1 must abort when duplicate primary-key rows are present."""
        w01_df = self._make_w01_df(add_dupes=True)
        ohlc_store, data_dir = self._make_ohlc_store_with_massive_close(tmp_path)
        with pytest.raises(SystemExit):
            run_fidelity_gate(w01_df, ohlc_store, data_dir)

    def test_g1_prints_per_family_counts(self, tmp_path, capsys):
        """G1 must print per-family row counts (not just total)."""
        w01_df = self._make_w01_df(families=["ep_onset_in", "ep_onset_out"], n_per_family=7)
        ohlc_store, data_dir = self._make_ohlc_store_with_massive_close(tmp_path)
        run_fidelity_gate(w01_df, ohlc_store, data_dir)
        captured = capsys.readouterr()
        assert "ep_onset_in" in captured.out, "G1 must print each family name"
        assert "ep_onset_out" in captured.out
        assert "7" in captured.out, "G1 must print per-family row count"


# ---------------------------------------------------------------------------
# Test 11: Fidelity Gate G2 — uses massive_stock_day (unadjusted), aborts on breach
# After fix-round: G2 compares to unadjusted source and sys.exit(1) on >0.1% diff.
# ---------------------------------------------------------------------------

class TestFidelityGateG2:
    """G2 must use massive_stock_day (unadjusted) and abort on return divergence."""

    def _make_stores(
        self,
        tmp_path: Path,
        ohlc_prices: np.ndarray | None = None,
        massive_prices: np.ndarray | None = None,
        n: int = 50,
    ) -> tuple[dict, Path]:
        """Build OHLC store and massive_stock_day parquets with specified prices."""
        dates = pd.bdate_range("2020-01-02", periods=n)
        tickers = ["XLK", "XLV", "XLF", "XLY", "XLI", "XLP", "XLE", "XLU", "XLB", "SPY"]

        if ohlc_prices is None:
            ohlc_prices = np.ones(n) * 100.0
        if massive_prices is None:
            massive_prices = np.ones(n) * 100.0

        massive_dir = tmp_path / "massive_stock_day"
        massive_dir.mkdir(parents=True)

        ohlc_store = {}
        for t in tickers:
            ohlc_df = pd.DataFrame(
                {"open": ohlc_prices, "high": ohlc_prices,
                 "low": ohlc_prices, "close": ohlc_prices, "volume": np.ones(n) * 1000},
                index=dates,
            )
            ohlc_store[t] = ohlc_df

            mass_df = pd.DataFrame(
                {"open": massive_prices, "high": massive_prices,
                 "low": massive_prices, "close": massive_prices, "volume": np.ones(n) * 1000},
                index=dates,
            )
            mass_df.to_parquet(massive_dir / f"{t}.parquet")

        return ohlc_store, tmp_path

    def _make_w01_df(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "family": "ep_onset_in", "node": "XLK", "trigger_date": "2020-01-02",
            "parameterization": "rot21", "dedup_variant": "raw",
            "direction": "in", "sigma20": 0.08, "state": "STOPPED",
        }])

    def test_g2_passes_matching_prices(self, tmp_path):
        """G2 passes when OHLC and massive_stock_day close returns agree."""
        w01_df = self._make_w01_df()
        ohlc_store, data_dir = self._make_stores(tmp_path)
        # No SystemExit expected
        run_fidelity_gate(w01_df, ohlc_store, data_dir)

    def test_g2_aborts_on_divergent_returns(self, tmp_path):
        """G2 must abort when OHLC returns diverge from massive_stock_day by >0.1%.

        Simulate a 5% level offset that translates into a return divergence on the
        very first consecutive pair sampled (since returns-based: (105/104 - 1) vs
        (100/100 - 1) → divergence on rising vs flat).
        """
        n = 50
        # ohlc: steadily rising (each bar 1% higher) → day-over-day return ~1%
        ohlc_prices = 100.0 * (1.01 ** np.arange(n))
        # massive: flat at 100 → day-over-day return = 0%
        # Return difference ≈ 1% >> 0.001 threshold → must abort
        massive_prices = np.ones(n) * 100.0

        w01_df = self._make_w01_df()
        ohlc_store, data_dir = self._make_stores(
            tmp_path, ohlc_prices=ohlc_prices, massive_prices=massive_prices
        )
        with pytest.raises(SystemExit):
            run_fidelity_gate(w01_df, ohlc_store, data_dir)
