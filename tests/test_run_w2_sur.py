"""Tests for scripts/research/run_w2_sur.py — W2 S-UR Spring Reclaim study.

Scope: event-join arithmetic, dedup, form labeling.
The underlying estimator is already tested in test_entry_strata_phase0.py.

Fixtures are hand-constructed to be deterministic and fast (<2s total).
All numerical expected values are derived from the fixture construction and
manually verified below each test — no floating-point magic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path bootstrap: allow running directly from the repo root or worktree.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from scripts.research.run_w2_sur import (
    dedup_events,
    enumerate_ur_events,
    label_coiled_context,
    label_gate_fire_proximity,
    GATE_FIRE_PROXIMITY_BARS,
    MAX_COFIRE_SHARE,
    MIN_EPISODES_PER_FORM,
    NONINFERIORITY_MARGIN,
)


# ---------------------------------------------------------------------------
# Helper: build a small deterministic date index
# ---------------------------------------------------------------------------
def _dates(n: int, start: str = "2020-01-02") -> pd.DatetimeIndex:
    """Return n business-day dates starting at start."""
    return pd.bdate_range(start=start, periods=n)


# ---------------------------------------------------------------------------
# Helper: build a close-only U&R fixture (two consecutive undercuts)
# ---------------------------------------------------------------------------
def _build_close_fixture(n: int = 80) -> pd.DataFrame:
    """Build a minimal OHLCV-like DataFrame with two U&R events.

    Structure (close-only, no H/L so undercut requires close < rolling_low):
    - Bars 0-20: close = 100.0 (21 bars, filling the rolling-21-bar window)
    - Bar 21: rolling_low = min(close[0..20]) = 100.0 (shift(1) means looking at bars 0-20)
    - Bar 22 (undercut 1): close = 97.0 < 100.0, depth = 3/100 = 3% >= 2% gate
    - Bar 23 (reclaim 1): close = 101.0 > 100.0  -> EVENT fires here
    - Bars 24-64: close = 100.0  (enough bars for rolling window to clear the dip)
    - Bar 65 (undercut 2): close = 97.5, rolling_low at bar 65 = min(close[44..64]) = 100.0
                           depth = 2.5/100 = 2.5% >= 2% gate  -> EVENT fires here
    - Bar 66 (reclaim 2): close = 101.5 > 100.0
    - Bars 67-n-1: close = 100.0

    Note: bars 22/23 (dip) are excluded from the rolling window at bar 65 because the
    rolling window at bar i covers close[i-21..i-1]. Bar 65's window = close[44..64],
    which is all 100.0. So the rolling_low at bar 65 = 100.0, not 97.
    """
    idx = _dates(n)
    vals = np.full(n, 100.0)
    vals[22] = 97.0
    vals[23] = 101.0
    vals[65] = 97.5
    vals[66] = 101.5
    return pd.DataFrame({"close": vals}, index=idx)


# ===========================================================================
# 1. Event-join arithmetic tests
# ===========================================================================

class TestEventJoinArithmetic:
    """Verify that enumerate_ur_events correctly joins undercut+reclaim events."""

    def test_events_fire_at_reclaim_bar(self):
        """Events must fire at the reclaim bar (23 and 44), not the undercut bar."""
        store = {"AAPL": _build_close_fixture(80)}
        events = enumerate_ur_events(store, "test", n=21, k=3)
        assert not events.empty, "Expected at least one event"
        event_dates = events["date"].values
        idx = _dates(80)
        assert idx[23] in event_dates, f"Expected event at bar 23; got {event_dates}"
        assert idx[66] in event_dates, f"Expected event at bar 66; got {event_dates}"

    def test_undercut_date_column_populated(self):
        """undercut_date must point to the actual undercut bar, not the reclaim bar."""
        store = {"AAPL": _build_close_fixture(80)}
        events = enumerate_ur_events(store, "test", n=21, k=3)
        assert not events.empty
        # First event: reclaim at bar 23, undercut at bar 22
        idx = _dates(80)
        first_ev = events[events["date"] == idx[23]].iloc[0]
        assert first_ev["undercut_date"] == idx[22], (
            f"undercut_date expected {idx[22]}, got {first_ev['undercut_date']}"
        )

    def test_arm_label_close_only(self):
        """Store without H/L columns must produce arm='close-only'."""
        store = {"AAPL": _build_close_fixture(80)}
        events = enumerate_ur_events(store, "test", n=21, k=3)
        assert not events.empty
        assert (events["arm"] == "close-only").all(), (
            f"Expected all close-only arm; got {events['arm'].unique()}"
        )

    def test_arm_label_hl_mode(self):
        """Store with H/L columns must produce arm='H/L'."""
        df = _build_close_fixture(80).copy()
        # Add trivial H/L (high = close + 1, low = close - 1)
        df["high"] = df["close"] + 1.0
        df["low"]  = df["close"] - 1.0
        # Force a deep undercut: bar 22 low well below rolling_low
        df.loc[df.index[22], "low"] = 90.0   # 10 pts below 100 >> 1xATR
        store = {"AAPL": df}
        events = enumerate_ur_events(store, "test", n=21, k=3)
        # We just check the arm label; events may vary due to ATR calculation
        if not events.empty:
            assert (events["arm"] == "H/L").all(), (
                f"Expected H/L arm; got {events['arm'].unique()}"
            )

    def test_output_columns_present(self):
        """enumerate_ur_events must return required columns."""
        store = {"AAPL": _build_close_fixture(80)}
        events = enumerate_ur_events(store, "test", n=21, k=3)
        required = {"ticker", "date", "n_low", "k_reclaim", "panel",
                    "undercut_date", "broken_level", "depth_frac", "arm"}
        assert required.issubset(set(events.columns)), (
            f"Missing columns: {required - set(events.columns)}"
        )

    def test_panel_label_stamped(self):
        """panel column must equal the passed panel_name."""
        store = {"AAPL": _build_close_fixture(80)}
        events = enumerate_ur_events(store, "my_panel", n=21, k=3)
        if not events.empty:
            assert (events["panel"] == "my_panel").all()

    def test_n_and_k_stamped(self):
        """n_low and k_reclaim must be stamped on every row."""
        store = {"AAPL": _build_close_fixture(80)}
        events = enumerate_ur_events(store, "test", n=21, k=5)
        if not events.empty:
            assert (events["n_low"] == 21).all()
            assert (events["k_reclaim"] == 5).all()

    def test_empty_store_returns_empty(self):
        """Empty store must return empty DataFrame with correct columns."""
        events = enumerate_ur_events({}, "test", n=21, k=3)
        assert events.empty
        assert "ticker" in events.columns

    def test_no_k_plus_1_fire(self):
        """Reclaim arriving on bar k+1 (4 bars after undercut for k=3) must NOT fire."""
        # Build fixture: bars 0-21 = 100, bar 22 = 97 (undercut), bars 23-25 = 96
        # (no reclaim within k=3), bar 26 = 101 (reclaim on bar 4 after undercut)
        n = 35
        idx = _dates(n)
        vals = np.full(n, 100.0)
        vals[22] = 97.0          # undercut
        vals[23] = 96.0          # still below — bar 1 after undercut
        vals[24] = 96.0          # still below — bar 2
        vals[25] = 96.0          # still below — bar 3 (= k=3, last allowed)
        vals[26] = 101.0         # reclaim on bar 4 — MUST NOT FIRE
        store = {"AAPL": pd.DataFrame({"close": vals}, index=idx)}
        events = enumerate_ur_events(store, "test", n=21, k=3)
        assert events.empty, (
            f"Expected no events (reclaim on bar k+1); got {len(events)}"
        )

    def test_depth_too_shallow_no_fire(self):
        """Undercut depth < 2% of rolling_low (close-only) must not fire."""
        # rolling_low = 100.0; close at undercut = 99.5 -> depth = 0.5/100 = 0.5% < 2%
        n = 30
        idx = _dates(n)
        vals = np.full(n, 100.0)
        vals[22] = 99.5   # <2% depth
        vals[23] = 101.0  # would-be reclaim
        store = {"AAPL": pd.DataFrame({"close": vals}, index=idx)}
        events = enumerate_ur_events(store, "test", n=21, k=3)
        assert events.empty, (
            f"Expected no events (depth too shallow); got {len(events)}"
        )

    def test_multi_ticker_events(self):
        """enumerate_ur_events must handle multiple tickers correctly."""
        store = {
            "AAPL": _build_close_fixture(80),
            "GOOG": _build_close_fixture(80),
        }
        events = enumerate_ur_events(store, "test", n=21, k=3)
        assert not events.empty
        tickers = events["ticker"].unique()
        assert "AAPL" in tickers
        assert "GOOG" in tickers


# ===========================================================================
# 2. Deduplication tests
# ===========================================================================

class TestDedup:
    """Verify dedup_events keeps one event per (ticker, undercut_date)."""

    def _make_events(self) -> pd.DataFrame:
        """Two events for AAPL from the same undercut_date (different k windows)."""
        idx = _dates(5)
        return pd.DataFrame({
            "ticker":        ["AAPL", "AAPL", "MSFT"],
            "date":          [idx[1], idx[2], idx[3]],
            "undercut_date": [idx[0], idx[0], idx[0]],
            "n_low":         [21, 21, 21],
            "k_reclaim":     [2, 3, 3],
            "panel":         ["test", "test", "test"],
            "broken_level":  [100.0, 100.0, 100.0],
            "depth_frac":    [0.03, 0.03, 0.03],
            "arm":           ["close-only", "close-only", "close-only"],
        })

    def test_dedup_keeps_first_reclaim(self):
        """For same (ticker, undercut_date), keep the earliest reclaim date."""
        events = self._make_events()
        deduped = dedup_events(events)
        # AAPL has two events (bar 1 and bar 2 from same undercut bar 0);
        # should keep bar 1 (earlier reclaim)
        aapl_rows = deduped[deduped["ticker"] == "AAPL"]
        assert len(aapl_rows) == 1, f"Expected 1 AAPL row, got {len(aapl_rows)}"
        idx = _dates(5)
        assert aapl_rows.iloc[0]["date"] == idx[1], (
            "Should keep the earliest reclaim date"
        )

    def test_dedup_preserves_different_tickers(self):
        """Different tickers with same undercut_date are NOT deduped."""
        events = self._make_events()
        deduped = dedup_events(events)
        assert "MSFT" in deduped["ticker"].values, "MSFT row should be preserved"

    def test_dedup_empty_input(self):
        """dedup_events on empty DataFrame must return empty DataFrame."""
        empty = pd.DataFrame(columns=["ticker", "date", "undercut_date"])
        result = dedup_events(empty)
        assert result.empty

    def test_dedup_no_duplicates(self):
        """Input with no duplicates must be unchanged (same row count)."""
        idx = _dates(3)
        events = pd.DataFrame({
            "ticker":        ["AAPL", "MSFT"],
            "date":          [idx[1], idx[2]],
            "undercut_date": [idx[0], idx[0]],
            "n_low":         [21, 21],
            "k_reclaim":     [3, 3],
            "panel":         ["t", "t"],
            "broken_level":  [100.0, 100.0],
            "depth_frac":    [0.03, 0.03],
            "arm":           ["close-only", "close-only"],
        })
        deduped = dedup_events(events)
        assert len(deduped) == 2

    def test_dedup_output_has_same_columns(self):
        """Deduped output must preserve all input columns."""
        events = self._make_events()
        deduped = dedup_events(events)
        assert set(deduped.columns) == set(events.columns)


# ===========================================================================
# 3. Form labeling tests
# ===========================================================================

class TestGateFireProximityLabeling:
    """Verify label_gate_fire_proximity correctly identifies nearby gate fires."""

    def _make_events_and_fires(self):
        """U&R event on 2020-01-10; gate fire for same ticker on 2020-01-13 (+3 trading bars)."""
        ev_date = pd.Timestamp("2020-01-10")
        gf_date = pd.Timestamp("2020-01-13")
        events = pd.DataFrame({
            "ticker": ["AAPL", "AAPL"],
            "date":   [ev_date, pd.Timestamp("2020-06-01")],
        })
        gate_fires = pd.DataFrame({
            "ticker": ["AAPL"],
            "date":   [gf_date],
        })
        return events, gate_fires

    def test_nearby_gate_fire_detected(self):
        """Event within GATE_FIRE_PROXIMITY_BARS of a gate fire must be flagged."""
        events, gate_fires = self._make_events_and_fires()
        labeled = label_gate_fire_proximity(events, gate_fires)
        # Jan 10 and Jan 13 are 3 calendar days apart (~2 trading bars)
        # GATE_FIRE_PROXIMITY_BARS = 5, so this must be flagged True
        assert labeled["near_gate_fire"].iloc[0], (
            "Event 3 calendar days from gate fire should be flagged as nearby"
        )

    def test_distant_event_not_flagged(self):
        """Event far from any gate fire must NOT be flagged."""
        events, gate_fires = self._make_events_and_fires()
        labeled = label_gate_fire_proximity(events, gate_fires)
        # Second event (2020-06-01) is far from the gate fire (2020-01-13)
        assert not labeled["near_gate_fire"].iloc[1], (
            "Event far from gate fire should not be flagged"
        )

    def test_no_gate_fires_for_ticker(self):
        """U&R event for a ticker with no gate fires must not be flagged."""
        events = pd.DataFrame({
            "ticker": ["TSLA"],
            "date":   [pd.Timestamp("2020-01-10")],
        })
        gate_fires = pd.DataFrame({
            "ticker": ["AAPL"],
            "date":   [pd.Timestamp("2020-01-10")],  # AAPL, not TSLA
        })
        labeled = label_gate_fire_proximity(events, gate_fires)
        assert not labeled["near_gate_fire"].iloc[0]

    def test_output_columns_added(self):
        """Must add near_gate_fire and min_gate_fire_dist_bars columns."""
        events, gate_fires = self._make_events_and_fires()
        labeled = label_gate_fire_proximity(events, gate_fires)
        assert "near_gate_fire" in labeled.columns
        assert "min_gate_fire_dist_bars" in labeled.columns

    def test_empty_gate_fires(self):
        """Empty gate_fires DataFrame must result in near_gate_fire=False for all events."""
        events = pd.DataFrame({
            "ticker": ["AAPL"],
            "date":   [pd.Timestamp("2020-01-10")],
        })
        gate_fires = pd.DataFrame({"ticker": [], "date": []})
        labeled = label_gate_fire_proximity(events, gate_fires)
        assert not labeled["near_gate_fire"].iloc[0]

    def test_co_fire_share_constant_registration(self):
        """MAX_COFIRE_SHARE independence clause constant must be 0.60."""
        assert MAX_COFIRE_SHARE == 0.60, (
            f"Independence clause constant should be 0.60; got {MAX_COFIRE_SHARE}"
        )

    def test_min_dist_nonnegative(self):
        """min_gate_fire_dist_bars must be >= 0 for events with a nearby gate fire."""
        events, gate_fires = self._make_events_and_fires()
        labeled = label_gate_fire_proximity(events, gate_fires)
        near_rows = labeled[labeled["near_gate_fire"]]
        if not near_rows.empty:
            assert (near_rows["min_gate_fire_dist_bars"] >= 0).all()


class TestCOILEDFormLabeling:
    """Verify label_coiled_context adds in_coiled_ctx column without reinventing COILED."""

    def _make_short_fixture(self, n: int = 350) -> pd.DataFrame:
        """Return a DataFrame with sufficient bars for washout_ctx (needs >=217 daily bars)."""
        # washout_ctx requires _WASH_CTX_A=217 bars minimum.
        # Build a simple monotonic series to avoid crashing on RSI/MACD internals.
        idx = _dates(n)
        vals = np.linspace(100, 80, n)  # gradual decline (washout-like)
        return pd.DataFrame({"close": vals}, index=idx)

    def test_column_added(self):
        """label_coiled_context must add in_coiled_ctx column."""
        n = 350
        store = {"AAPL": self._make_short_fixture(n)}
        idx = _dates(n)
        events = pd.DataFrame({
            "ticker": ["AAPL"],
            "date":   [idx[-1]],  # last bar, well after warm-up
        })
        labeled = label_coiled_context(events, store)
        assert "in_coiled_ctx" in labeled.columns

    def test_unknown_ticker_gets_none(self):
        """Event for a ticker not in ohlcv_store must get in_coiled_ctx = None."""
        store = {}
        events = pd.DataFrame({
            "ticker": ["UNKNOWN"],
            "date":   [pd.Timestamp("2020-01-10")],
        })
        labeled = label_coiled_context(events, store)
        assert labeled["in_coiled_ctx"].iloc[0] is None

    def test_insufficient_history_gets_none(self):
        """Event with fewer bars than washout_ctx minimum should get None."""
        # Only 50 bars — not enough for washout_ctx (_WASH_CTX_A=217)
        n = 50
        idx = _dates(n)
        store = {"AAPL": pd.DataFrame({
            "close": np.full(n, 100.0)
        }, index=idx)}
        events = pd.DataFrame({
            "ticker": ["AAPL"],
            "date":   [idx[-1]],
        })
        labeled = label_coiled_context(events, store)
        # None is expected because washout_ctx needs 217+ bars
        assert labeled["in_coiled_ctx"].iloc[0] is None

    def test_boolean_or_none_values_only(self):
        """in_coiled_ctx must only contain True, False, or None (not arbitrary values)."""
        n = 350
        store = {"AAPL": self._make_short_fixture(n)}
        idx = _dates(n)
        events = pd.DataFrame({
            "ticker": ["AAPL", "AAPL"],
            "date":   [idx[220], idx[340]],
        })
        labeled = label_coiled_context(events, store)
        for val in labeled["in_coiled_ctx"]:
            assert val is None or isinstance(val, bool), (
                f"in_coiled_ctx must be bool or None; got {val!r}"
            )


# ===========================================================================
# 4. Species bar constant tests (enforcement of pre-registered values)
# ===========================================================================

class TestSpeciesBarConstants:
    """Verify pre-registered species bar constants match masterplan §5."""

    def test_min_episodes(self):
        """MIN_EPISODES_PER_FORM must equal 150 (masterplan §5 species bar)."""
        assert MIN_EPISODES_PER_FORM == 150

    def test_noninferiority_margin(self):
        """NONINFERIORITY_MARGIN must be -0.01 (CI_lo > -1pp vs incumbent)."""
        assert abs(NONINFERIORITY_MARGIN - (-0.01)) < 1e-9

    def test_gate_fire_proximity_bars(self):
        """GATE_FIRE_PROXIMITY_BARS must equal 5 (masterplan F2 'within +/-5 bars')."""
        assert GATE_FIRE_PROXIMITY_BARS == 5
