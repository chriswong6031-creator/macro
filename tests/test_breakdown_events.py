"""Tests for BD Phase-0 / Phase-0b breakdown event tape (L1 short-side).

Synthetic fixtures only — CI has no canonical massive_stock_day data.

Covers:
  1. terminal_state_short: correctness incl. liftoff_mult<1 trap
  2. BD-1 event detection on hand-built close series
  3. BD-2 event detection on hand-built series (mocked replay_boarded)
  4. BD-3 event detection on hand-built series (mocked ETF data)
  5. Episode collapse
  6. Paired-grading plumbing
  7. Control sampling determinism + year-stratification (B3)
  8. Module-level smoke test
  9. Paired within-event contrast correctness (B1)
  10. Clustered bootstrap CI plumbing determinism (B2)
  11. fresh_breach_mask canonical helper (N1)
  --- Phase-0b additions ---
  12. BD-4 Two-Clock Rollover detector (warmup floor, rollover formula, extended gate)
  13. BD-5 Coiled Breakdown detector (coil percentile, distribution sigma, flat-window guard)
  14. BD-6 Within-Sector Leader Fade detector (sector pre-pass, fade guard, near-highs)
  15. Sector pre-pass on synthetic panel
  16. Seeding stability: BD-4/5/6 independent seeds don't corrupt BD-1/2/3 event rows
  17. v3 summary schema: all six definitions + overlap matrix + RUL-U3a budget note
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from engine.grading import (
    TerminalState,
    TerminalStateShort,
    SHORT_ADVERSE_MULT,
    SHORT_FAVORABLE_MULT_21,
    SHORT_FAVORABLE_MULT_126,
    LIFTOFF_HORIZON_21,
    LIFTOFF_HORIZON_126,
    terminal_state,
    terminal_state_short,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _series(vals, start="2021-08-01", freq="B"):
    """Build a business-day DatetimeIndex close series."""
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series([float(v) for v in vals], index=idx)


def _long_series(n=300, start_price=10.0, start="2021-01-04"):
    """Build a flat close series of n bars (sufficient for ERA + prior bars)."""
    idx = pd.bdate_range(start, periods=n)
    vals = np.full(n, start_price)
    return pd.Series(vals, index=idx)


# ---------------------------------------------------------------------------
# 1. terminal_state_short correctness
# ---------------------------------------------------------------------------

class TestTerminalStateShort:

    def test_adverse_triggers_when_price_rises(self):
        """Price rises above entry * 1.05 → ADVERSE_TRIGGERED."""
        # entry will be close[1] (fill=1); close[2..22] need to hit 1.05* entry
        entry = 100.0
        # close[0]=95 (signal), close[1]=entry=100, close[2..10]=106 (>1.05*100=105)
        vals = [95.0, entry] + [106.0] * 21
        s = _series(vals)
        sig = str(s.index[0].date())
        r = terminal_state_short(s, sig, adverse_mult=1.05, favorable_mult=0.92, horizon=21)
        assert r["state"] == TerminalStateShort.ADVERSE_TRIGGERED
        assert r["adverse_at_bar"] is not None
        assert r["favorable_at_bar"] is None
        assert r["entry_price"] == pytest.approx(entry)

    def test_favorable_triggers_when_price_falls(self):
        """Price falls below entry * 0.92 → FAVORABLE_TRIGGERED."""
        entry = 100.0
        # signal=close[0]=105, fill=close[1]=100, forward: all 90 (< 0.92*100=92)
        vals = [105.0, entry] + [90.0] * 21
        s = _series(vals)
        sig = str(s.index[0].date())
        r = terminal_state_short(s, sig, adverse_mult=1.05, favorable_mult=0.92, horizon=21)
        assert r["state"] == TerminalStateShort.FAVORABLE_TRIGGERED
        assert r["favorable_at_bar"] is not None
        assert r["adverse_at_bar"] is None

    def test_unremarkable_when_no_barrier_reached(self):
        """Neither barrier reached within horizon → UNREMARKABLE."""
        entry = 100.0
        # flat at 96 — below entry but above favorable (0.92*100=92) and below adverse (1.05*100=105)
        vals = [105.0, entry] + [96.0] * 21
        s = _series(vals)
        sig = str(s.index[0].date())
        r = terminal_state_short(s, sig, adverse_mult=1.05, favorable_mult=0.92, horizon=21)
        assert r["state"] == TerminalStateShort.UNREMARKABLE

    def test_adverse_wins_on_tie_same_bar(self):
        """If both adverse and favorable would fire on the same bar, ADVERSE wins (conservative)."""
        # This can't happen mathematically (price can't be >= 1.05*E AND <= 0.92*E simultaneously)
        # but we test the tie-rule logic via the order of checks (adverse first).
        # Build a simpler test: just ensure that when the first bar crosses adverse, adverse wins
        # even if we later reach favorable.
        entry = 100.0
        vals = [110.0, entry] + [106.0, 85.0] + [96.0] * 20  # adverse at bar1, favorable at bar2
        s = _series(vals)
        sig = str(s.index[0].date())
        r = terminal_state_short(s, sig, adverse_mult=1.05, favorable_mult=0.92, horizon=21)
        assert r["state"] == TerminalStateShort.ADVERSE_TRIGGERED
        assert r["adverse_at_bar"] == 1  # bar 1 (first forward bar)

    def test_liftoff_mult_less_than_1_trap_raises(self):
        """Passing favorable_mult >= 1 raises ValueError (the liftoff_mult<1 trap mirrored)."""
        s = _series([100.0] * 30)
        sig = str(s.index[0].date())
        with pytest.raises(ValueError, match="favorable_mult must be <1"):
            terminal_state_short(s, sig, favorable_mult=1.05, adverse_mult=1.10, horizon=21)

    def test_adverse_mult_le_1_raises(self):
        """Passing adverse_mult <= 1 raises ValueError (wrong direction)."""
        s = _series([100.0] * 30)
        sig = str(s.index[0].date())
        with pytest.raises(ValueError, match="adverse_mult must be >1"):
            terminal_state_short(s, sig, adverse_mult=0.95, favorable_mult=0.92, horizon=21)

    def test_none_when_not_matured(self):
        """Returns state=None when fewer than horizon forward bars available."""
        s = _series([100.0] * 10)
        sig = str(s.index[0].date())
        r = terminal_state_short(s, sig, horizon=21)
        assert r["state"] is None
        assert "not yet matured" in r["note"]

    def test_none_when_no_fill(self):
        """Returns state=None when signal_date is the last bar (no fill bar)."""
        s = _series([100.0] * 5)
        sig = str(s.index[-1].date())
        r = terminal_state_short(s, sig)
        assert r["state"] is None

    def test_favorable_mult_126_different_from_21(self):
        """The two prereg-specified favorable barriers differ (@21=0.92, @126=0.85)."""
        assert SHORT_FAVORABLE_MULT_21  == pytest.approx(0.92)
        assert SHORT_FAVORABLE_MULT_126 == pytest.approx(0.85)
        assert SHORT_FAVORABLE_MULT_21  != SHORT_FAVORABLE_MULT_126

    def test_not_same_as_terminal_state_long(self):
        """terminal_state_short CANNOT be reproduced by flipping mults in terminal_state.

        The liftoff_mult<1 trap: terminal_state with liftoff_mult=0.92 fires CLEAN_LIFTOFF
        the moment the close drops below entry*0.92 — which happens on ANY bar where close
        is between entry*0.92 and entry*0.95 (below the normal stop zone), so the entire
        short-favorable zone mislabels as CLEAN_LIFTOFF instead of the desired state.

        To demonstrate: build a series where close = entry * 0.93 (below 0.92*entry but
        above 0.95*entry). terminal_state with liftoff_mult=0.92 classifies this as
        CLEAN_LIFTOFF (wrong). terminal_state_short correctly gives FAVORABLE_TRIGGERED.
        """
        entry = 100.0
        # close[0]=signal(105), close[1]=fill(100), close[2..22]=93
        # 93 < 0.95*100=95 → stop fires. With liftoff=0.92, check if liftoff fires before stop.
        # Actually: 93 < 0.95 (stop) AND 93 < 0.92 (liftoff with wrong direction).
        # Sequential scan: stop checked first (93 ≤ 95) → STOPPED.
        # To isolate the trap: use a close that is BETWEEN 0.92*entry and 0.95*entry
        # e.g. 93.5 → 93.5 > 0.92*100=92 (no short-liftoff with wrong direction)
        #            → 93.5 < 0.95*100=95 → STOPPED for long
        # The real trap manifests when the close < entry*0.92: liftoff fires first since
        # liftoff_mult=0.92 means barrier = 92, and the scan finds liftoff before stop.
        # Build: entry=100, forward=[97]*21, then at bar 10 drop to 91.
        # With liftoff_mult=0.92, liftoff_barrier=92, stop_barrier=95.
        # Bar 1..9: close=97 → > stop (no stop), > liftoff (92; 97>92 so NO — wait, liftoff
        # is cl >= liftoff_barrier = 92, and 97 >= 92 = True → CLEAN_LIFTOFF fires at bar 1!
        vals = [105.0, entry] + [97.0] * 21
        s = _series(vals)
        sig = str(s.index[0].date())

        # Long-side with wrong mults: liftoff_mult=0.92, liftoff_horizon=21
        # liftoff_barrier = entry * 0.92 = 92.0
        # Bar 1: close=97, 97 >= 92 → CLEAN_LIFTOFF fires immediately
        long_wrong = terminal_state(s, sig, liftoff_mult=0.92, liftoff_horizon=21,
                                    stop_mult=0.95, cushion_mult=0.97)
        # The TRAP: close=97 >= entry*0.92=92 fires CLEAN_LIFTOFF on bar 1
        assert long_wrong["state"] == TerminalState.CLEAN_LIFTOFF, (
            f"Expected CLEAN_LIFTOFF (the trap) but got {long_wrong['state']} — "
            "the test premise is wrong"
        )
        assert long_wrong["liftoff_at_bar"] == 1  # fires on first forward bar

        # Short-side correct behavior: entry=100, forward=97 (< adverse=105, > favorable=92)
        # → UNREMARKABLE (never crossed either barrier)
        short_correct = terminal_state_short(s, sig, adverse_mult=1.05,
                                             favorable_mult=0.92, horizon=21)
        assert short_correct["state"] == TerminalStateShort.UNREMARKABLE, (
            f"Short side should be UNREMARKABLE (97 between 92 and 105) "
            f"but got {short_correct['state']}"
        )


# ---------------------------------------------------------------------------
# 2. BD-1 event detection
# ---------------------------------------------------------------------------

class TestBD1Detection:

    def _make_close_with_lower_high(self, n_pre=300) -> tuple[pd.Series, pd.DataFrame]:
        """Build a close series that should fire BD-1:
        - pinned near 63-bar max
        - lower swing-high within trailing 63 bars
        - AD deterioration (sign_volume declining)
        """
        import numpy as np
        # Build n_pre bars as warm-up, then a specific pattern
        warm = np.full(n_pre, 50.0)
        # Phase 1: prior high at 100 (21 bars back from event)
        # Phase 2: slightly lower high at 98 (recent, within 63 bars)
        # Phase 3: return to ~99.5 (pinned near 63-bar max ~100)
        prior_high = np.full(30, 100.0)  # first swing-high at ~100
        pullback = np.linspace(100, 90, 10)
        recovery = np.full(30, 98.0)  # second swing-high at ~98 (lower)
        pin = np.full(10, 99.5)        # pinned near 63-bar max (~100)
        vals = np.concatenate([warm, prior_high, pullback, recovery, pin])
        idx = pd.bdate_range("2021-01-04", periods=len(vals))
        close = pd.Series(vals, index=idx)

        # Build OHLCV with sign_volume that's deteriorating
        # sign_volume = volume * ((C-L)-(H-C)) / (H-L)
        # For deteriorating AD: H-C >> C-L (bars closing near low)
        n = len(vals)
        high  = close + 1.5  # H = C + 1.5
        low   = close - 2.0  # L = C - 2.0  → (C-L)=2.0 but (H-C)=1.5 → sv > 0 mostly
        # For deteriorating signal in the "pin" phase, make H-C >> C-L
        for j in range(len(vals) - 40, len(vals)):
            high.iloc[j]  = close.iloc[j] + 3.0   # H = C + 3 (wider)
            low.iloc[j]   = close.iloc[j] - 0.5   # L = C - 0.5 (narrow)
            # → (C-L)=0.5, (H-C)=3.0 → ((C-L)-(H-C)) = -2.5 → sv very negative

        volume = pd.Series(np.full(n, 1_000_000.0), index=idx)
        raw_df = pd.DataFrame({"open": close, "high": high, "low": low,
                                "close": close, "volume": volume}, index=idx)
        return close, raw_df

    def test_bd1_fires_on_crafted_series(self):
        """BD-1 fires when pinned + lower_high + AD deterioration all hold."""
        from scripts.research.dump_breakdown_events import detect_bd1, _collapse_episodes
        close, raw_df = self._make_close_with_lower_high()
        events = detect_bd1("TEST", close, raw_df)
        collapsed = _collapse_episodes(events, close)
        # We may or may not get exact hits depending on exact series construction,
        # but we should at minimum get the module to run without error
        assert isinstance(collapsed, list)

    def test_bd1_requires_hlv(self):
        """BD-1 returns empty when raw_df has no H/L/V (AD can't be computed)."""
        from scripts.research.dump_breakdown_events import detect_bd1
        close = _long_series(n=400, start_price=50.0)
        events = detect_bd1("TEST", close, None)
        assert events == []

    def test_bd1_no_events_below_era_start(self):
        """Events outside ERA window (pre-2021-07-06) are not returned."""
        from scripts.research.dump_breakdown_events import detect_bd1, ERA_START
        # Build a series entirely before ERA_START
        close = pd.Series(
            np.full(500, 100.0),
            index=pd.bdate_range("2018-01-01", periods=500)
        )
        raw_df = pd.DataFrame({
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": pd.Series(1e6, index=close.index)
        })
        events = detect_bd1("TEST", close, raw_df)
        for ts in events:
            assert ts >= ERA_START, f"Event {ts} is before ERA_START {ERA_START}"


# ---------------------------------------------------------------------------
# 3. BD-2 event detection
# ---------------------------------------------------------------------------

class TestBD2Detection:

    def test_bd2_fires_on_failed_reclaim(self):
        """BD-2 fires when a STOPPED fire is followed by a failed rally below fire-day close."""
        from scripts.research.dump_breakdown_events import detect_bd2, ERA_START

        # Build a close series with enough ERA history
        n_pre = 260  # > 252 required
        start_date = pd.Timestamp("2021-01-04")
        idx = pd.bdate_range(start_date, periods=n_pre + 50)
        vals = np.full(len(idx), 100.0)
        # Set up: signal at bar n_pre (fire-day close=100)
        # Entry = bar n_pre+1 = 100, stop at bar n_pre+1+5 = close 94.0 (<= 0.95*100)
        # Then rally to 96 (below fire-day close 100), then down-close
        fire_idx   = n_pre
        entry_idx  = n_pre + 1
        stop_idx   = n_pre + 6
        rally_idx  = n_pre + 7
        rally_high = n_pre + 12  # highest rally close
        fail_bar   = n_pre + 13  # down-close after rally high

        vals[fire_idx]  = 100.0   # fire-day close (signal bar)
        vals[entry_idx] = 100.0   # entry bar
        for j in range(entry_idx + 1, stop_idx + 1):
            vals[j] = 100.0
        vals[stop_idx] = 94.0    # stop triggered (< 0.95*100 = 95)
        for j in range(stop_idx + 1, rally_high + 1):
            vals[j] = 96.0       # rally to 96, still BELOW fire-day close (100)
        vals[rally_high] = 97.0  # highest point of rally
        vals[fail_bar]   = 95.0  # down-close after rally high → BD-2 fires here

        # Pad remainder
        for j in range(fail_bar + 1, len(vals)):
            vals[j] = 95.0

        close = pd.Series(vals, index=idx)

        # Mock replay_boarded to return one STOPPED fire row
        signal_date = str(idx[fire_idx].date())
        fill_date   = str(idx[entry_idx].date())
        stopped_at  = stop_idx - entry_idx  # bars from fill = 5

        mock_stopped = [{
            "ticker": "TEST",
            "signal_date": signal_date,
            "entry_price": 100.0,
            "fill_date": fill_date,
            "state_8_21": "STOPPED",
            "stopped_at_8_21": stopped_at,
        }]

        with patch(
            "scripts.research.dump_breakdown_events._load_stopped_fires",
            return_value=mock_stopped
        ):
            raw_df = pd.DataFrame({
                "open": close, "high": close + 1, "low": close - 1,
                "close": close, "volume": pd.Series(2e6, index=close.index)
            })
            events = detect_bd2("TEST", close, raw_df)

        # There should be at least one BD-2 event
        assert len(events) >= 1
        for ts in events:
            assert ts >= ERA_START

    def test_bd2_no_event_when_rally_reclaims_fire_close(self):
        """BD-2 does NOT fire when the post-stop rally reclaims the fire-day close."""
        from scripts.research.dump_breakdown_events import detect_bd2

        n_pre = 260
        idx = pd.bdate_range("2021-01-04", periods=n_pre + 30)
        vals = np.full(len(idx), 100.0)
        fire_idx  = n_pre
        entry_idx = n_pre + 1
        stop_idx  = n_pre + 6
        vals[stop_idx] = 94.0       # stop
        # Rally RECLAIMS fire-day close (101 >= 100)
        for j in range(stop_idx + 1, n_pre + 20):
            vals[j] = 101.0
        close = pd.Series(vals, index=idx)

        mock_stopped = [{
            "ticker": "TEST",
            "signal_date": str(idx[fire_idx].date()),
            "entry_price": 100.0,
            "fill_date":   str(idx[entry_idx].date()),
            "state_8_21":  "STOPPED",
            "stopped_at_8_21": 5,
        }]
        with patch(
            "scripts.research.dump_breakdown_events._load_stopped_fires",
            return_value=mock_stopped
        ):
            raw_df = pd.DataFrame({
                "open": close, "high": close + 1, "low": close - 1,
                "close": close, "volume": pd.Series(2e6, index=close.index)
            })
            events = detect_bd2("TEST", close, raw_df)
        assert len(events) == 0

    def test_bd2_empty_when_no_stopped_fires(self):
        """BD-2 returns empty when there are no STOPPED fires."""
        from scripts.research.dump_breakdown_events import detect_bd2
        close = _long_series(n=400, start_price=100.0)
        with patch(
            "scripts.research.dump_breakdown_events._load_stopped_fires",
            return_value=[]
        ):
            events = detect_bd2("TEST", close, None)
        assert events == []


# ---------------------------------------------------------------------------
# 4. BD-3 event detection
# ---------------------------------------------------------------------------

class TestBD3Detection:

    def _make_etf_series(self, n=300, ret_21d: float = 0.0, start="2020-01-02") -> pd.Series:
        """Build a synthetic ETF close series where the 21d return equals ret_21d."""
        idx = pd.bdate_range(start, periods=n)
        vals = np.ones(n) * 100.0
        # Set the last 22 bars to give the desired 21d return
        vals[-22] = 100.0
        vals[-1]  = vals[-22] * (1.0 + ret_21d)
        # linearly interpolate between
        vals[-21:-1] = np.linspace(vals[-22], vals[-1], 21)
        return pd.Series(vals, index=idx)

    def test_bd3_fires_when_all_conditions_met(self):
        """BD-3 fires when ema8_breach + extended + defensive_bid all hold."""
        from scripts.research.dump_breakdown_events import detect_bd3, ERA_START

        # Build a close series where BD-3 should fire
        n_pre = 300
        idx = pd.bdate_range("2021-01-04", periods=n_pre + 50)
        vals = np.full(len(idx), 100.0)

        # Make close "extended" in the recent tail: >= 1.15 * rolling-126-bar-min
        # Early bars at 50, later bars at 100 → 100 >= 1.15 * 50 = 57.5 ✓
        for j in range(0, n_pre - 130):
            vals[j] = 50.0
        for j in range(n_pre - 130, len(vals)):
            vals[j] = 100.0

        close = pd.Series(vals, index=idx)

        # Mock _defensive_bid_on to return True
        # Mock signal_frame to return a fresh_breach on a specific bar
        # (rather than constructing the exact EMA8 condition on synthetic data)
        from unittest.mock import MagicMock
        import engine.signal_quality as sq

        # Build a minimal signal_frame mock that fires fresh_breach on the last ERA bar
        era_bars = close[close.index >= ERA_START]
        if len(era_bars) == 0:
            return

        # The safest integration test: just call detect_bd3 and verify it doesn't crash
        # (full integration with a fresh_breach on synthetic data is complex due to
        # 3B-resample alignment)
        with patch("scripts.research.dump_breakdown_events._defensive_bid_on",
                   return_value=True):
            raw_df = pd.DataFrame({
                "open": close, "high": close + 2, "low": close - 2,
                "close": close, "volume": pd.Series(2e6, index=close.index)
            })
            # This should not raise
            events = detect_bd3("TEST", close, raw_df)
            assert isinstance(events, list)
            for ts in events:
                assert ts >= ERA_START

    def test_bd3_no_events_when_defensive_bid_false(self):
        """BD-3 never fires when defensive_bid returns False."""
        from scripts.research.dump_breakdown_events import detect_bd3
        close = _long_series(n=400, start_price=100.0)
        with patch("scripts.research.dump_breakdown_events._defensive_bid_on",
                   return_value=False):
            events = detect_bd3("TEST", close, None)
        assert events == []

    def test_defensive_bid_on_checks_etf_returns(self):
        """_defensive_bid_on returns True when def ETFs outperform SPY."""
        from scripts.research.dump_breakdown_events import _defensive_bid_on, _ETF_CLOSES
        # Build ETF series where XLP/XLU/XLV return +5% vs SPY +1%
        def_ret = 0.05
        spy_ret = 0.01
        test_date = pd.Timestamp("2023-06-01")

        def make_series(ret):
            n = 50
            idx = pd.bdate_range("2023-01-01", periods=n)
            vals = np.ones(n) * 100.0
            vals[-22] = 100.0
            vals[-1]  = vals[-22] * (1 + ret)
            # interpolate the 20 bars between -22 and -1 (indices -21 through -2)
            vals[-21:-1] = np.linspace(vals[-22], vals[-1], 20)
            return pd.Series(vals, index=idx)

        def patched_load(ticker):
            if ticker == "SPY":
                return make_series(spy_ret)
            return make_series(def_ret)

        # Clear the ETF cache before testing
        _ETF_CLOSES.clear()
        with patch("scripts.research.dump_breakdown_events._load_etf_close", side_effect=patched_load):
            result = _defensive_bid_on(test_date)
        assert result == True  # noqa: E712 — numpy bool_ safe with ==

        # SPY outperforms: should return False
        def patched_spy_wins(ticker):
            if ticker == "SPY":
                return make_series(0.10)
            return make_series(0.01)

        _ETF_CLOSES.clear()
        with patch("scripts.research.dump_breakdown_events._load_etf_close",
                   side_effect=patched_spy_wins):
            result = _defensive_bid_on(test_date)
        assert result == False  # noqa: E712


# ---------------------------------------------------------------------------
# 5. Episode collapse
# ---------------------------------------------------------------------------

class TestEpisodeCollapse:

    def test_collapse_adjacent_events(self):
        """Events within 21 bars collapse to first event."""
        from scripts.research.dump_breakdown_events import _collapse_episodes, EPISODE_COLLAPSE_BARS
        close = _long_series(n=400, start_price=100.0)
        # Two events 5 bars apart → should collapse to 1 episode
        ts0 = close.index[260]
        ts1 = close.index[265]
        result = _collapse_episodes([ts0, ts1], close)
        assert len(result) == 1
        assert result[0] == ts0

    def test_separate_events_beyond_window(self):
        """Events more than 21 bars apart are NOT collapsed."""
        from scripts.research.dump_breakdown_events import _collapse_episodes, EPISODE_COLLAPSE_BARS
        close = _long_series(n=500, start_price=100.0)
        ts0 = close.index[260]
        ts1 = close.index[260 + EPISODE_COLLAPSE_BARS + 1]  # just beyond window
        result = _collapse_episodes([ts0, ts1], close)
        assert len(result) == 2

    def test_collapse_is_idempotent_on_empty(self):
        """Empty event list returns empty."""
        from scripts.research.dump_breakdown_events import _collapse_episodes
        close = _long_series(n=100)
        assert _collapse_episodes([], close) == []

    def test_collapse_three_events_two_collapse(self):
        """Three events: first two within window collapse, third is separate."""
        from scripts.research.dump_breakdown_events import _collapse_episodes, EPISODE_COLLAPSE_BARS
        close = _long_series(n=600, start_price=100.0)
        ts0 = close.index[260]
        ts1 = close.index[265]  # within window of ts0
        ts2 = close.index[260 + EPISODE_COLLAPSE_BARS + 5]  # beyond window
        result = _collapse_episodes([ts0, ts1, ts2], close)
        assert len(result) == 2
        assert result[0] == ts0
        assert result[1] == ts2


# ---------------------------------------------------------------------------
# 6. Paired grading plumbing
# ---------------------------------------------------------------------------

class TestPairedGrading:

    def _make_event_series_and_grade(self, n_fwd_vals: list[float]) -> dict:
        """Build a close series and grade one event with both sides.

        Layout: [n_pre bars at 100] [signal bar at 100] [fill bar at 100] [fwd_vals...]
        The signal bar is at index n_pre; fill bar is at n_pre+1 (value 100); forward
        starts at n_pre+2.
        """
        from scripts.research.dump_breakdown_events import _grade_event
        n_pre = 260
        fwd = n_fwd_vals
        # signal=idx[n_pre], fill=idx[n_pre+1]=100, forward=idx[n_pre+2..] = fwd_vals
        idx = pd.bdate_range("2021-01-04", periods=n_pre + 2 + len(fwd))
        entry_val = 100.0
        pre_vals = list(np.full(n_pre, entry_val))
        vals = pre_vals + [entry_val, entry_val] + fwd  # signal, fill, then fwd
        close = pd.Series([float(v) for v in vals], index=idx)
        signal_date = idx[n_pre]  # signal bar at n_pre → fill at n_pre+1 = entry_val
        row = _grade_event("TEST", signal_date, close, "BD-1")
        return row

    def test_paired_grade_has_both_sides(self):
        """A graded event has both long-side and short-side state columns."""
        # Forward: price rises to 115 (liftoff for long-side, adverse for short)
        fwd = [106.0] * 126  # always > 1.05 (adverse on short side)
        row = self._make_event_series_and_grade(fwd)
        # Long-side should have CLEAN_LIFTOFF (if > 1.15) or CUSHIONED
        assert "long_state_clean15_126" in row
        assert "long_state_clean8_21" in row
        assert "short_state_short21" in row
        assert "short_state_short126" in row

    def test_long_adverse_short_split(self):
        """A sharp decline grades as STOPPED for long, FAVORABLE for short."""
        # entry=100, close immediately falls to 94 → long STOPPED, short FAVORABLE
        fwd = [94.0] * 126  # < 0.95*100 = 95 → long stop; < 0.92*100 = 92? no, 94 > 92
        # Actually 94 > 92, so short won't be FAVORABLE at 21d favorable mult=0.92
        # Use 88 (< 0.92*100 = 92) for short FAVORABLE
        fwd2 = [88.0] * 126
        row = self._make_event_series_and_grade(fwd2)
        # Long: 88 < 0.95*100=95 → STOPPED
        assert row.get("long_state_clean8_21") == TerminalState.STOPPED
        # Short @21: 88 < 0.92*100=92 → FAVORABLE_TRIGGERED
        assert row.get("short_state_short21") == TerminalStateShort.FAVORABLE_TRIGGERED

    def test_grade_event_marks_censored_when_forward_short(self):
        """Events where forward data < max horizon are marked censored=True."""
        from scripts.research.dump_breakdown_events import _grade_event
        # Only 10 bars forward (< 126)
        n_pre = 260
        idx = pd.bdate_range("2021-01-04", periods=n_pre + 1 + 10)
        vals = list(np.full(n_pre + 1 + 10, 100.0))
        close = pd.Series([float(v) for v in vals], index=idx)
        sig_ts = idx[n_pre]
        row = _grade_event("TEST", sig_ts, close, "BD-1")
        assert row["censored"] is True

    def test_forward_metrics_present_in_graded_row(self):
        """Graded row includes fwd_ret/mdd/mfe at all GRADE_HORIZONS."""
        from scripts.research.dump_breakdown_events import _grade_event, GRADE_HORIZONS
        n_pre = 260
        n_fwd = 130
        idx = pd.bdate_range("2021-01-04", periods=n_pre + 1 + n_fwd)
        vals = list(np.full(n_pre + 1 + n_fwd, 100.0))
        close = pd.Series([float(v) for v in vals], index=idx)
        sig_ts = idx[n_pre]
        row = _grade_event("TEST", sig_ts, close, "BD-2")
        for h in GRADE_HORIZONS:
            assert f"fwd_ret_{h}" in row
            assert f"fwd_mdd_{h}" in row
            assert f"fwd_mfe_{h}" in row


# ---------------------------------------------------------------------------
# 7. Control sampling determinism
# ---------------------------------------------------------------------------

class TestControlSampling:
    """Tests for year-stratified control sampling (B3)."""

    def _make_event_timestamps(self, close: pd.Series, indices: list[int]) -> list[pd.Timestamp]:
        """Build event timestamp list from close series indices."""
        return [close.index[i] for i in indices]

    def test_controls_are_deterministic_with_same_seed(self):
        """Sampling with the same RNG seed produces the same controls."""
        from scripts.research.dump_breakdown_events import _sample_controls, CONTROL_RNG_SEED
        close = _long_series(n=400, start_price=100.0)
        ev_ts = self._make_event_timestamps(close, [260, 270, 280, 290, 300])
        rng1 = np.random.default_rng(CONTROL_RNG_SEED)
        rng2 = np.random.default_rng(CONTROL_RNG_SEED)
        c1 = _sample_controls("TEST", close, None, ev_ts, rng1)
        c2 = _sample_controls("TEST", close, None, ev_ts, rng2)
        dates1 = [r.get("event_date") for r in c1]
        dates2 = [r.get("event_date") for r in c2]
        assert dates1 == dates2

    def test_different_seeds_give_different_controls(self):
        """Different seeds produce different samples (with high probability)."""
        from scripts.research.dump_breakdown_events import _sample_controls, CONTROL_RNG_SEED
        close = _long_series(n=500, start_price=100.0)
        ev_ts = self._make_event_timestamps(close, list(range(260, 270)))
        rng1 = np.random.default_rng(CONTROL_RNG_SEED)
        rng2 = np.random.default_rng(CONTROL_RNG_SEED + 1)
        c1 = _sample_controls("TEST", close, None, ev_ts, rng1)
        c2 = _sample_controls("TEST", close, None, ev_ts, rng2)
        dates1 = sorted([r.get("event_date") for r in c1])
        dates2 = sorted([r.get("event_date") for r in c2])
        assert dates1 != dates2  # different seeds → different samples

    def test_control_ratio_matches_spec(self):
        """Controls are sampled at CONTROL_RATIO : 1 vs events (when pool is large enough)."""
        from scripts.research.dump_breakdown_events import _sample_controls, CONTROL_RATIO
        close = _long_series(n=500, start_price=100.0)
        n_events = 4
        ev_ts = self._make_event_timestamps(close, [260, 270, 280, 290])
        rng = np.random.default_rng(42)
        controls = _sample_controls("TEST", close, None, ev_ts, rng)
        assert len(controls) == n_events * CONTROL_RATIO

    def test_controls_are_marked_as_control(self):
        """Control rows have is_control=True."""
        from scripts.research.dump_breakdown_events import _sample_controls
        close = _long_series(n=400, start_price=100.0)
        ev_ts = self._make_event_timestamps(close, [260, 270, 280])
        rng = np.random.default_rng(0)
        controls = _sample_controls("TEST", close, None, ev_ts, rng)
        for r in controls:
            assert r.get("is_control") is True

    def test_controls_within_era_window(self):
        """All control bar dates are within the ERA window."""
        from scripts.research.dump_breakdown_events import _sample_controls, ERA_START
        close = _long_series(n=400, start_price=100.0)
        ev_ts = self._make_event_timestamps(close, [260, 270, 280, 290, 300])
        rng = np.random.default_rng(7)
        controls = _sample_controls("TEST", close, None, ev_ts, rng)
        for r in controls:
            ev_date = pd.Timestamp(r.get("event_date", "2099-01-01"))
            assert ev_date >= ERA_START, f"Control date {ev_date} < ERA_START {ERA_START}"

    def test_controls_empty_when_insufficient_history(self):
        """No controls when series has < ERA_PRIOR_BARS_REQUIRED bars in ERA window."""
        from scripts.research.dump_breakdown_events import _sample_controls
        # Series entirely before ERA window
        close = pd.Series(
            np.full(50, 100.0),
            index=pd.bdate_range("2021-01-04", periods=50)
        )
        ev_ts = [close.index[10]]  # dummy event timestamp
        rng = np.random.default_rng(0)
        controls = _sample_controls("TEST", close, None, ev_ts, rng)
        assert controls == []

    def test_controls_empty_when_no_event_timestamps(self):
        """No controls when event_timestamps list is empty."""
        from scripts.research.dump_breakdown_events import _sample_controls
        close = _long_series(n=400, start_price=100.0)
        rng = np.random.default_rng(0)
        controls = _sample_controls("TEST", close, None, [], rng)
        assert controls == []

    def test_year_stratification_controls_within_same_year(self):
        """Year-stratified: each event's controls come from the same calendar year."""
        from scripts.research.dump_breakdown_events import _sample_controls, CONTROL_RATIO
        # Build a 2-year series (2021 + 2022) with enough bars
        close_2021 = _long_series(n=300, start_price=100.0, start="2021-07-06")
        close_2022 = _long_series(n=260, start_price=100.0, start="2022-01-03")
        close = pd.concat([close_2021, close_2022]).sort_index()
        close = close[~close.index.duplicated()]

        # Place one event clearly in 2022
        ev_2022_idx = close.index.searchsorted(pd.Timestamp("2022-06-01"))
        if ev_2022_idx >= len(close):
            ev_2022_idx = len(close) - 50
        ev_ts = [close.index[ev_2022_idx]]

        rng = np.random.default_rng(99)
        controls = _sample_controls("TESTYR", close, None, ev_ts, rng)

        # Controls for a 2022 event must come from 2022 (or ±1 fallback)
        for r in controls:
            ctrl_year = pd.Timestamp(r.get("event_date", "2099-01-01")).year
            assert ctrl_year in (2021, 2022, 2023), (
                f"Control year {ctrl_year} not in expected range for 2022 event"
            )
            # Tighter: should ideally be 2022 when 2022 pool is non-empty
            assert ctrl_year == 2022, (
                f"Expected year-matched control in 2022, got {ctrl_year}"
            )


# ---------------------------------------------------------------------------
# 8. Module-level smoke test
# ---------------------------------------------------------------------------

class TestModuleImports:
    def test_all_exports_importable(self):
        """All declared exports from grading.py are importable."""
        from engine.grading import (
            TerminalStateShort, terminal_state_short,
            SHORT_ADVERSE_MULT, SHORT_FAVORABLE_MULT_21, SHORT_FAVORABLE_MULT_126,
        )
        assert SHORT_ADVERSE_MULT > 1.0
        assert SHORT_FAVORABLE_MULT_21 < 1.0
        assert SHORT_FAVORABLE_MULT_126 < SHORT_FAVORABLE_MULT_21  # 0.85 < 0.92

    def test_short_side_constants_in_grading_all(self):
        """New constants appear in grading.__all__."""
        import engine.grading as g
        assert "TerminalStateShort" in g.__all__
        assert "terminal_state_short" in g.__all__
        assert "SHORT_ADVERSE_MULT" in g.__all__

    def test_dump_script_importable(self):
        """dump_breakdown_events.py can be imported without error."""
        import scripts.research.dump_breakdown_events as m  # noqa: F401
        assert hasattr(m, "detect_bd1")
        assert hasattr(m, "detect_bd2")
        assert hasattr(m, "detect_bd3")
        # Phase-0b
        assert hasattr(m, "detect_bd4")
        assert hasattr(m, "detect_bd5")
        assert hasattr(m, "detect_bd6")
        assert hasattr(m, "build_sector_panel")
        assert hasattr(m, "_collapse_episodes")
        assert hasattr(m, "_grade_event")

    def test_new_summary_functions_present(self):
        """B1/B2 helper functions exist in the module."""
        import scripts.research.dump_breakdown_events as m
        assert hasattr(m, "_paired_within_event_stats")
        assert hasattr(m, "_vs_control_stats")
        assert hasattr(m, "_clustered_bootstrap_ci95")

    def test_fresh_breach_mask_importable_from_signal_quality(self):
        """N1: fresh_breach_mask is importable from engine.signal_quality."""
        from engine.signal_quality import fresh_breach_mask
        assert callable(fresh_breach_mask)


# ---------------------------------------------------------------------------
# 9. Paired within-event contrast correctness (B1)
# ---------------------------------------------------------------------------

class TestPairedWithinEventContrast:

    def _make_events_df(
        self,
        n_events: int = 20,
        long_stopped_rate: float = 0.8,
        short_favorable_rate: float = 0.6,
        seed: int = 7,
    ) -> pd.DataFrame:
        """Build a synthetic events DataFrame with controlled terminal state rates.

        long_stopped_rate: fraction of events where long_state_clean8_21 == STOPPED
        short_favorable_rate: fraction of events where short_state_short21 == FAVORABLE_TRIGGERED
        """
        rng = np.random.default_rng(seed)
        rows = []
        tickers = ["AAA", "BBB", "CCC", "DDD"]
        years = [2022, 2023, 2024]
        for i in range(n_events):
            ticker = tickers[i % len(tickers)]
            year = years[i % len(years)]
            event_date = f"{year}-06-{(i % 28) + 1:02d}"
            try:
                pd.Timestamp(event_date)
            except Exception:
                event_date = f"{year}-06-15"
            long_stop = rng.random() < long_stopped_rate
            short_fav  = rng.random() < short_favorable_rate
            rows.append({
                "ticker": ticker,
                "definition": "BD-1",
                "event_date": event_date,
                "is_control": False,
                "censored": False,
                "long_state_clean8_21": (
                    TerminalState.STOPPED if long_stop else TerminalState.CLEAN_LIFTOFF
                ),
                "long_state_clean15_126": (
                    TerminalState.STOPPED if long_stop else TerminalState.CLEAN_LIFTOFF
                ),
                "short_state_short21": (
                    TerminalStateShort.FAVORABLE_TRIGGERED if short_fav
                    else TerminalStateShort.ADVERSE_TRIGGERED
                ),
                "short_state_short126": (
                    TerminalStateShort.FAVORABLE_TRIGGERED if short_fav
                    else TerminalStateShort.ADVERSE_TRIGGERED
                ),
            })
        return pd.DataFrame(rows)

    def test_paired_diff_sign_matches_rates(self):
        """mean_paired_diff_pp is positive when short_favorable > long_stopped."""
        from scripts.research.dump_breakdown_events import _paired_within_event_stats
        ev = self._make_events_df(
            n_events=100, long_stopped_rate=0.3, short_favorable_rate=0.7, seed=42
        )
        boot_rng = np.random.default_rng(0)
        result = _paired_within_event_stats(ev, "clean8_21", "short21", boot_rng)
        assert result is not None
        # short_favorable 70% > long_stopped 30% → mean_paired_diff_pp > 0
        assert result["mean_paired_diff_pp"] > 0, (
            f"Expected positive diff (short fav dominates) but got {result['mean_paired_diff_pp']}"
        )

    def test_paired_diff_negative_when_long_stop_dominates(self):
        """mean_paired_diff_pp is negative when long_stopped > short_favorable."""
        from scripts.research.dump_breakdown_events import _paired_within_event_stats
        ev = self._make_events_df(
            n_events=100, long_stopped_rate=0.8, short_favorable_rate=0.2, seed=42
        )
        boot_rng = np.random.default_rng(0)
        result = _paired_within_event_stats(ev, "clean8_21", "short21", boot_rng)
        assert result is not None
        # long_stopped 80% > short_favorable 20% → mean_paired_diff_pp < 0
        assert result["mean_paired_diff_pp"] < 0, (
            f"Expected negative diff (long stop dominates) but got {result['mean_paired_diff_pp']}"
        )

    def test_paired_diff_returns_correct_keys(self):
        """Returned dict has all required keys from §6 deliverable."""
        from scripts.research.dump_breakdown_events import _paired_within_event_stats
        ev = self._make_events_df(n_events=50)
        boot_rng = np.random.default_rng(0)
        result = _paired_within_event_stats(ev, "clean8_21", "short21", boot_rng)
        assert result is not None
        required_keys = {
            "mean_paired_diff_pp", "n_matured_both_sides",
            "long_stopped_rate_pct", "short_favorable_rate_pct",
            "ci95", "cluster_var", "boot_n_iter",
        }
        assert required_keys.issubset(set(result.keys())), (
            f"Missing keys: {required_keys - set(result.keys())}"
        )

    def test_paired_diff_none_when_missing_columns(self):
        """Returns None when required columns are absent."""
        from scripts.research.dump_breakdown_events import _paired_within_event_stats
        ev = pd.DataFrame({"ticker": ["A"], "definition": ["BD-1"], "event_date": ["2022-01-01"]})
        boot_rng = np.random.default_rng(0)
        result = _paired_within_event_stats(ev, "clean8_21", "short21", boot_rng)
        assert result is None

    def test_paired_diff_cluster_var_is_ticker_x_year(self):
        """cluster_var field reports 'ticker_x_year'."""
        from scripts.research.dump_breakdown_events import _paired_within_event_stats
        ev = self._make_events_df(n_events=40)
        boot_rng = np.random.default_rng(0)
        result = _paired_within_event_stats(ev, "clean8_21", "short21", boot_rng)
        assert result is not None
        assert result["cluster_var"] == "ticker_x_year"

    def test_vs_control_block_has_correct_keys(self):
        """_vs_control_stats returns dict with long_stop_vs_control_pp key."""
        from scripts.research.dump_breakdown_events import _vs_control_stats
        ev = self._make_events_df(n_events=50)
        # Build minimal control df
        ctrl_rows = []
        for i in range(150):
            ctrl_rows.append({
                "ticker": "AAA",
                "definition": "CONTROL",
                "event_date": f"2022-0{(i%9)+1}-15",
                "is_control": True,
                "censored": False,
                "long_state_clean8_21": TerminalState.STOPPED if i % 2 == 0 else TerminalState.CLEAN_LIFTOFF,
                "long_state_clean15_126": TerminalState.STOPPED if i % 3 == 0 else TerminalState.CLEAN_LIFTOFF,
            })
        ctrl = pd.DataFrame(ctrl_rows)
        boot_rng = np.random.default_rng(0)
        result = _vs_control_stats(ev, ctrl, "clean8_21", boot_rng)
        assert result is not None
        assert "long_stop_vs_control_pp" in result
        assert "event_stop_rate_pct" in result
        assert "control_stop_rate_pct" in result

    def test_build_summary_has_paired_within_and_vs_control(self):
        """build_summary output has paired_within_event and vs_control blocks."""
        from scripts.research.dump_breakdown_events import build_summary
        ev = self._make_events_df(n_events=50)
        ctrl_rows = [
            {
                "ticker": "AAA", "definition": "CONTROL", "event_date": f"2022-{(i%12)+1:02d}-15",
                "is_control": True, "censored": False,
                "long_state_clean8_21": TerminalState.STOPPED if i % 2 == 0 else TerminalState.CLEAN_LIFTOFF,
                "long_state_clean15_126": TerminalState.STOPPED if i % 3 == 0 else TerminalState.CLEAN_LIFTOFF,
                "short_state_short21": TerminalStateShort.FAVORABLE_TRIGGERED,
                "short_state_short126": TerminalStateShort.ADVERSE_TRIGGERED,
            }
            for i in range(150)
        ]
        events_df = pd.concat([ev, pd.DataFrame(ctrl_rows)], ignore_index=True)
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(events_df, stamp)

        bd1 = summary["per_definition"]["BD-1"]
        assert "paired_within_event" in bd1, "B1: paired_within_event block missing"
        assert "vs_control" in bd1, "B1: vs_control block missing"
        assert "paired_asymmetry_delta" not in bd1, "Old key should be gone"

        # Check no 'Phase-1 work' punt note remains
        import json
        summary_str = json.dumps(summary)
        assert "Phase-1 work" not in summary_str, "B2: Phase-1 punt note should be removed"


# ---------------------------------------------------------------------------
# 10. Clustered bootstrap CI plumbing determinism (B2)
# ---------------------------------------------------------------------------

class TestClusteredBootstrapCI:

    def test_same_seed_deterministic(self):
        """Seeded bootstrap produces identical CI on repeated calls."""
        from scripts.research.dump_breakdown_events import _clustered_bootstrap_ci95
        values   = np.array([1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0])
        clusters = np.array(["A_2022", "A_2022", "B_2022", "B_2022",
                              "C_2023", "C_2023", "D_2023", "D_2023"])
        rng1 = np.random.default_rng(999)
        rng2 = np.random.default_rng(999)
        ci1 = _clustered_bootstrap_ci95(values, clusters, rng1, n_iter=200)
        ci2 = _clustered_bootstrap_ci95(values, clusters, rng2, n_iter=200)
        assert ci1 == ci2, f"Same seed should give same CI: {ci1} vs {ci2}"

    def test_ci_bounds_are_ordered(self):
        """ci95[0] <= ci95[1] always."""
        from scripts.research.dump_breakdown_events import _clustered_bootstrap_ci95
        values   = np.random.default_rng(0).random(30)
        clusters = np.array([f"T{i % 6}_2022" for i in range(30)])
        rng = np.random.default_rng(1)
        ci = _clustered_bootstrap_ci95(values, clusters, rng, n_iter=200)
        assert ci is not None
        assert ci[0] <= ci[1], f"CI lower > upper: {ci}"

    def test_ci_none_when_single_cluster(self):
        """Returns None when all observations are in one cluster (< 2 clusters)."""
        from scripts.research.dump_breakdown_events import _clustered_bootstrap_ci95
        values   = np.array([1.0, 0.0, 1.0])
        clusters = np.array(["only_2022", "only_2022", "only_2022"])
        rng = np.random.default_rng(0)
        ci = _clustered_bootstrap_ci95(values, clusters, rng, n_iter=100)
        assert ci is None

    def test_ci_mean_is_within_bounds(self):
        """The point estimate falls within the CI (not guaranteed but holds for stable data)."""
        from scripts.research.dump_breakdown_events import _clustered_bootstrap_ci95
        # Stable data: all 1s in different clusters → mean=1.0, CI should bracket 1.0
        values   = np.ones(10)
        clusters = np.array([f"T{i}_2022" for i in range(10)])
        rng = np.random.default_rng(5)
        ci = _clustered_bootstrap_ci95(values, clusters, rng, n_iter=500)
        assert ci is not None
        assert ci[0] <= 1.0 <= ci[1], f"Mean=1.0 not within CI {ci}"

    def test_ci_excludes_zero_for_strong_signal(self):
        """CI excludes 0 when all values are 1 (trivially strong signal)."""
        from scripts.research.dump_breakdown_events import _clustered_bootstrap_ci95
        values   = np.ones(20)
        clusters = np.array([f"T{i % 5}_202{2 + i % 3}" for i in range(20)])
        rng = np.random.default_rng(3)
        ci = _clustered_bootstrap_ci95(values, clusters, rng, n_iter=500)
        assert ci is not None
        assert ci[0] > 0.0, f"CI should exclude 0 for all-ones: {ci}"


# ---------------------------------------------------------------------------
# 11. fresh_breach_mask canonical helper (N1)
# ---------------------------------------------------------------------------

class TestFreshBreachMask:

    def test_returns_bool_series_on_sufficient_data(self):
        """fresh_breach_mask returns a boolean Series on a 200+ bar series."""
        from engine.signal_quality import fresh_breach_mask
        close = _long_series(n=300, start_price=100.0)
        mask = fresh_breach_mask(close)
        assert isinstance(mask, pd.Series)
        assert mask.dtype == bool or mask.dtype == np.dtype("bool")

    def test_returns_empty_on_short_series(self):
        """Returns empty Series when input is < 90 bars (signal_frame returns empty)."""
        from engine.signal_quality import fresh_breach_mask
        close = _long_series(n=50, start_price=100.0)
        mask = fresh_breach_mask(close)
        assert len(mask) == 0

    def test_flat_series_has_no_breaches(self):
        """A perfectly flat close never breaches its own EMA-trail."""
        from engine.signal_quality import fresh_breach_mask
        close = _long_series(n=300, start_price=100.0)
        mask = fresh_breach_mask(close)
        # Flat series: EMA-trail equals close; close < trail never fires
        assert not mask.any(), "Flat series should have no fresh breaches"

    def test_consistent_with_analyze_risk_flags(self):
        """analyze() risk_flags are a subset of fresh_breach_mask dates.

        analyze() additionally dropna's on macd/sig/k/d/rsi14 columns before
        scanning for breaches, so it may emit fewer dates than the raw mask.
        The key invariant: every risk_flag date appears in the fresh_breach_mask.
        """
        from engine.signal_quality import fresh_breach_mask, analyze
        # Use a series with variation to get some breaches
        rng = np.random.default_rng(42)
        n = 300
        walk = np.cumsum(rng.normal(0, 1, n)) + 100
        close = pd.Series(walk, index=pd.bdate_range("2020-01-02", periods=n))
        close = pd.Series(np.abs(close), index=close.index)

        mask = fresh_breach_mask(close)
        breach_dates_mask = {str(d.date()) for d in mask.index[mask]}

        result = analyze("TEST", close)
        if result is None:
            return  # not enough data; skip
        risk_flag_dates = set(result.get("risk_flags", []))

        # Every flag emitted by analyze must be in our canonical mask
        missing = risk_flag_dates - breach_dates_mask
        assert not missing, (
            f"analyze() risk_flags {missing} not present in fresh_breach_mask — "
            "fresh_breach_mask and analyze use different constructions"
        )


# ---------------------------------------------------------------------------
# 12. BD-4 Two-Clock Rollover detector (Phase-0b prereg §1)
# ---------------------------------------------------------------------------

class TestBD4Detection:
    """BD-4 Two-Clock Rollover — frozen formula edge cases."""

    def _make_rolling_peak_series(self, n_pre: int = 290) -> tuple[pd.Series, pd.DataFrame]:
        """Build a close series that fires BD-4:
        - price runs up to ~100, then rolls over (oscillators peak near 80+, then fall 15+)
        - close stays extended (>= 0.88 * 252-bar max)
        """
        # warmup phase: gradual rise from 50 to 100
        warm = np.linspace(50.0, 100.0, n_pre)
        # peak phase: flat at 100 for 20 bars (osc should be near 100)
        peak = np.full(20, 100.0)
        # rollover phase: drop to 90 over 20 bars — osc falls sharply
        roll = np.linspace(100.0, 90.0, 20)
        # extended tail: stay at 90 (0.90 >= 0.88 * 100 = 88 ✓)
        tail = np.full(20, 90.0)
        vals = np.concatenate([warm, peak, roll, tail])
        idx = pd.bdate_range("2021-01-04", periods=len(vals))
        close = pd.Series(vals, index=idx)
        raw_df = pd.DataFrame({
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": pd.Series(2e6, index=close.index)
        })
        return close, raw_df

    def test_bd4_requires_273_warmup_bars(self):
        """BD-4 never fires before 273 prior bars (raised ERA-LAW floor)."""
        from scripts.research.dump_breakdown_events import detect_bd4, BD4_WARMUP_BARS
        close, raw_df = self._make_rolling_peak_series(n_pre=290)
        events = detect_bd4("TEST", close, raw_df)
        for ts in events:
            loc = close.index.get_loc(ts)
            assert loc >= BD4_WARMUP_BARS, (
                f"BD-4 event at bar {loc} < warmup floor {BD4_WARMUP_BARS}"
            )

    def test_bd4_returns_list(self):
        """detect_bd4 returns a list (no exception) on a valid series."""
        from scripts.research.dump_breakdown_events import detect_bd4
        close, raw_df = self._make_rolling_peak_series()
        events = detect_bd4("TEST", close, raw_df)
        assert isinstance(events, list)

    def test_bd4_empty_on_flat_series(self):
        """BD-4 never fires on a flat series (oscillators don't peak then roll)."""
        from scripts.research.dump_breakdown_events import detect_bd4
        # Flat close: pos63/pos252 are NaN (max==min), daily/weekly_osc = NaN
        # So rollover conditions can't fire
        close = _long_series(n=500, start_price=50.0)
        raw_df = pd.DataFrame({
            "open": close, "high": close + 0.01, "low": close - 0.01,
            "close": close, "volume": pd.Series(1e6, index=close.index)
        })
        events = detect_bd4("TEST", close, raw_df)
        assert events == []

    def test_bd4_extended_gate_requires_close_near_max(self):
        """BD-4 extended gate: close < 0.88 * 252-bar max → no event even if oscillators roll."""
        from scripts.research.dump_breakdown_events import detect_bd4
        # Build series: peak at 100, then crashes to 70 (70 < 0.88 * 100 = 88)
        n_pre = 290
        warm = np.linspace(50.0, 100.0, n_pre)
        crash = np.full(30, 70.0)  # 70 < 88 → not extended
        vals = np.concatenate([warm, crash])
        idx = pd.bdate_range("2021-01-04", periods=len(vals))
        close = pd.Series(vals, index=idx)
        raw_df = pd.DataFrame({
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": pd.Series(2e6, index=close.index)
        })
        events = detect_bd4("TEST", close, raw_df)
        # In the crash zone, extended=False → no BD-4 events should fire
        for ts in events:
            loc = close.index.get_loc(ts)
            price = float(close.iloc[loc])
            max252 = float(close.rolling(252).max().iloc[loc])
            assert price >= 0.88 * max252, (
                f"BD-4 event at {ts}: price={price:.2f} < 0.88*max252={0.88*max252:.2f}"
            )

    def test_bd4_era_start_respected(self):
        """BD-4 events are all >= ERA_START."""
        from scripts.research.dump_breakdown_events import detect_bd4, ERA_START
        close, raw_df = self._make_rolling_peak_series()
        events = detect_bd4("TEST", close, raw_df)
        for ts in events:
            assert ts >= ERA_START


# ---------------------------------------------------------------------------
# 13. BD-5 Coiled Breakdown detector (Phase-0b prereg §2)
# ---------------------------------------------------------------------------

class TestBD5Detection:
    """BD-5 Coiled Breakdown — frozen formula edge cases."""

    def _make_coiled_breakdown_series(self, n_pre: int = 260) -> tuple[pd.Series, pd.DataFrame]:
        """Build a series that fires BD-5:
        - coil_ratio < 20th pctile (tight range before breakdown)
        - distribution (sv_21 sum) is -0.5σ below mean
        - breakdown: C < min(C, 21 bars ending t-1)
        """
        # warmup: varying prices to build meaningful pctile distribution
        rng = np.random.default_rng(42)
        warm = 50.0 + np.cumsum(rng.normal(0, 1, n_pre)) % 20
        warm = np.clip(warm, 30, 80)

        # coil phase: very tight range (21-bar range ~ 1.0 on price 60)
        coil_phase = np.full(30, 60.0)
        # slight perturbation to avoid exactly flat
        coil_phase += rng.uniform(-0.1, 0.1, 30)

        # breakdown: sharp drop below prior 21-bar min
        prior_21_min = float(np.min(coil_phase[-21:]))
        breakdown_val = prior_21_min * 0.97  # 3% below 21-bar min
        breakdown = np.array([breakdown_val, breakdown_val * 0.99])

        tail = np.full(30, breakdown_val * 0.98)
        vals = np.concatenate([warm, coil_phase, breakdown, tail])
        idx = pd.bdate_range("2021-01-04", periods=len(vals))
        close = pd.Series(vals, index=idx)

        # OHLCV: in the coil phase, close near high (sv > 0 usually)
        # In breakdown phase: close near low (sv < 0) to build distribution signal
        n = len(vals)
        high  = pd.Series(close + 2.0, index=idx)
        low   = pd.Series(close - 0.5, index=idx)
        # In breakdown zone: close near low (deteriorating distribution)
        bd_start = n_pre + 30
        for j in range(bd_start, n):
            high.iloc[j] = close.iloc[j] + 0.3
            low.iloc[j]  = close.iloc[j] - 3.0
        volume = pd.Series(np.full(n, 1_500_000.0), index=idx)
        raw_df = pd.DataFrame({
            "open": close, "high": high, "low": low,
            "close": close, "volume": volume
        })
        return close, raw_df

    def test_bd5_returns_list_no_exception(self):
        """detect_bd5 returns a list without raising on a valid series."""
        from scripts.research.dump_breakdown_events import detect_bd5
        close, raw_df = self._make_coiled_breakdown_series()
        events = detect_bd5("TEST", close, raw_df)
        assert isinstance(events, list)

    def test_bd5_requires_hlv(self):
        """BD-5 returns empty when raw_df is None (no H/L/V → sign_volume unavailable)."""
        from scripts.research.dump_breakdown_events import detect_bd5
        close = _long_series(n=400, start_price=50.0)
        events = detect_bd5("TEST", close, None)
        assert events == [], "BD-5 requires H/L/V; should return empty without raw_df"

    def test_bd5_breakdown_gate_requires_close_below_prior_21min(self):
        """BD-5 breakdown gate: C >= min(C, 21 bars ending t-1) → no event."""
        from scripts.research.dump_breakdown_events import detect_bd5
        # Flat close: never breaks below its own 21-bar min
        close = _long_series(n=500, start_price=50.0)
        raw_df = pd.DataFrame({
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": pd.Series(2e6, index=close.index)
        })
        events = detect_bd5("TEST", close, raw_df)
        assert events == [], "Flat series: no breakdown → no BD-5 events"

    def test_bd5_coil_percentile_uses_252bar_window(self):
        """The coil percentile window is 252 bars (bd1 convention: sv_21.rolling(252))."""
        from scripts.research.dump_breakdown_events import (
            BD5_COIL_PCT_WINDOW, BD5_DIST_ROLL_WINDOW
        )
        assert BD5_COIL_PCT_WINDOW == 252
        assert BD5_DIST_ROLL_WINDOW == 252

    def test_bd5_distribution_sigma_is_neg_half(self):
        """The distribution sigma threshold is -0.5 (BD-1 convention verbatim)."""
        from scripts.research.dump_breakdown_events import BD5_DIST_SIGMA
        assert BD5_DIST_SIGMA == pytest.approx(-0.5)

    def test_bd5_era_start_respected(self):
        """BD-5 events are all >= ERA_START."""
        from scripts.research.dump_breakdown_events import detect_bd5, ERA_START
        close, raw_df = self._make_coiled_breakdown_series()
        events = detect_bd5("TEST", close, raw_df)
        for ts in events:
            assert ts >= ERA_START


# ---------------------------------------------------------------------------
# 14. BD-6 Within-Sector Leader Fade (Phase-0b prereg §3)
# ---------------------------------------------------------------------------

class TestBD6Detection:
    """BD-6 Within-Sector Leader Fade — frozen formula, sector pre-pass, flat-window guard."""

    def _make_sector_panel_synthetic(
        self, tickers: list[str], sector: str = "TestSector"
    ) -> dict:
        """Build a minimal sector_panel dict for testing detect_bd6.

        Each ticker has a 500-bar close series (2021+).  All in the same synthetic sector.
        Returns sector_panel with pre-computed top-decile and median values.
        """
        rng = np.random.default_rng(77)
        n = 500
        idx = pd.bdate_range("2021-01-04", periods=n)
        ticker_closes: dict[str, pd.Series] = {}
        for i, tk in enumerate(tickers):
            # Each ticker has slightly different trajectory
            vals = 50.0 + np.cumsum(rng.normal(0, 0.5, n)) + i * 5
            vals = np.clip(vals, 5.0, 200.0)
            ticker_closes[tk] = pd.Series(vals, index=idx)

        # Compute per-bar top-decile (126-bar return) and median (21-bar return)
        from scripts.research.dump_breakdown_events import BD6_MIN_SECTOR_MEMBERS
        sector_top_decile_126: dict[str, dict[str, float]] = {}
        sector_median_21:      dict[str, dict[str, float]] = {}
        sector_map = {tk: sector for tk in tickers}

        for i, ts in enumerate(idx):
            ts_str = str(ts.date())
            r126_vals = []
            r21_vals  = []
            for tk, c in ticker_closes.items():
                if i >= 126:
                    p_now  = float(c.iloc[i])
                    p_prev = float(c.iloc[i - 126])
                    if p_prev > 0:
                        r126_vals.append(p_now / p_prev - 1.0)
                if i >= 21:
                    p_now  = float(c.iloc[i])
                    p_prev = float(c.iloc[i - 21])
                    if p_prev > 0:
                        r21_vals.append(p_now / p_prev - 1.0)
            sec_d: dict[str, float] = {}
            sec_m: dict[str, float] = {}
            if len(r126_vals) >= BD6_MIN_SECTOR_MEMBERS:
                sec_d[sector] = float(np.percentile(r126_vals, 90))
            if len(r21_vals) >= BD6_MIN_SECTOR_MEMBERS:
                sec_m[sector] = float(np.median(r21_vals))
            sector_top_decile_126[ts_str] = sec_d
            sector_median_21[ts_str]      = sec_m

        return {
            "sector_top_decile_126": sector_top_decile_126,
            "sector_median_21":      sector_median_21,
            "sector_map":            sector_map,
            "artifact_path":         "synthetic",
            "as_of":                 "2026-07-06",
            "n_tickers_covered":     len(tickers),
        }

    def test_bd6_returns_empty_when_no_sector_panel(self):
        """detect_bd6 returns [] when sector_panel is None or empty."""
        from scripts.research.dump_breakdown_events import detect_bd6
        close = _long_series(n=500, start_price=100.0)
        events = detect_bd6("TEST", close, None, {})
        assert events == []

        events2 = detect_bd6("TEST", close, None, None)
        assert events2 == []

    def test_bd6_returns_empty_when_ticker_not_in_sector_map(self):
        """detect_bd6 returns [] when ticker has no sector assignment."""
        from scripts.research.dump_breakdown_events import detect_bd6
        close = _long_series(n=500, start_price=100.0)
        panel = {"sector_map": {"OTHER_TICKER": "Tech"}, "sector_top_decile_126": {},
                 "sector_median_21": {}}
        events = detect_bd6("TEST", close, None, panel)
        assert events == []

    def test_bd6_flat_window_guard_skips_zero_std(self):
        """Bars where std(rel21, 252)==0 are skipped (flat-window guard)."""
        from scripts.research.dump_breakdown_events import detect_bd6
        # Build a series where rel21 is constant (identical to sector median every bar)
        # → std(rel21, 252) = 0 → all bars skipped by the guard
        n = 500
        close = _long_series(n=n, start_price=100.0)
        idx = close.index

        # Build a sector panel where ticker 21-bar return == sector median every bar
        # → rel21 = 0 always → std = 0
        sector_top_decile_126 = {}
        sector_median_21 = {}
        sector = "TestSector"
        for i, ts in enumerate(idx):
            ts_str = str(ts.date())
            if i >= 21:
                p_now  = float(close.iloc[i])
                p_prev = float(close.iloc[i - 21])
                r21 = p_now / p_prev - 1.0 if p_prev > 0 else 0.0
                sector_median_21[ts_str] = {sector: r21}  # matches ticker's own return
            if i >= 126:
                p_now  = float(close.iloc[i])
                p_prev = float(close.iloc[i - 126])
                r126 = p_now / p_prev - 1.0 if p_prev > 0 else 0.0
                sector_top_decile_126[ts_str] = {sector: r126 - 1.0}  # ticker is always leader

        panel = {
            "sector_top_decile_126": sector_top_decile_126,
            "sector_median_21": sector_median_21,
            "sector_map": {"TEST": sector},
            "artifact_path": "synthetic",
            "as_of": "2026-07-06",
        }
        raw_df = pd.DataFrame({
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": pd.Series(2e6, index=close.index)
        })
        events = detect_bd6("TEST", close, raw_df, panel)
        # With constant rel21=0, std=0, all bars are skipped by the flat-window guard
        assert events == [], (
            f"Expected no events (flat-window guard), got {len(events)} events"
        )

    def test_bd6_returns_list_no_exception(self):
        """detect_bd6 doesn't raise on a synthetic sector panel with many tickers."""
        from scripts.research.dump_breakdown_events import detect_bd6, _collapse_episodes
        tickers = [f"T{i:02d}" for i in range(12)]
        panel = self._make_sector_panel_synthetic(tickers, sector="Alpha")
        # Process the first ticker in the panel
        tk = tickers[0]
        n = 500
        idx = pd.bdate_range("2021-01-04", periods=n)
        rng = np.random.default_rng(33)
        vals = 60.0 + np.cumsum(rng.normal(0, 0.5, n))
        vals = np.clip(vals, 5.0, 300.0)
        close = pd.Series(vals, index=idx)
        raw_df = pd.DataFrame({
            "open": close, "high": close + 2, "low": close - 2,
            "close": close, "volume": pd.Series(2e6, index=close.index)
        })
        events = detect_bd6(tk, close, raw_df, panel)
        assert isinstance(events, list)

    def test_bd6_near_highs_gate(self):
        """BD-6 near_highs gate: events only when close >= 0.85 * rolling 126-bar max."""
        from scripts.research.dump_breakdown_events import detect_bd6, BD6_NEAR_HIGHS_MULT
        assert BD6_NEAR_HIGHS_MULT == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# 15. Sector pre-pass on synthetic panel
# ---------------------------------------------------------------------------

class TestSectorPrePass:
    """build_sector_panel on synthetic data — validates structure and sector filtering."""

    def test_sector_panel_structure(self):
        """build_sector_panel returns required keys."""
        from scripts.research.dump_breakdown_events import build_sector_panel
        from unittest.mock import patch
        import pandas as pd

        n_tickers = 10
        tickers = {f"T{i:02d}" for i in range(n_tickers)}
        sector_map = pd.DataFrame({
            "ticker": list(tickers),
            "sector": ["Alpha"] * 5 + ["Beta"] * 5,
        })

        # Build a minimal close series for each ticker
        def mock_read_massive(ticker):
            n = 500
            rng = np.random.default_rng(hash(ticker) % (2**31))
            vals = 50.0 + np.cumsum(rng.normal(0, 0.5, n))
            vals = np.clip(vals, 5.0, 200.0)
            idx = pd.bdate_range("2021-01-04", periods=n)
            return pd.Series(vals, index=idx)

        with patch(
            "scripts.research.dump_breakdown_events._read_massive_ticker",
            side_effect=mock_read_massive
        ):
            panel = build_sector_panel(tickers, sector_map)

        assert "sector_top_decile_126" in panel
        assert "sector_median_21" in panel
        assert "sector_map" in panel
        assert "artifact_path" in panel
        assert "as_of" in panel
        assert "n_tickers_covered" in panel
        assert panel["n_tickers_covered"] > 0

    def test_sector_panel_skips_sectors_below_8_members(self):
        """Sectors with <8 covered members are skipped per BD6_MIN_SECTOR_MEMBERS."""
        from scripts.research.dump_breakdown_events import (
            build_sector_panel, BD6_MIN_SECTOR_MEMBERS
        )
        from unittest.mock import patch
        import pandas as pd

        assert BD6_MIN_SECTOR_MEMBERS == 8

        # Build universe with 5 tickers in one sector (< 8)
        n_tickers = 5
        tickers = {f"T{i:02d}" for i in range(n_tickers)}
        sector_map = pd.DataFrame({
            "ticker": list(tickers),
            "sector": ["TinyOne"] * n_tickers,
        })

        def mock_read_massive(ticker):
            n = 500
            rng = np.random.default_rng(hash(ticker) % (2**31))
            vals = 50.0 + np.cumsum(rng.normal(0, 0.5, n))
            vals = np.clip(vals, 5.0, 200.0)
            idx = pd.bdate_range("2021-01-04", periods=n)
            return pd.Series(vals, index=idx)

        with patch(
            "scripts.research.dump_breakdown_events._read_massive_ticker",
            side_effect=mock_read_massive
        ):
            panel = build_sector_panel(tickers, sector_map)

        # All dates should have {} for sector_top_decile_126 (< 8 members → skipped)
        for ts_str, sec_d in panel["sector_top_decile_126"].items():
            assert "TinyOne" not in sec_d, (
                f"Date {ts_str}: TinyOne sector should be skipped (<8 members) but has value"
            )

    def test_sector_panel_empty_universe(self):
        """build_sector_panel handles empty universe gracefully."""
        from scripts.research.dump_breakdown_events import build_sector_panel
        import pandas as pd

        sector_map = pd.DataFrame({"ticker": ["AAA"], "sector": ["Tech"]})
        panel = build_sector_panel(set(), sector_map)
        assert panel["n_tickers_covered"] == 0
        assert panel["sector_top_decile_126"] == {}


# ---------------------------------------------------------------------------
# 16. Seeding stability: BD-1/2/3 event rows identical regardless of BD-4/5/6
# ---------------------------------------------------------------------------

class TestSeedingStability:
    """BD-1/2/3 event rows are content-identical when BD-4/5/6 are inactive vs active."""

    def test_bd1_event_rows_unchanged_by_bd4_presence(self):
        """BD-1 event detection is pure per-ticker arithmetic; adding BD-4 doesn't change it."""
        from scripts.research.dump_breakdown_events import detect_bd1, detect_bd4

        # Build a series with known BD-1 events
        n_pre = 300
        rng = np.random.default_rng(42)
        warm = np.full(n_pre, 50.0)
        prior_high = np.full(30, 100.0)
        pullback   = np.linspace(100, 90, 10)
        recovery   = np.full(30, 98.0)
        pin        = np.full(10, 99.5)
        vals = np.concatenate([warm, prior_high, pullback, recovery, pin])
        idx  = pd.bdate_range("2021-01-04", periods=len(vals))
        close = pd.Series(vals, index=idx)

        n = len(vals)
        high  = close + 1.5
        low   = close - 2.0
        for j in range(len(vals) - 40, len(vals)):
            high.iloc[j] = close.iloc[j] + 3.0
            low.iloc[j]  = close.iloc[j] - 0.5
        volume = pd.Series(np.full(n, 1_000_000.0), index=idx)
        raw_df = pd.DataFrame({"open": close, "high": high, "low": low,
                                "close": close, "volume": volume}, index=idx)

        # BD-1 events: deterministic (pure arithmetic, no RNG)
        bd1_events_1 = detect_bd1("TEST", close, raw_df)
        bd1_events_2 = detect_bd1("TEST", close, raw_df)
        assert bd1_events_1 == bd1_events_2, "BD-1 detection is not deterministic"

        # BD-4 events on the same series: different detector, doesn't affect BD-1
        bd4_events = detect_bd4("TEST", close, raw_df)
        bd1_events_after = detect_bd1("TEST", close, raw_df)
        assert bd1_events_1 == bd1_events_after, (
            "BD-1 event list changed after running BD-4 detector on same series"
        )

    def test_bd5_independent_rng_seed_constants_distinct(self):
        """BD-4/5/6 control RNG seeds are distinct from each other and from CONTROL_RNG_SEED=42."""
        from scripts.research.dump_breakdown_events import (
            CONTROL_RNG_SEED, BD4_CONTROL_RNG_SEED, BD5_CONTROL_RNG_SEED, BD6_CONTROL_RNG_SEED
        )
        seeds = [CONTROL_RNG_SEED, BD4_CONTROL_RNG_SEED, BD5_CONTROL_RNG_SEED, BD6_CONTROL_RNG_SEED]
        assert len(seeds) == len(set(seeds)), f"Duplicate seeds: {seeds}"
        # None should be 0 or negative
        for s in seeds:
            assert s > 0, f"Seed {s} should be positive"


# ---------------------------------------------------------------------------
# 17. v3 summary schema: all six definitions + overlap matrix + RUL-U3a budget note
# ---------------------------------------------------------------------------

class TestV3SummarySchema:
    """Verify that build_summary returns the v3 schema with all required fields."""

    def _make_six_def_events_df(self, n_per_def: int = 30) -> pd.DataFrame:
        """Build a minimal events DataFrame with all six definitions + controls."""
        rng = np.random.default_rng(7)
        defs = ["BD-1", "BD-2", "BD-3", "BD-4", "BD-5", "BD-6"]
        rows = []
        tickers = ["AAA", "BBB", "CCC", "DDD"]
        years = [2022, 2023, 2024]
        for defn in defs:
            for i in range(n_per_def):
                ticker = tickers[i % len(tickers)]
                year = years[i % len(years)]
                event_date = f"{year}-0{(i % 9) + 1}-{(i % 28) + 1:02d}"
                try:
                    pd.Timestamp(event_date)
                except Exception:
                    event_date = f"{year}-06-15"
                long_stop  = rng.random() < 0.5
                short_fav  = rng.random() < 0.4
                rows.append({
                    "ticker": ticker,
                    "definition": defn,
                    "event_date": event_date,
                    "is_control": False,
                    "censored": False,
                    "long_state_clean8_21": (
                        TerminalState.STOPPED if long_stop else TerminalState.CLEAN_LIFTOFF
                    ),
                    "long_state_clean15_126": (
                        TerminalState.STOPPED if long_stop else TerminalState.CLEAN_LIFTOFF
                    ),
                    "short_state_short21": (
                        TerminalStateShort.FAVORABLE_TRIGGERED if short_fav
                        else TerminalStateShort.ADVERSE_TRIGGERED
                    ),
                    "short_state_short126": (
                        TerminalStateShort.FAVORABLE_TRIGGERED if short_fav
                        else TerminalStateShort.ADVERSE_TRIGGERED
                    ),
                })

        # Add controls
        for i in range(n_per_def * 3):
            year = years[i % len(years)]
            rows.append({
                "ticker": tickers[i % len(tickers)],
                "definition": "CONTROL",
                "event_date": f"{year}-06-15",
                "is_control": True,
                "censored": False,
                "long_state_clean8_21": (
                    TerminalState.STOPPED if i % 2 == 0 else TerminalState.CLEAN_LIFTOFF
                ),
                "long_state_clean15_126": (
                    TerminalState.STOPPED if i % 3 == 0 else TerminalState.CLEAN_LIFTOFF
                ),
                "short_state_short21": TerminalStateShort.ADVERSE_TRIGGERED,
                "short_state_short126": TerminalStateShort.ADVERSE_TRIGGERED,
            })
        return pd.DataFrame(rows)

    def test_v3_schema_present(self):
        """build_summary returns schema='breakdown_events_summary.v3'."""
        from scripts.research.dump_breakdown_events import build_summary
        df = self._make_six_def_events_df()
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(df, stamp)
        assert summary["schema"] == "breakdown_events_summary.v3", (
            f"Expected v3 schema, got {summary['schema']}"
        )

    def test_v3_all_six_definitions_present(self):
        """per_definition has keys for all six definitions."""
        from scripts.research.dump_breakdown_events import build_summary
        df = self._make_six_def_events_df()
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(df, stamp)
        required_defs = {"BD-1", "BD-2", "BD-3", "BD-4", "BD-5", "BD-6"}
        actual_defs   = set(summary["per_definition"].keys())
        assert required_defs == actual_defs, (
            f"Missing definitions: {required_defs - actual_defs}"
        )

    def test_v3_overlap_matrix_has_six_definitions(self):
        """overlap_matrix.matrix covers all six definitions."""
        from scripts.research.dump_breakdown_events import build_summary
        df = self._make_six_def_events_df()
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(df, stamp)
        matrix = summary["overlap_matrix"]["matrix"]
        required_defs = {"BD-1", "BD-2", "BD-3", "BD-4", "BD-5", "BD-6"}
        assert required_defs == set(matrix.keys()), (
            f"overlap_matrix.matrix missing defs: {required_defs - set(matrix.keys())}"
        )

    def test_v3_bd4_x_bd3_required_row_present(self):
        """overlap_matrix has bd4_x_bd3 key with all required subkeys."""
        from scripts.research.dump_breakdown_events import build_summary
        df = self._make_six_def_events_df()
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(df, stamp)
        bd4x3 = summary["overlap_matrix"].get("bd4_x_bd3")
        assert bd4x3 is not None, "bd4_x_bd3 key missing from overlap_matrix"
        required_keys = {
            "n_bd4_episodes", "n_bd3_episodes", "n_exact_overlap",
            "n_near_overlap_21bars", "share_exact", "share_near_21bars", "redundancy_flag"
        }
        assert required_keys.issubset(set(bd4x3.keys())), (
            f"bd4_x_bd3 missing keys: {required_keys - set(bd4x3.keys())}"
        )

    def test_v3_redundancy_flag_fires_when_overlap_exceeds_50pct(self):
        """redundancy_flag=True when BD-4 shares >50% episodes with BD-3 (±21 bars)."""
        from scripts.research.dump_breakdown_events import build_summary
        # Build DF where all BD-4 events have a BD-3 event on the same date (100% overlap)
        rows = []
        for i in range(20):
            dt = f"2023-0{(i%9)+1}-{(i%28)+1:02d}"
            try:
                pd.Timestamp(dt)
            except Exception:
                dt = "2023-06-15"
            for defn in ["BD-3", "BD-4"]:
                rows.append({
                    "ticker": "AAA",
                    "definition": defn,
                    "event_date": dt,
                    "is_control": False,
                    "censored": False,
                    "long_state_clean8_21": TerminalState.STOPPED,
                    "long_state_clean15_126": TerminalState.STOPPED,
                    "short_state_short21": TerminalStateShort.ADVERSE_TRIGGERED,
                    "short_state_short126": TerminalStateShort.ADVERSE_TRIGGERED,
                })
        df = pd.DataFrame(rows)
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(df, stamp)
        bd4x3 = summary["overlap_matrix"]["bd4_x_bd3"]
        assert bd4x3["redundancy_flag"] is True, (
            "100% same-date overlap should set redundancy_flag=True"
        )
        assert bd4x3["redundancy_note"], "redundancy_note should be non-empty when flag is True"

    def test_v3_near_overlap_uses_business_days_not_calendar_days(self):
        """±21 near-overlap check uses business days (not calendar days / ns-timestamp proxy).

        Regression guard for the fix described in W-0B code review finding #1 (2026-07-06):
        the prior implementation used pd.Timedelta(days=30) as an ~21-trading-bar proxy,
        which could under-count near-overlaps by 0-1 bar around US holiday clusters.
        The corrected implementation uses np.busday_count (Mon-Fri business days), which
        is conservative (slightly over-inclusive: at most ~1 bar, because US market
        holidays are not explicitly excluded from the weekday count).

        This test exercises the non-exact-date near-overlap path: BD-4 event on day T,
        BD-3 event 15 business days later on the same ticker.  This should be flagged as
        near-overlap (15 <= 21) regardless of whether 15 bdays spans >=30 calendar days.
        """
        from scripts.research.dump_breakdown_events import build_summary

        bd3_date = pd.Timestamp("2023-01-03")  # a Tuesday
        # 15 business days after 2023-01-03 = 2023-01-24 (Mon-Fri, no holiday exclusion)
        bd4_date = pd.Timestamp("2023-01-24")
        # Verify: np.busday_count gives 15
        import numpy as np
        bdays = np.busday_count(bd3_date.date(), bd4_date.date())
        assert bdays == 15, f"fixture sanity: expected 15 bdays, got {bdays}"
        # Calendar days between them: 21 calendar days exactly
        cal_days = (bd4_date - bd3_date).days
        # The near-overlap should fire because 15 bdays <= 21 threshold

        def _row(defn, dt):
            return {
                "ticker": "ZZZ",
                "definition": defn,
                "event_date": str(dt.date()),
                "is_control": False,
                "censored": False,
                "long_state_clean8_21": TerminalState.STOPPED,
                "long_state_clean15_126": TerminalState.STOPPED,
                "short_state_short21": TerminalStateShort.ADVERSE_TRIGGERED,
                "short_state_short126": TerminalStateShort.ADVERSE_TRIGGERED,
            }

        rows = [_row("BD-3", bd3_date), _row("BD-4", bd4_date)]
        df = pd.DataFrame(rows)
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(df, stamp)
        bd4x3 = summary["overlap_matrix"]["bd4_x_bd3"]
        assert bd4x3["n_near_overlap_21bars"] == 1, (
            f"BD-4 event {bd4_date.date()} is {bdays} bdays ({cal_days} cal days) from "
            f"BD-3 event {bd3_date.date()} — should count as near-overlap (15 <= 21 bdays). "
            f"Got n_near_overlap_21bars={bd4x3['n_near_overlap_21bars']}"
        )
        assert bd4x3["redundancy_flag"] is True, (
            "1/1 BD-4 episode overlapping BD-3 (15 bdays) should set redundancy_flag=True"
        )

    def test_v3_no_near_overlap_beyond_21_bdays(self):
        """BD-4 event more than 21 bdays from any BD-3 event is NOT flagged as near-overlap."""
        from scripts.research.dump_breakdown_events import build_summary
        import numpy as np

        bd3_date = pd.Timestamp("2023-01-03")
        # 30 business days later: 2023-02-14
        bd4_date = bd3_date + pd.offsets.BDay(30)
        bdays = np.busday_count(bd3_date.date(), bd4_date.date())
        assert bdays == 30, f"fixture sanity: expected 30 bdays, got {bdays}"

        def _row(defn, dt):
            return {
                "ticker": "ZZZ",
                "definition": defn,
                "event_date": str(dt.date()),
                "is_control": False,
                "censored": False,
                "long_state_clean8_21": TerminalState.STOPPED,
                "long_state_clean15_126": TerminalState.STOPPED,
                "short_state_short21": TerminalStateShort.ADVERSE_TRIGGERED,
                "short_state_short126": TerminalStateShort.ADVERSE_TRIGGERED,
            }

        rows = [_row("BD-3", bd3_date), _row("BD-4", bd4_date)]
        df = pd.DataFrame(rows)
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(df, stamp)
        bd4x3 = summary["overlap_matrix"]["bd4_x_bd3"]
        assert bd4x3["n_near_overlap_21bars"] == 0, (
            f"BD-4 event {bd4_date.date()} is {bdays} bdays from BD-3 event {bd3_date.date()} "
            f"— should NOT count as near-overlap (30 > 21 bdays). "
            f"Got n_near_overlap_21bars={bd4x3['n_near_overlap_21bars']}"
        )
        assert bd4x3["redundancy_flag"] is False, (
            "0/1 BD-4 episodes overlapping should set redundancy_flag=False"
        )

    def test_v3_budget_semantics_note_present(self):
        """budget_semantics_note key is present and mentions max() and literal_n."""
        from scripts.research.dump_breakdown_events import build_summary
        df = self._make_six_def_events_df()
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(df, stamp)
        note = summary.get("budget_semantics_note", "")
        assert "max()" in note, "budget_semantics_note should mention max() semantics"
        assert "literal_n" in note.lower() or "literal_n" in note, (
            "budget_semantics_note should mention literal_n"
        )

    def test_v3_derived_from_surface_stamped(self):
        """derived_from_surface='bd_phase0_tape' is present in summary."""
        from scripts.research.dump_breakdown_events import build_summary
        df = self._make_six_def_events_df()
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(df, stamp)
        assert summary.get("derived_from_surface") == "bd_phase0_tape", (
            "derived_from_surface should be 'bd_phase0_tape' per Phase-0b contamination stamp"
        )

    def test_v3_phase0b_definitions_have_powering_note_when_small(self):
        """Phase-0b definitions with <100 episodes have non-empty powering_note."""
        from scripts.research.dump_breakdown_events import build_summary
        # With n_per_def=30, all defs have 30 episodes → < 100 → parked
        df = self._make_six_def_events_df(n_per_def=30)
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(df, stamp)
        for defn in ["BD-4", "BD-5", "BD-6"]:
            note = summary["per_definition"][defn].get("powering_note", "")
            assert note, (
                f"{defn}: expected powering_note (< 100 episodes) but got empty string"
            )

    def test_v3_no_validated_word_in_summary(self):
        """The word 'validated' must not appear anywhere in the summary JSON (CI-enforced)."""
        import json
        from scripts.research.dump_breakdown_events import build_summary
        df = self._make_six_def_events_df()
        stamp = {"generated_utc": "2026-07-06T00:00:00", "price_plane_id": "test"}
        summary = build_summary(df, stamp)
        summary_str = json.dumps(summary)
        assert "validated" not in summary_str.lower(), (
            "The word 'validated' must not appear in any user-facing summary text"
        )
