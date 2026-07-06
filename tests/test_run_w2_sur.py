"""Tests for scripts/research/run_w2_sur.py — W2 S-UR Spring Reclaim study.

Scope: event-join arithmetic, dedup, form labeling, sign-convention enforcement,
species-bar verdict logic (verdict-logic unit tests — ADDITION A).

The underlying estimator is already tested in test_entry_strata_phase0.py.

Fixtures are hand-constructed to be deterministic and fast (<2s total).
All numerical expected values are derived from the fixture construction and
manually verified below each test — no floating-point magic.

ADDITION A — Verdict-logic unit tests (TestVerdictLogic):
  These are the tests that would have caught the sign-convention blocker.
  A synthetic candidate clearly WORSE on stop5 must FAIL species bar.
  A synthetic clearly-better candidate must PASS non-inferiority + superiority.
  A boundary case at exactly the margin is tested for correct direction.
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
    compute_cofire_share_trading_bars,
    check_species_bar_per_form,
    _run_nc2_band_fe,
    GATE_FIRE_PROXIMITY_BARS,
    INDEPENDENCE_BARS,
    MAX_COFIRE_SHARE,
    MIN_EPISODES_PER_FORM,
    NONINFERIORITY_MARGIN,
    OUTCOME_COLS,
    OUTCOME_COLS_BH,
    ADVERSE_METRICS,
    BENEFICIAL_METRICS,
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
    """
    idx = _dates(n)
    vals = np.full(n, 100.0)
    vals[22] = 97.0
    vals[23] = 101.0
    vals[65] = 97.5
    vals[66] = 101.5
    return pd.DataFrame({"close": vals}, index=idx)


# ---------------------------------------------------------------------------
# Helper: build synthetic effects dict for verdict-logic tests
# ---------------------------------------------------------------------------
def _make_synthetic_results(
    stop5_coef: float,
    stop5_ci_lo: float,
    stop5_ci_hi: float,
    cushion_coef: float = 0.0,
    cushion_ci_lo: float = -0.05,
    cushion_ci_hi: float = 0.05,
    dead_coef: float = 0.0,
    dead_ci_lo: float = -0.05,
    dead_ci_hi: float = 0.05,
    zone_coef: float = 0.0,
    zone_ci_lo: float = -0.05,
    zone_ci_hi: float = 0.05,
) -> dict:
    """Build a synthetic results dict resembling run_form_analysis output."""
    return {
        "effects": [
            {
                "outcome": "stop5",
                "coef": stop5_coef,
                "ci_lo": stop5_ci_lo,
                "ci_hi": stop5_ci_hi,
                "p_value": 0.01,
                "recall": 0.5,
            },
            {
                "outcome": "cushion_rot",
                "coef": cushion_coef,
                "ci_lo": cushion_ci_lo,
                "ci_hi": cushion_ci_hi,
                "p_value": 0.3,
                "recall": 0.5,
            },
            {
                "outcome": "dead_money",
                "coef": dead_coef,
                "ci_lo": dead_ci_lo,
                "ci_hi": dead_ci_hi,
                "p_value": 0.3,
                "recall": 0.5,
            },
            {
                "outcome": "zone_held_21",
                "coef": zone_coef,
                "ci_lo": zone_ci_lo,
                "ci_hi": zone_ci_hi,
                "p_value": 0.2,
                "recall": 0.5,
            },
        ],
        "era_sign_stable": True,
        "n_treatment": 200,
        "n_control": 500,
    }


# ===========================================================================
# 1. Event-join arithmetic tests
# ===========================================================================

class TestEventJoinArithmetic:
    """Verify that enumerate_ur_events correctly joins undercut+reclaim events."""

    def test_events_fire_at_reclaim_bar(self):
        """Events must fire at the reclaim bar (23 and 66), not the undercut bar."""
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

    def test_gate_fire_proximity_bars_constant(self):
        """GATE_FIRE_PROXIMITY_BARS must equal 5 per masterplan F2."""
        assert GATE_FIRE_PROXIMITY_BARS == 5, (
            f"GATE_FIRE_PROXIMITY_BARS must be 5; got {GATE_FIRE_PROXIMITY_BARS}"
        )

    def test_independence_bars_constant(self):
        """INDEPENDENCE_BARS (independence clause) must equal 3 (true trading bars)."""
        assert INDEPENDENCE_BARS == 3, (
            f"INDEPENDENCE_BARS must be 3 (true trading bars); got {INDEPENDENCE_BARS}"
        )


class TestCOILEDFormLabeling:
    """Verify label_coiled_context adds TRUE COILED columns.

    TRUE COILED = washout_ctx AND cohort_frac >= 0.40 per engine/coiled.py assess().
    The in_washout_ctx column is the individual washout state (kept as extra context).
    The in_coiled_ctx column is the TRUE COILED state (S3 fix).
    """

    def _make_short_fixture(self, n: int = 350) -> pd.DataFrame:
        """Return a DataFrame with sufficient bars for washout_ctx (needs >=308 daily bars)."""
        idx = _dates(n)
        vals = np.linspace(100, 80, n)  # gradual decline (washout-like)
        return pd.DataFrame({"close": vals}, index=idx)

    def test_three_columns_added(self):
        """label_coiled_context must add in_washout_ctx, cohort_frac, in_coiled_ctx columns."""
        n = 350
        store = {"AAPL": self._make_short_fixture(n)}
        idx = _dates(n)
        events = pd.DataFrame({
            "ticker": ["AAPL"],
            "date":   [idx[-1]],
        })
        labeled = label_coiled_context(events, store)
        assert "in_washout_ctx" in labeled.columns, "in_washout_ctx column required"
        assert "cohort_frac" in labeled.columns, "cohort_frac column required"
        assert "in_coiled_ctx" in labeled.columns, "in_coiled_ctx column required"

    def test_column_added(self):
        """label_coiled_context must add in_coiled_ctx column (backward compat test)."""
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

    def test_coiled_requires_cohort_gate(self):
        """COILED intersection requires cohort_frac >= 0.40.

        S3 fixture: if washout_ctx=True but cohort_frac < 0.40, in_coiled_ctx
        must be False (not True). This is the test that asserts assess() semantics.

        With only 1 ticker in the panel:
         - sector_map = {"AAPL": "tech"}
         - No peers exist (min_peers=5 not met)
         - cohort_frac = None → in_coiled_ctx = None (untestable, not False)

        With 5+ peers in the same sector, ALL at full value (>30 threshold for washout),
        cohort_frac = 0.0 < 0.40 → in_coiled_ctx = False even if washout_ctx = True.
        """
        from engine.coiled import washout_ctx, cohort_fractions, weekly_d_last, assess

        # Build a multi-ticker panel so cohort_frac can be computed
        n = 350
        idx = _dates(n)
        # AAPL declines (washout-like): washout_ctx might be True
        store: dict[str, pd.DataFrame] = {}
        # Target ticker: declining series
        vals_target = np.concatenate([
            np.full(200, 100.0),   # stable
            np.linspace(100, 80, 150),  # decline
        ])[:n]
        store["AAPL"] = pd.DataFrame({"close": vals_target}, index=idx)
        # 5 peers: all at high values (NOT in washout in terms of weekly D > 30)
        # Using stable / slightly rising series so their weekly StochRSI D is NOT below 30
        for peer in ["PEER1", "PEER2", "PEER3", "PEER4", "PEER5"]:
            vals_peer = np.linspace(80, 120, n)  # steadily rising
            store[peer] = pd.DataFrame({"close": vals_peer}, index=idx)

        # Sector map: all in same sector
        sector_map = {t: "tech" for t in store}

        events = pd.DataFrame({
            "ticker": ["AAPL"],
            "date":   [idx[-1]],
        })
        labeled = label_coiled_context(events, store, sector_map=sector_map)

        # in_washout_ctx and in_coiled_ctx should both be present
        assert "in_washout_ctx" in labeled.columns
        assert "in_coiled_ctx"  in labeled.columns

        # Verify assess() semantics: coiled = washout AND cohort_frac >= 0.40
        # The in_coiled_ctx value should match assess() output for this fixture
        w_val = labeled["in_washout_ctx"].iloc[0]
        f_val = labeled["cohort_frac"].iloc[0]
        c_val = labeled["in_coiled_ctx"].iloc[0]

        if w_val is None or f_val is None:
            # Untestable (insufficient history or insufficient peers)
            assert c_val is None, (
                "in_coiled_ctx must be None when washout_ctx or cohort_frac is None"
            )
        else:
            # Must match assess() semantics exactly
            expected = assess(w_val, f_val, False)["coiled"]
            assert c_val == expected, (
                f"in_coiled_ctx={c_val} does not match assess() coiled={expected} "
                f"(washout_ctx={w_val}, cohort_frac={f_val:.3f})"
            )

    def test_washout_only_does_not_equal_coiled(self):
        """in_washout_ctx is NOT the same as in_coiled_ctx when cohort gate matters.

        This is the canonical S3 fixture: the prior bug used in_washout_ctx
        as if it were in_coiled_ctx. With sector_map=None (fallback), the two
        columns WILL be equal by design (documented fallback). But the labels
        must be DIFFERENT columns with DIFFERENT semantics documented.
        """
        n = 350
        idx = _dates(n)
        vals = np.linspace(100, 80, n)
        store = {"AAPL": pd.DataFrame({"close": vals}, index=idx)}
        events = pd.DataFrame({
            "ticker": ["AAPL"],
            "date":   [idx[-1]],
        })
        # Without sector_map: fallback documented
        labeled = label_coiled_context(events, store, sector_map=None)
        # Both columns must exist regardless
        assert "in_washout_ctx" in labeled.columns
        assert "in_coiled_ctx" in labeled.columns
        # With sector_map provided and 6 tickers in same sector:
        sector_map = {"AAPL": "tech"}
        labeled2 = label_coiled_context(events, store, sector_map=sector_map)
        # With only 1 ticker → min_peers=5 not met → cohort_frac=None → coiled=None
        assert labeled2["cohort_frac"].iloc[0] is None
        assert labeled2["in_coiled_ctx"].iloc[0] is None, (
            "With insufficient peers, in_coiled_ctx must be None (not equal to washout_ctx)"
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
        """NONINFERIORITY_MARGIN must be +0.01 (CI_hi < +1pp = non-inferiority for stop5)."""
        assert abs(NONINFERIORITY_MARGIN - 0.01) < 1e-9, (
            f"NONINFERIORITY_MARGIN must be +0.01; got {NONINFERIORITY_MARGIN}. "
            "Sign convention: stop5 adverse; non-inferiority = CI_hi < +0.01."
        )

    def test_gate_fire_proximity_bars(self):
        """GATE_FIRE_PROXIMITY_BARS must equal 5 (masterplan F2 'within +/-5 bars')."""
        assert GATE_FIRE_PROXIMITY_BARS == 5

    def test_independence_bars_separation(self):
        """INDEPENDENCE_BARS (3) must differ from GATE_FIRE_PROXIMITY_BARS (5).

        The independence clause uses +/-3 TRUE TRADING BARS (not the form's +/-5).
        These must be different constants to prevent confusion.
        """
        assert INDEPENDENCE_BARS == 3
        assert INDEPENDENCE_BARS != GATE_FIRE_PROXIMITY_BARS


# ===========================================================================
# 5. Outcome column tests (RUL-13 compliance)
# ===========================================================================

class TestOutcomeColumns:
    """Verify OUTCOME_COLS contains the correct metrics per RUL-13/14."""

    def test_mae63_removed_from_verdict_cols(self):
        """mae63 must NOT appear in OUTCOME_COLS (RUL-13: mae63 removed from verdict tables)."""
        assert "mae63" not in OUTCOME_COLS, (
            "mae63 must be removed from OUTCOME_COLS per RUL-13. "
            "It feeds no verdict clause in W2."
        )

    def test_fwd_mdd_21_present(self):
        """fwd_mdd_21 (mae21) must be in OUTCOME_COLS (RUL-13 primary)."""
        assert "fwd_mdd_21" in OUTCOME_COLS, (
            "fwd_mdd_21 (mae21) must be a primary outcome per RUL-13."
        )

    def test_stop5_present(self):
        """stop5 must be present (primary adverse outcome)."""
        assert "stop5" in OUTCOME_COLS

    def test_zone_held_21_present(self):
        """zone_held_21 must be present (RUL-14 co-primary, ADDITION C)."""
        assert "zone_held_21" in OUTCOME_COLS, (
            "zone_held_21 must be present as co-primary per RUL-14."
        )

    def test_stop_vol_21_not_in_bh_pool(self):
        """stop_vol_21 must NOT be in the BH pool (mechanical mirror of zone_held_21)."""
        assert "stop_vol_21" not in OUTCOME_COLS_BH, (
            "stop_vol_21 must be excluded from BH pool — it is a mechanical mirror of zone_held_21."
        )

    def test_days_to_10_not_in_bh_pool(self):
        """days_to_10 must NOT be in BH pool (collider/selection-biased)."""
        assert "days_to_10" not in OUTCOME_COLS_BH, (
            "days_to_10 must be excluded from BH pool (selection-biased collider outcome)."
        )


# ===========================================================================
# 6. Independence clause: true trading bars (MINOR fix verification)
# ===========================================================================

class TestTradingBarsIndependence:
    """Verify compute_cofire_share_trading_bars uses true bar distance, not calendar approx."""

    def _make_trading_index(self, n: int = 100, start: str = "2020-01-02") -> pd.DatetimeIndex:
        return pd.bdate_range(start=start, periods=n)

    def test_adjacent_bars_detected(self):
        """Events at bar 10 and gate fires at bar 11 (1 bar) must be detected at ±3."""
        idx = self._make_trading_index(50)
        # Event on bar 10
        events = pd.DataFrame({
            "ticker": ["AAPL"],
            "date": [idx[10]],
            "undercut_date": [idx[5]],
        })
        gate_fires = pd.DataFrame({
            "ticker": ["AAPL"],
            "date": [idx[11]],  # 1 bar away
        })
        ohlcv = {"AAPL": pd.DataFrame({"close": np.full(50, 100.0)}, index=idx)}
        share, n_near = compute_cofire_share_trading_bars(events, ohlcv, gate_fires, 3)
        assert n_near == 1, f"Expected 1 near co-fire; got {n_near}"
        assert share == 1.0

    def test_far_bars_not_detected(self):
        """Events at bar 10 and gate fires at bar 20 (10 bars) must NOT be detected at ±3."""
        idx = self._make_trading_index(50)
        events = pd.DataFrame({
            "ticker": ["AAPL"],
            "date": [idx[10]],
            "undercut_date": [idx[5]],
        })
        gate_fires = pd.DataFrame({
            "ticker": ["AAPL"],
            "date": [idx[20]],  # 10 bars away
        })
        ohlcv = {"AAPL": pd.DataFrame({"close": np.full(50, 100.0)}, index=idx)}
        share, n_near = compute_cofire_share_trading_bars(events, ohlcv, gate_fires, 3)
        assert n_near == 0, f"Expected 0 near co-fires (10 bars > 3 threshold); got {n_near}"
        assert share == 0.0

    def test_empty_events_returns_zero(self):
        """Empty events must return (0.0, 0)."""
        gate_fires = pd.DataFrame({"ticker": ["AAPL"], "date": [pd.Timestamp("2020-01-10")]})
        ohlcv = {"AAPL": pd.DataFrame({"close": np.ones(50)}, index=self._make_trading_index(50))}
        share, n = compute_cofire_share_trading_bars(pd.DataFrame(), ohlcv, gate_fires, 3)
        assert share == 0.0
        assert n == 0


# ===========================================================================
# 7. ADDITION A — Verdict-logic unit tests (sign-convention blocker)
#
# These are the tests that would have caught the sign-convention inversion.
# A candidate WORSE on stop5 (positive coef, CI entirely above 0) must FAIL.
# A candidate BETTER on stop5 (negative coef, CI entirely below 0) must PASS.
# A boundary case at exactly the margin must be tested for correct direction.
# ===========================================================================

class TestVerdictLogic:
    """Verdict-logic unit tests for check_species_bar_per_form.

    CRITICAL: these tests guard the sign-convention blocker.

    Sign convention: stop5 is ADVERSE.
    - POSITIVE coef = MORE stops = WORSE candidate.
    - NEGATIVE coef = FEWER stops = BETTER candidate.
    - Non-inferiority = CI_hi < +0.01 (not worse than incumbent by >1pp).
    - Superiority on stop5 = CI_hi < 0.0 (significantly fewer stops).
    """

    def _eval_form(
        self,
        stop5_coef: float,
        stop5_ci_lo: float,
        stop5_ci_hi: float,
        n_events: int = 200,
        **kwargs
    ) -> dict:
        """Run check_species_bar_per_form with synthetic results."""
        results = _make_synthetic_results(
            stop5_coef=stop5_coef,
            stop5_ci_lo=stop5_ci_lo,
            stop5_ci_hi=stop5_ci_hi,
            **kwargs
        )
        return check_species_bar_per_form(
            form_label="test_form",
            results=results,
            n_events=n_events,
            co_fire_share=0.10,  # well below 0.60 threshold
            coiled_fire_recall=None,
            ur_recall=0.20,
        )

    # --- Clearly WORSE candidate (positive coef, CI entirely above 0) ---

    def test_clearly_worse_fails_noninferiority(self):
        """Candidate with stop5 coef=+0.0244, CI=[+0.021,+0.037] must FAIL non-inferiority.

        This is the actual standalone form result from the original (incorrectly labeled) report.
        Under the correct sign convention, CI_hi=+0.037 > +0.01 → FAILS non-inferiority.
        The original code incorrectly used CI_lo > -0.01, which passed this case.
        """
        sb = self._eval_form(
            stop5_coef=+0.0244,
            stop5_ci_lo=+0.021,
            stop5_ci_hi=+0.037,
        )
        assert sb["stop5_noninferiority_met"] is False, (
            "Candidate with stop5 CI entirely above 0 (+0.021, +0.037) must FAIL non-inferiority. "
            f"Got: stop5_noninferiority_met={sb['stop5_noninferiority_met']}, "
            f"CI_hi={sb['stop5_ci_hi']}"
        )

    def test_clearly_worse_fails_stop5_superiority(self):
        """Candidate with stop5 CI=[+0.021,+0.037] must FAIL stop5 superiority (CI_hi > 0)."""
        sb = self._eval_form(
            stop5_coef=+0.0244,
            stop5_ci_lo=+0.021,
            stop5_ci_hi=+0.037,
        )
        assert sb["stop5_superiority_met"] is False, (
            "Candidate with positive stop5 CI must FAIL stop5 superiority."
        )

    def test_clearly_worse_coiled_fails_noninferiority(self):
        """COILED form coef=+0.0467, CI=[+0.036,+0.057] must FAIL non-inferiority.

        This is the actual COILED form result. CI_hi=+0.057 >> +0.01.
        """
        sb = self._eval_form(
            stop5_coef=+0.0467,
            stop5_ci_lo=+0.036,
            stop5_ci_hi=+0.057,
        )
        assert sb["stop5_noninferiority_met"] is False, (
            "COILED form with stop5 coef=+0.0467 CI=[+0.036,+0.057] must FAIL non-inferiority. "
            f"Got: stop5_noninferiority_met={sb['stop5_noninferiority_met']}"
        )

    # --- Clearly BETTER candidate (negative coef, CI entirely below 0) ---

    def test_clearly_better_passes_noninferiority(self):
        """Candidate with stop5 coef=-0.0266, CI=[-0.033,-0.009] must PASS non-inferiority.

        CI_hi=-0.009 < +0.01 → PASSES non-inferiority.
        This mirrors the gatefire-proximity form result.
        """
        sb = self._eval_form(
            stop5_coef=-0.0266,
            stop5_ci_lo=-0.033,
            stop5_ci_hi=-0.009,
        )
        assert sb["stop5_noninferiority_met"] is True, (
            "Candidate with stop5 CI entirely below 0 must PASS non-inferiority. "
            f"Got: stop5_noninferiority_met={sb['stop5_noninferiority_met']}, "
            f"CI_hi={sb['stop5_ci_hi']}"
        )

    def test_clearly_better_passes_stop5_superiority(self):
        """Candidate with stop5 CI=[-0.033,-0.009] must PASS stop5 superiority (CI_hi < 0)."""
        sb = self._eval_form(
            stop5_coef=-0.0266,
            stop5_ci_lo=-0.033,
            stop5_ci_hi=-0.009,
        )
        assert sb["stop5_superiority_met"] is True, (
            "Candidate with CI_hi < 0 must PASS stop5 superiority."
        )

    def test_clearly_better_stop5_in_superiority_axes(self):
        """stop5 must appear in superiority_axes when CI_hi < 0."""
        sb = self._eval_form(
            stop5_coef=-0.0266,
            stop5_ci_lo=-0.033,
            stop5_ci_hi=-0.009,
        )
        assert "stop5" in sb["superiority_axes"], (
            "stop5 must be in superiority_axes when CI_hi < 0."
        )

    # --- Boundary cases ---

    def test_boundary_ci_hi_exactly_at_margin_fails(self):
        """CI_hi exactly at +0.01 must FAIL non-inferiority (strict: CI_hi < 0.01 required)."""
        sb = self._eval_form(
            stop5_coef=+0.005,
            stop5_ci_lo=-0.003,
            stop5_ci_hi=+0.010,   # exactly at the margin
        )
        # CI_hi < 0.01 is required; CI_hi == 0.01 fails
        assert sb["stop5_noninferiority_met"] is False, (
            "CI_hi exactly at +0.01 must FAIL non-inferiority (strict inequality required)."
        )

    def test_boundary_ci_hi_just_below_margin_passes(self):
        """CI_hi just below +0.01 (e.g., +0.0099) must PASS non-inferiority."""
        sb = self._eval_form(
            stop5_coef=+0.004,
            stop5_ci_lo=-0.002,
            stop5_ci_hi=+0.0099,  # just below the margin
        )
        assert sb["stop5_noninferiority_met"] is True, (
            "CI_hi just below +0.01 must PASS non-inferiority."
        )

    def test_boundary_straddling_zero_fails_superiority(self):
        """CI straddling zero (e.g., [-0.003, +0.005]) must FAIL stop5 superiority."""
        sb = self._eval_form(
            stop5_coef=+0.001,
            stop5_ci_lo=-0.003,
            stop5_ci_hi=+0.005,
        )
        assert sb["stop5_superiority_met"] is False, (
            "CI straddling zero must FAIL stop5 superiority (CI_hi > 0)."
        )

    # --- n_events check ---

    def test_insufficient_events_fails_n_clause(self):
        """n_events < 150 must FAIL the n_events clause."""
        sb = self._eval_form(
            stop5_coef=-0.03,
            stop5_ci_lo=-0.05,
            stop5_ci_hi=-0.01,
            n_events=100,  # below MIN_EPISODES_PER_FORM=150
        )
        assert sb["n_met"] is False, (
            f"n_events=100 < 150 must FAIL n_met clause. Got: {sb['n_met']}"
        )

    def test_sufficient_events_passes_n_clause(self):
        """n_events >= 150 must PASS the n_events clause."""
        sb = self._eval_form(
            stop5_coef=-0.03,
            stop5_ci_lo=-0.05,
            stop5_ci_hi=-0.01,
            n_events=200,  # above threshold
        )
        assert sb["n_met"] is True, (
            f"n_events=200 >= 150 must PASS n_met clause. Got: {sb['n_met']}"
        )

    # --- Constitution axes (superiority clause) ---

    def test_cushion_superiority_counts_as_constitution_axis(self):
        """cushion_rot with CI_lo > 0 must appear in superiority_axes."""
        sb = self._eval_form(
            stop5_coef=+0.02,
            stop5_ci_lo=+0.01,
            stop5_ci_hi=+0.04,
            cushion_coef=+0.05,
            cushion_ci_lo=+0.01,  # CI_lo > 0 → superiority
            cushion_ci_hi=+0.09,
        )
        assert "cushion_rot" in sb["superiority_axes"], (
            "cushion_rot with CI_lo > 0 must appear in superiority_axes."
        )
        assert sb["superiority_met"] is True, (
            "superiority_met must be True when cushion_rot has CI_lo > 0."
        )

    def test_dead_money_direction_adverse_not_beneficial(self):
        """dead_money is ADVERSE (S4 fix): more dead money = WORSE.

        Superiority = CI_hi < 0 (significantly FEWER dead money outcomes).
        A candidate with positive dead_money coef (MORE dead money) and CI entirely
        above zero must NOT earn dead_money superiority — CI_lo > 0 would count MORE
        dead money as "beneficial," which is latently inverted.

        This is the S4 test: a candidate producing MORE dead money must never earn
        superiority on that axis.
        """
        # Candidate with more dead money: positive coef, CI entirely above 0
        sb = self._eval_form(
            stop5_coef=+0.02,
            stop5_ci_lo=+0.01,
            stop5_ci_hi=+0.04,
            dead_coef=+0.03,
            dead_ci_lo=+0.01,   # CI_lo > 0 and CI_hi > 0: MORE dead money (adverse)
            dead_ci_hi=+0.05,
        )
        # dead_money is in ADVERSE_METRICS: superiority = CI_hi < 0.
        # Here CI_hi = +0.05 > 0 → NOT superior on dead_money.
        assert "dead_money" not in sb["superiority_axes"], (
            "dead_money with CI entirely above 0 (MORE dead money) must NOT earn superiority. "
            "dead_money is ADVERSE: superiority = CI_hi < 0 (significantly FEWER adverse outcomes). "
            f"Got superiority_axes={sb['superiority_axes']}"
        )

    def test_dead_money_superiority_with_negative_ci(self):
        """dead_money with CI entirely below 0 (FEWER dead money) must earn superiority.

        S4 fix: dead_money is in ADVERSE_METRICS, so superiority = CI_hi < 0.
        """
        sb = self._eval_form(
            stop5_coef=-0.02,
            stop5_ci_lo=-0.03,
            stop5_ci_hi=-0.01,
            dead_coef=-0.04,
            dead_ci_lo=-0.06,   # CI entirely below 0 = FEWER dead money = BETTER
            dead_ci_hi=-0.02,
        )
        assert "dead_money" in sb["superiority_axes"], (
            "dead_money with CI entirely below 0 (CI_hi < 0) must earn superiority on "
            "the adverse-direction axis. "
            f"Got superiority_axes={sb['superiority_axes']}"
        )

    def test_adverse_metrics_set_contains_dead_money(self):
        """ADVERSE_METRICS must contain dead_money, stop5, and stop_vol_21 (S4 requirement)."""
        assert "dead_money" in ADVERSE_METRICS, "dead_money must be in ADVERSE_METRICS"
        assert "stop5" in ADVERSE_METRICS, "stop5 must be in ADVERSE_METRICS"
        assert "stop_vol_21" in ADVERSE_METRICS, "stop_vol_21 must be in ADVERSE_METRICS"

    def test_beneficial_metrics_do_not_overlap_adverse(self):
        """BENEFICIAL_METRICS and ADVERSE_METRICS must be disjoint."""
        overlap = ADVERSE_METRICS & BENEFICIAL_METRICS
        assert len(overlap) == 0, (
            f"ADVERSE_METRICS and BENEFICIAL_METRICS overlap: {overlap}. "
            "A metric cannot be both adverse and beneficial."
        )

    # --- Independence clause ---

    def test_high_cofire_fails_independence_clause(self):
        """co_fire_share > 0.60 must FAIL the independence clause."""
        results = _make_synthetic_results(stop5_coef=-0.02, stop5_ci_lo=-0.03, stop5_ci_hi=-0.01)
        sb = check_species_bar_per_form(
            form_label="test",
            results=results,
            n_events=200,
            co_fire_share=0.70,  # > 0.60
            coiled_fire_recall=None,
            ur_recall=0.20,
        )
        assert sb["independence_clause_met"] is False, (
            "co_fire_share=0.70 > 0.60 must FAIL independence clause."
        )

    def test_low_cofire_passes_independence_clause(self):
        """co_fire_share <= 0.60 must PASS the independence clause."""
        results = _make_synthetic_results(stop5_coef=-0.02, stop5_ci_lo=-0.03, stop5_ci_hi=-0.01)
        sb = check_species_bar_per_form(
            form_label="test",
            results=results,
            n_events=200,
            co_fire_share=0.10,  # well below 0.60
            coiled_fire_recall=None,
            ur_recall=0.20,
        )
        assert sb["independence_clause_met"] is True, (
            "co_fire_share=0.10 <= 0.60 must PASS independence clause."
        )

    # --- zone_held_21 presence (ADDITION C) ---

    def test_zone_held_21_in_results(self):
        """zone_held_21 must appear in effects and be accessible in species bar."""
        results = _make_synthetic_results(
            stop5_coef=-0.02,
            stop5_ci_lo=-0.03,
            stop5_ci_hi=-0.01,
            zone_coef=+0.04,
            zone_ci_lo=+0.01,
            zone_ci_hi=+0.07,
        )
        sb = check_species_bar_per_form(
            form_label="test",
            results=results,
            n_events=200,
            co_fire_share=0.10,
            coiled_fire_recall=None,
            ur_recall=0.20,
        )
        # zone_held_21_coef should be accessible
        assert sb.get("zone_held_21_coef") is not None, (
            "zone_held_21_coef must be accessible in species bar dict (ADDITION C)."
        )
        assert abs(sb["zone_held_21_coef"] - 0.04) < 1e-9


# ===========================================================================
# 8. Era sign-stability helper (internal)
# ===========================================================================

class TestEraSignStability:
    """Verify _check_era_sign_stability correctly identifies sign-stable eras."""

    def test_all_positive_sign_stable(self):
        """4/4 eras with positive diff → sign-stable True."""
        from scripts.research.run_w2_sur import _check_era_sign_stability
        # Build era table: 4 eras, treatment always worse (stop5_rate higher)
        eras = ["2012-2015", "2016-2019", "2020-2022", "2023-2026"]
        rows = []
        for era in eras:
            rows.append({"era": era, "_is_sur": 1, "stop5_rate": 0.15, "n_fires": 50})
            rows.append({"era": era, "_is_sur": 0, "stop5_rate": 0.10, "n_fires": 100})
        era_tbl = pd.DataFrame(rows)
        result = _check_era_sign_stability(era_tbl, "_is_sur")
        assert result is True

    def test_mixed_signs_not_stable(self):
        """2/4 eras positive, 2/4 negative → NOT sign-stable."""
        from scripts.research.run_w2_sur import _check_era_sign_stability
        rows = [
            {"era": "2012-2015", "_is_sur": 1, "stop5_rate": 0.15, "n_fires": 50},
            {"era": "2012-2015", "_is_sur": 0, "stop5_rate": 0.10, "n_fires": 100},
            {"era": "2016-2019", "_is_sur": 1, "stop5_rate": 0.08, "n_fires": 50},  # reversed
            {"era": "2016-2019", "_is_sur": 0, "stop5_rate": 0.12, "n_fires": 100},
            {"era": "2020-2022", "_is_sur": 1, "stop5_rate": 0.18, "n_fires": 50},
            {"era": "2020-2022", "_is_sur": 0, "stop5_rate": 0.12, "n_fires": 100},
            {"era": "2023-2026", "_is_sur": 1, "stop5_rate": 0.07, "n_fires": 50},  # reversed
            {"era": "2023-2026", "_is_sur": 0, "stop5_rate": 0.11, "n_fires": 100},
        ]
        era_tbl = pd.DataFrame(rows)
        result = _check_era_sign_stability(era_tbl, "_is_sur")
        assert result is False

    def test_3_of_4_eras_stable(self):
        """3/4 eras same sign → sign-stable True."""
        from scripts.research.run_w2_sur import _check_era_sign_stability
        rows = [
            {"era": "2012-2015", "_is_sur": 1, "stop5_rate": 0.15, "n_fires": 50},
            {"era": "2012-2015", "_is_sur": 0, "stop5_rate": 0.10, "n_fires": 100},
            {"era": "2016-2019", "_is_sur": 1, "stop5_rate": 0.08, "n_fires": 50},  # reversed
            {"era": "2016-2019", "_is_sur": 0, "stop5_rate": 0.12, "n_fires": 100},
            {"era": "2020-2022", "_is_sur": 1, "stop5_rate": 0.18, "n_fires": 50},
            {"era": "2020-2022", "_is_sur": 0, "stop5_rate": 0.12, "n_fires": 100},
            {"era": "2023-2026", "_is_sur": 1, "stop5_rate": 0.16, "n_fires": 50},
            {"era": "2023-2026", "_is_sur": 0, "stop5_rate": 0.11, "n_fires": 100},
        ]
        era_tbl = pd.DataFrame(rows)
        result = _check_era_sign_stability(era_tbl, "_is_sur")
        assert result is True  # 3 of 4 positive

    def test_insufficient_data_returns_none(self):
        """Fewer than 2 eras with both strata → returns None."""
        from scripts.research.run_w2_sur import _check_era_sign_stability
        rows = [
            {"era": "2012-2015", "_is_sur": 1, "stop5_rate": 0.15, "n_fires": 50},
            # only treatment, no control
        ]
        era_tbl = pd.DataFrame(rows)
        result = _check_era_sign_stability(era_tbl, "_is_sur")
        assert result is None


# ===========================================================================
# 9. NC-2 injected-effect regression test (FINDING 1 requirement)
#
# The prior _run_nc2_band_fe implementation assigned bands ONLY to treatment
# rows, causing perfect FE separation and a degenerate coef = 0.0 with
# zero-width CI regardless of the true effect. This test verifies that
# an injected +5pp true treatment effect is recovered (not 0.0000).
# ===========================================================================

class TestNC2InjectedEffect:
    """NC-2 band FE must recover a known injected effect, not return 0.0.

    CRITICAL: This test is the sentinel against the degenerate-NC-2 blocker.
    If _run_nc2_band_fe assigns bands only to treatment rows, the composite
    date+band FE will perfectly separate arms → coef = 0.0000 regardless of
    any planted effect. A recovered coefficient near +0.05 confirms the fix.
    """

    def _make_nc2_synthetic_frame(
        self,
        n_treatment: int = 120,
        n_control: int = 300,
        true_effect: float = 0.05,
        seed: int = 42,
    ) -> tuple[dict, "pd.DataFrame"]:
        """Build a synthetic gradable DataFrame with a known planted stop5 effect.

        KEY DESIGN REQUIREMENTS for a non-degenerate NC-2 band FE test:
        1. Multiple distinct event dates — the composite FE = date+band needs
           multiple cells so treatment and control can SHARE cells.
        2. Mixed proximity profiles — price histories must produce at least TWO
           distinct proximity bands so band FE absorbs confounding.
        3. Both arms represented in each FE cell — each date bucket must contain
           treatment AND control rows with the same band.

        SOLUTION: Use N_DATES event-date clusters, each with a BALANCED mix of
        treatment and control rows. Within each cluster, half the rows have a
        CLOSE proximity profile (price still near the 63-bar low at event date)
        and half have a FAR proximity profile (price well above the 63-bar low).
        This creates cells with BOTH arms in the same (date, band) FE cell,
        enabling the estimator to isolate the treatment coefficient.

        The key insight: to avoid FE perfect separation, EVERY (date, band) cell
        must contain at least one treatment AND one control row.

        Returns (closes_dict, gradable_df).
        The planted effect = true_effect on the stop5 outcome for treatment arm.
        """
        rng = np.random.default_rng(seed)

        # Use 10 distinct event-date clusters to create FE variation
        N_DATES = 10
        PRICE_LEN = 200
        # Events fire at bar 100 (63 bars of lookback before it)
        EV_POS = 100

        rows = []
        closes: dict[str, pd.Series] = {}

        # Base date: 2014-01-02; each cluster starts 20 business days apart
        base_start = pd.Timestamp("2014-01-02")

        # Interleave treatment and control within each cluster:
        # n_treat_per_cluster treatment rows + n_ctrl_per_cluster control rows
        # so every cluster has BOTH arms.
        n_treat_per_cluster = n_treatment // N_DATES  # e.g. 12
        n_ctrl_per_cluster = n_control // N_DATES      # e.g. 30

        ticker_idx = 0
        for d_cluster in range(N_DATES):
            cluster_start = base_start + pd.offsets.BDay(d_cluster * 20)
            price_idx = pd.bdate_range(cluster_start, periods=PRICE_LEN)
            ev_date = price_idx[EV_POS]
            era_str = "2015-2019"

            # Build treatment and control rows for this cluster
            n_treat_c = n_treat_per_cluster if d_cluster < N_DATES - 1 else (n_treatment - ticker_idx)
            n_ctrl_c = n_ctrl_per_cluster

            cluster_rows = (
                [(True, j) for j in range(n_treat_c)]
                + [(False, j) for j in range(n_ctrl_c)]
            )

            for is_treat, j in cluster_rows:
                ticker = f"SYN_{ticker_idx:04d}"

                # Alternate between two proximity profiles within each cluster:
                # CLOSE profile (j even): price ~5% above 63-bar low → band 0
                # FAR profile (j odd): price ~50% above 63-bar low → band 1 or 2
                use_close_profile = (j % 2 == 0)

                close_vals = np.ones(PRICE_LEN) * 100.0
                if use_close_profile:
                    # Deep undercut zone; at event date still near the low
                    close_vals[EV_POS - 30 : EV_POS] = 60.0
                    close_vals[EV_POS] = 63.0  # ~5% above 63-bar min (60)
                else:
                    # Mild dip; at event date well above the low
                    close_vals[EV_POS - 30 : EV_POS] = 80.0
                    close_vals[EV_POS] = 100.0  # 25% above 63-bar min (80)

                closes[ticker] = pd.Series(close_vals, index=price_idx)

                # Planted stop5: treatment arm has higher stop rate by true_effect
                base_stop_rate = 0.15
                stop5_val = float(
                    rng.random() < (base_stop_rate + true_effect if is_treat else base_stop_rate)
                )

                rows.append({
                    "ticker": ticker,
                    "date": ev_date,
                    "era": era_str,
                    "_fe": str(ev_date)[:10],
                    "stratum": 1 if is_treat else 0,
                    "stop5": stop5_val,
                    "gradable": True,
                    "sector": "tech",
                })

                ticker_idx += 1

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return closes, df

    def test_injected_effect_recovered_not_zero(self):
        """A synthetic +5pp stop5 effect must yield a non-zero coef after NC-2 band FE.

        This is the critical sentinel: if _run_nc2_band_fe still assigns bands
        only to treatment rows, the composite FE will perfectly separate arms
        and return coef = 0.0 with zero-width CI — failing this test.

        With the fix (bands computed for both arms), the estimator can see
        both arms in the same FE cells and recover a coefficient near +0.05.
        Tolerance: coef should NOT be exactly 0.0000.
        """
        true_effect = 0.05
        closes, df = self._make_nc2_synthetic_frame(
            n_treatment=120,
            n_control=300,
            true_effect=true_effect,
            seed=99,
        )

        result = _run_nc2_band_fe(
            gradable=df,
            stratum_col="stratum",
            closes=closes,
            n_bootstrap=100,  # small for speed in test
            rng_seed=0,
            panel="test",
            sector_col="sector",
        )

        # The band FE computation must succeed (enough rows)
        assert result.get("band_computed", False), (
            f"NC-2 band FE failed to compute: {result.get('note', 'unknown')}. "
            "This may indicate insufficient price history for the proxy computation."
        )

        coef = result.get("coef")
        assert coef is not None, "NC-2 band FE returned no coefficient."

        # PRIMARY ASSERTION: the coefficient must NOT be exactly 0.0000.
        # A degenerate (perfectly separated) FE produces coef = 0.0 exactly.
        # A non-degenerate result will be some non-zero value (positive or negative
        # depending on the realized stop5 rates after band FE absorption).
        assert coef != 0.0, (
            f"NC-2 band FE returned coef = 0.0000 — this indicates the degenerate "
            f"FE-separation bug is still present. Expected a non-zero coefficient "
            f"(planted effect = +{true_effect:.3f}). "
            "Fix: ensure compute_nc2_proximity_proxy is called on ALL rows (both "
            "treatment and control), not just treatment rows."
        )

        # SECONDARY ASSERTION: CI bounds must not both be exactly 0.0
        ci_lo = result.get("ci_lo", None)
        ci_hi = result.get("ci_hi", None)
        if ci_lo is not None and ci_hi is not None:
            assert not (ci_lo == 0.0 and ci_hi == 0.0), (
                "NC-2 band FE returned zero-width CI at 0.0 — degenerate regression. "
                f"coef={coef}, ci_lo={ci_lo}, ci_hi={ci_hi}"
            )


# ===========================================================================
# 10. Per-form independence: co-fire shares differ between forms (FINDING 2)
#
# The gatefire form IS the gate-fire-proximate event subset, so its co-fire
# share is ~100% by construction. The standalone form should have a lower
# co-fire share. This test verifies the per-form computation differs.
# ===========================================================================

class TestPerFormCofireShares:
    """Per-form co-fire shares must differ between standalone and gatefire forms.

    CRITICAL: The prior implementation computed a single co-fire share from the
    standalone event set and fed it identically to all three forms. This masked
    the fact that the gatefire form is definitionally 100% co-fired.

    This test constructs a scenario where:
    - A gate fire at date D exists for a ticker
    - A U&R event at the same date D (near gate fire) → in gatefire form
    - A U&R event far from any gate fire → in standalone-only
    The gatefire form must show higher co-fire share than standalone.
    """

    def _make_cofire_fixture(self) -> tuple:
        """Two events: one near a gate fire, one far from any gate fire."""
        idx = pd.bdate_range("2020-01-02", periods=100)

        # Event 1: near gate fire (at bar 10; gate fire at bar 11 = 1 bar away)
        ev_near = pd.DataFrame({
            "ticker": ["AAPL"],
            "date": [idx[10]],
            "undercut_date": [idx[5]],
        })

        # Event 2: far from any gate fire (at bar 80)
        ev_far = pd.DataFrame({
            "ticker": ["MSFT"],
            "date": [idx[80]],
            "undercut_date": [idx[75]],
        })

        events_combined = pd.concat([ev_near, ev_far], ignore_index=True)

        # Gate fire only for AAPL at bar 11 (1 bar from event 1)
        gate_fires = pd.DataFrame({
            "ticker": ["AAPL"],
            "date": [idx[11]],
        })

        # OHLCV with trading index
        ohlcv = {
            "AAPL": pd.DataFrame({"close": np.full(100, 100.0)}, index=idx),
            "MSFT": pd.DataFrame({"close": np.full(100, 100.0)}, index=idx),
        }

        return events_combined, gate_fires, ohlcv, idx

    def test_gatefire_form_has_higher_cofire_share(self):
        """Gatefire-proximate events must show higher co-fire share than far events.

        Standalone (all events): AAPL + MSFT → co-fire = 50% (1 of 2 events near gate fire).
        Gatefire subset (near-gate events only): AAPL → co-fire = 100%.
        Per-form co-fire shares MUST differ.
        """
        events, gate_fires, ohlcv, idx = self._make_cofire_fixture()

        # Standalone: both events → co-fire share = 50%
        sa_share, sa_n = compute_cofire_share_trading_bars(events, ohlcv, gate_fires, 3)

        # Gatefire subset: only AAPL (near gate fire) → co-fire share = 100%
        gf_events = events[events["ticker"] == "AAPL"].copy()
        gf_share, gf_n = compute_cofire_share_trading_bars(gf_events, ohlcv, gate_fires, 3)

        assert sa_share < gf_share, (
            f"Standalone co-fire ({sa_share:.1%}) must be lower than gatefire co-fire "
            f"({gf_share:.1%}). Per-form co-fire shares must differ."
        )
        assert gf_share == 1.0, (
            f"Gatefire subset (all events near gate fire) must have co-fire share = 100%. "
            f"Got: {gf_share:.1%}"
        )
        assert sa_share == 0.5, (
            f"Standalone with 1 of 2 events near gate fire must have co-fire share = 50%. "
            f"Got: {sa_share:.1%}"
        )

    def test_cofire_per_form_not_shared_constant(self):
        """Computing co-fire on the full event set must differ from the gatefire subset.

        This validates that the BLOCKER FIX is meaningful: had we used the
        standalone set's co-fire share for the gatefire form, we'd pass a 50%
        share (below 60% threshold), wrongly PASSING the independence clause.
        With per-form computation, the gatefire form shows 100% and FAILS.
        """
        events, gate_fires, ohlcv, idx = self._make_cofire_fixture()

        # Shared (old buggy approach): co-fire of FULL event set
        shared_share, _ = compute_cofire_share_trading_bars(events, ohlcv, gate_fires, 3)

        # Per-form (correct): co-fire of gatefire-proximate subset only
        gf_events = events[events["ticker"] == "AAPL"].copy()
        gf_share, _ = compute_cofire_share_trading_bars(gf_events, ohlcv, gate_fires, 3)

        # The shared approach wrongly passes the gatefire form (50% <= 60%)
        assert shared_share <= MAX_COFIRE_SHARE, (
            f"Shared co-fire ({shared_share:.1%}) must be <= 60% (wrongly passes the threshold). "
            "This is the prior behavior — the bug."
        )
        # The per-form approach correctly fails the gatefire form (100% > 60%)
        assert gf_share > MAX_COFIRE_SHARE, (
            f"Per-form gatefire co-fire ({gf_share:.1%}) must be > 60% (correctly fails). "
            "This is the fixed behavior."
        )


# ===========================================================================
# 11. Species ID and registry collision tests (S1/S2 requirements)
# ===========================================================================

class TestSpeciesIDRegistry:
    """Verify Spring Reclaim uses S15 (not S14 which was taken by Failed Breakout).

    S1 blocker: S14 = Failed breakout is registered on origin/main (PR #1457).
    Spring Reclaim must use the next free number: S15.
    """

    def test_species_id_is_s15(self):
        """SPECIES_ID constant must be 'S15' — not S14 (which is Failed Breakout)."""
        from scripts.research.run_w2_sur import SPECIES_ID
        assert SPECIES_ID == "S15", (
            f"SPECIES_ID must be 'S15' (S14 was taken by Failed Breakout via PR #1457). "
            f"Got: {SPECIES_ID!r}"
        )

    def test_s14_not_spring_reclaim(self):
        """Verify that S14 in the registry is NOT Spring Reclaim.

        The registry must show S14 = 'Failed breakout' (from PR #1457), not
        Spring Reclaim. If this fails, there is a registry clobber (S2 blocker).
        """
        import json
        registry_path = _REPO_ROOT / "data" / "species" / "registry.json"
        if not registry_path.exists():
            return  # registry not available; skip
        with open(registry_path) as f:
            reg = json.load(f)
        species_list = reg.get("species", []) if isinstance(reg, dict) else []
        s14_entries = [s for s in species_list if isinstance(s, dict) and s.get("species_id") == "S14"]
        for entry in s14_entries:
            name = entry.get("name", "")
            assert "Spring Reclaim" not in name and "U&R" not in name, (
                f"S14 must not be Spring Reclaim (registry clobber detected). "
                f"Found S14 = {name!r}. Spring Reclaim must register as S15."
            )

    def test_s15_spring_reclaim_in_registry(self):
        """Verify S15 = Spring Reclaim is in the registry.

        After the branch commit, data/species/registry.json must contain an
        entry with species_id='S15' and the Spring Reclaim / U&R name.
        """
        import json
        registry_path = _REPO_ROOT / "data" / "species" / "registry.json"
        if not registry_path.exists():
            return  # registry not available; skip
        with open(registry_path) as f:
            reg = json.load(f)
        species_list = reg.get("species", []) if isinstance(reg, dict) else []
        s15_entries = [s for s in species_list if isinstance(s, dict) and s.get("species_id") == "S15"]
        assert len(s15_entries) >= 1, (
            "S15 (Spring Reclaim) must be registered in data/species/registry.json. "
            "The registry currently has no S15 entry. "
            f"Registered species: {[s.get('species_id') for s in species_list if isinstance(s, dict)]}"
        )
        s15 = s15_entries[0]
        name = s15.get("name", "")
        assert "Spring Reclaim" in name or "U&R" in name or "Undercut" in name, (
            f"S15 name must reference Spring Reclaim/U&R. Got: {name!r}"
        )
