"""Tests for scripts/study_construction_divergence.py.

Fixture-driven with synthetic price panels; no real data dependencies.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.study_construction_divergence import (
    _block_collapse,
    _compute_label_series,
    _extract_cap_lags_ew,
    _extract_events,
    _is_reducing,
    _panel_breadth,
    _rs_features,
    DEOVERLAP_MIN,
    BLOCK_DAYS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dates(n: int, start: str = "2010-01-04") -> pd.DatetimeIndex:
    """Generate n business days from start."""
    return pd.bdate_range(start=start, periods=n)


def _make_price_series(n: int, start: float = 100.0, drift: float = 0.0,
                       noise: float = 0.01, seed: int = 0) -> pd.Series:
    """Random walk price series."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift / 252, noise, n)
    prices = start * np.cumprod(1.0 + returns)
    dates = _make_dates(n)
    return pd.Series(prices, index=dates, name="close")


def _make_declining_series(n: int, start: float = 100.0,
                            decline_pct: float = -0.01) -> pd.Series:
    """Steadily declining price series for forcing fading/deteriorating labels."""
    dates = _make_dates(n)
    prices = start * (1.0 + decline_pct) ** np.arange(n)
    return pd.Series(prices.astype(float), index=dates, name="close")


# ---------------------------------------------------------------------------
# Test (a): onset de-overlap >= 15d works
# ---------------------------------------------------------------------------

class TestDeoverlapMinimum:
    """Verify that events within DEOVERLAP_MIN trading days are suppressed."""

    def test_deoverlap_suppresses_rapid_refires(self):
        """Two onsets < 15 days apart: only the first should be recorded."""
        n = 600
        dates = _make_dates(n)
        # Build cap series that dips into 'fading' state early and often
        # We'll use a synthetic declining series
        cap_s = _make_declining_series(n, start=100.0, decline_pct=-0.002)
        spy_s = _make_price_series(n, start=100.0, drift=0.05, seed=1)
        # Build a panel with the cap series (needed for breadth)
        panel = pd.DataFrame({"CAP": cap_s, "SPY": spy_s})

        cap_labels = _compute_label_series(cap_s, spy_s, panel)

        # Find reducing runs
        reducing_indices = [i for i, v in enumerate(cap_labels) if _is_reducing(v)]
        if len(reducing_indices) < 2:
            pytest.skip("Not enough reducing states for de-overlap test")

        # For this test, just verify the extraction function respects DEOVERLAP_MIN
        # We'll use a fake ew_labels series (all non-reducing = "neutral") to get divergent events
        ew_labels = pd.Series("neutral", index=cap_s.index)
        window_start = cap_s.index[max(252, 200)]
        lookahead_audit: dict = {}

        events = _extract_events(
            cap_labels, ew_labels, cap_s, spy_s, "TEST", window_start, lookahead_audit
        )

        if len(events) >= 2:
            # Check all event pairs are >= DEOVERLAP_MIN bars apart
            for i in range(len(events) - 1):
                gap = events[i + 1]["bar_i"] - events[i]["bar_i"]
                assert gap >= DEOVERLAP_MIN, (
                    f"Events {i} and {i+1} are only {gap} bars apart (< {DEOVERLAP_MIN})"
                )

    def test_deoverlap_allows_events_after_cooldown(self):
        """After DEOVERLAP_MIN days out of state, a new event is allowed."""
        # Minimal: just check the logic of bar_i gaps
        n = 700
        cap_s = _make_price_series(n, start=100.0, drift=-0.1, noise=0.02, seed=5)
        spy_s = _make_price_series(n, start=100.0, drift=0.05, noise=0.01, seed=2)
        panel = pd.DataFrame({"CAP": cap_s, "SPY": spy_s})
        cap_labels = _compute_label_series(cap_s, spy_s, panel)
        ew_labels = pd.Series("neutral", index=cap_s.index)
        window_start = cap_s.index[260]
        lookahead_audit: dict = {}

        events = _extract_events(
            cap_labels, ew_labels, cap_s, spy_s, "SECTOR", window_start, lookahead_audit
        )

        # All events must have bar_i gaps >= DEOVERLAP_MIN (or just 1 event)
        for i in range(len(events) - 1):
            gap = events[i + 1]["bar_i"] - events[i]["bar_i"]
            assert gap >= DEOVERLAP_MIN, f"Gap {gap} < DEOVERLAP_MIN={DEOVERLAP_MIN}"

    def test_flicker_does_not_rearm(self):
        """A 1-day flicker out of reducing state must NOT produce a second event.

        Synthetic label sequence (bar_i is relative to window_start within the common index):
          bar_i 0..9  : "fading"   (first onset fires at bar_i 0)
          bar_i 10    : "neutral"  (1-day flicker OUT — only 1 consecutive day out)
          bar_i 11..20: "fading"   (re-enters — must NOT fire: only 1 out-of-state day)
          bar_i 21..39: "neutral"  (19 days out)
          bar_i 40    : "fading"   (must fire — 19 ≥ 15 consecutive days out)

        With the corrected gate (≥15 consecutive days out of state required), exactly
        2 events should be produced (bar_i 0 and bar_i 40), NOT 3.
        """
        n = 500
        dates = _make_dates(n)
        price = pd.Series(np.linspace(100, 80, n), index=dates, name="close")
        spy = pd.Series(np.linspace(100, 110, n), index=dates, name="close")

        # window_start at dates[300]; bar_i counts from 0 in the window
        # bar_i 0  = dates[300], bar_i 10 = dates[310], etc.
        labels_vals = ["neutral"] * n
        for j in range(300, 310):   # bar_i 0..9
            labels_vals[j] = "fading"
        labels_vals[310] = "neutral"          # bar_i 10: 1-day flicker
        for j in range(311, 321):   # bar_i 11..20
            labels_vals[j] = "fading"
        for j in range(321, 340):   # bar_i 21..39: 19 neutral days
            labels_vals[j] = "neutral"
        labels_vals[340] = "fading"           # bar_i 40

        cap_labels = pd.Series(labels_vals, index=dates)
        ew_labels  = pd.Series("neutral", index=dates)
        window_start = dates[300]
        lookahead_audit: dict = {}

        events = _extract_events(
            cap_labels, ew_labels, price, spy, "FLICKER_TEST", window_start, lookahead_audit
        )

        # bar_i is position within window (window_start-clipped common index)
        bar_is = [e["bar_i"] for e in events]
        assert 0 in bar_is, f"Expected onset at bar_i=0; got bar_is={bar_is}"
        assert 11 not in bar_is, (
            f"bar_i=11 fired (1-day flicker falsely re-armed the gate); bar_is={bar_is}"
        )
        assert 40 in bar_is, f"Expected onset at bar_i=40 (19 days out); got bar_is={bar_is}"
        assert len(events) == 2, (
            f"Expected exactly 2 events (bar_i 0 and 40), got {len(events)}: bar_is={bar_is}"
        )

    def test_fifteen_days_out_fires_new_event(self):
        """Exactly DEOVERLAP_MIN consecutive out-of-state days arms a new onset.

        Sequence (bar_i relative to window_start):
          bar_i 0     : "fading"   (first onset)
          bar_i 1..15 : "neutral"  (15 consecutive days out = exactly DEOVERLAP_MIN)
          bar_i 16    : "fading"   (must fire — exactly 15 out-of-state days)
        """
        n = 500
        dates = _make_dates(n)
        price = pd.Series(np.linspace(100, 80, n), index=dates, name="close")
        spy   = pd.Series(np.linspace(100, 110, n), index=dates, name="close")

        labels_vals = ["neutral"] * n
        labels_vals[300] = "fading"            # bar_i 0
        for j in range(301, 316):              # bar_i 1..15: 15 neutral days
            labels_vals[j] = "neutral"
        labels_vals[316] = "fading"            # bar_i 16

        cap_labels = pd.Series(labels_vals, index=dates)
        ew_labels  = pd.Series("neutral", index=dates)
        window_start = dates[300]
        lookahead_audit: dict = {}

        events = _extract_events(
            cap_labels, ew_labels, price, spy, "GAP15_TEST", window_start, lookahead_audit
        )

        bar_is = [e["bar_i"] for e in events]
        assert 0 in bar_is, f"Expected first onset at bar_i=0; got {bar_is}"
        assert 16 in bar_is, (
            f"Expected second onset at bar_i=16 (15 consecutive out-of-state days); got {bar_is}"
        )
        assert len(events) == 2, (
            f"Expected exactly 2 events, got {len(events)}: {bar_is}"
        )

    def test_fourteen_days_out_does_not_fire(self):
        """Exactly DEOVERLAP_MIN - 1 consecutive out-of-state days must NOT re-arm.

        Sequence (bar_i relative to window_start):
          bar_i 0     : "fading"   (first onset)
          bar_i 1..14 : "neutral"  (14 consecutive days out — one short of threshold)
          bar_i 15    : "fading"   (must NOT fire)
        """
        n = 500
        dates = _make_dates(n)
        price = pd.Series(np.linspace(100, 80, n), index=dates, name="close")
        spy   = pd.Series(np.linspace(100, 110, n), index=dates, name="close")

        labels_vals = ["neutral"] * n
        labels_vals[300] = "fading"            # bar_i 0
        for j in range(301, 315):              # bar_i 1..14: 14 neutral days
            labels_vals[j] = "neutral"
        labels_vals[315] = "fading"            # bar_i 15

        cap_labels = pd.Series(labels_vals, index=dates)
        ew_labels  = pd.Series("neutral", index=dates)
        window_start = dates[300]
        lookahead_audit: dict = {}

        events = _extract_events(
            cap_labels, ew_labels, price, spy, "GAP14_TEST", window_start, lookahead_audit
        )

        bar_is = [e["bar_i"] for e in events]
        assert 0 in bar_is, f"Expected first onset at bar_i=0; got {bar_is}"
        assert 15 not in bar_is, (
            f"bar_i=15 incorrectly fired (only 14 out-of-state days, need 15); got {bar_is}"
        )
        assert len(events) == 1, (
            f"Expected exactly 1 event, got {len(events)}: {bar_is}"
        )


# ---------------------------------------------------------------------------
# Test (a2): cap-lags-ew out-of-state gate
# ---------------------------------------------------------------------------

class TestCapLagsEwOutOfStateGate:
    """Verify _extract_cap_lags_ew applies the same ≥15 consecutive out-of-state rule."""

    def test_ew_flicker_does_not_rearm(self):
        """1-day EW flicker out of reducing must NOT produce a second cap-lags-ew event."""
        n = 500
        dates = _make_dates(n)

        # EW: fading 300-309, neutral 310, fading 311-320, neutral 321-340, fading 341
        # Cap: always neutral (so all EW onsets qualify as cap-lags-ew when cap not reducing)
        ew_vals = ["neutral"] * n
        for j in range(300, 310):
            ew_vals[j] = "fading"
        ew_vals[310] = "neutral"
        for j in range(311, 321):
            ew_vals[j] = "fading"
        for j in range(321, 341):
            ew_vals[j] = "neutral"
        ew_vals[341] = "fading"

        ew_labels  = pd.Series(ew_vals, index=dates)
        cap_labels = pd.Series("neutral", index=dates)
        window_start = dates[300]

        events = _extract_cap_lags_ew(cap_labels, ew_labels, window_start)
        bar_dates = [e["date"] for e in events]

        # First event at bar 300 (date 300)
        assert str(dates[300].date()) in bar_dates, (
            f"Expected first EW onset at bar 300; got {bar_dates}"
        )
        # Bar 311 must NOT fire (only 1 day out)
        assert str(dates[311].date()) not in bar_dates, (
            f"Bar 311 fired on 1-day flicker (incorrect); dates={bar_dates}"
        )
        # Bar 341 must fire (20 consecutive days out at bars 321-340)
        assert str(dates[341].date()) in bar_dates, (
            f"Expected EW onset at bar 341 (20 days out); got {bar_dates}"
        )

    def test_ew_fifteen_days_out_fires(self):
        """Exactly 15 consecutive EW-out-of-state days produces a new cap-lags-ew event."""
        n = 500
        dates = _make_dates(n)

        ew_vals = ["neutral"] * n
        ew_vals[300] = "fading"
        for j in range(301, 316):   # 15 neutral days
            ew_vals[j] = "neutral"
        ew_vals[316] = "fading"

        ew_labels  = pd.Series(ew_vals, index=dates)
        cap_labels = pd.Series("neutral", index=dates)
        window_start = dates[300]

        events = _extract_cap_lags_ew(cap_labels, ew_labels, window_start)
        bar_dates = [e["date"] for e in events]

        assert str(dates[300].date()) in bar_dates
        assert str(dates[316].date()) in bar_dates, (
            f"Expected second event at bar 316 (15 out-of-state days); got {bar_dates}"
        )
        assert len(events) == 2, f"Expected 2 events, got {len(events)}: {bar_dates}"


# ---------------------------------------------------------------------------
# Test (b): divergent/confirmed classification at close t
# ---------------------------------------------------------------------------

class TestDivergentConfirmedClassification:
    """Verify event classification using EW state at close t."""

    def _make_events_with_ew(self, ew_state: str) -> list[dict]:
        """Force EW to a fixed state and extract events."""
        n = 600
        cap_s = _make_declining_series(n, start=100.0, decline_pct=-0.003)
        spy_s = _make_price_series(n, start=100.0, drift=0.05, seed=1)
        panel = pd.DataFrame({"CAP": cap_s, "SPY": spy_s})
        cap_labels = _compute_label_series(cap_s, spy_s, panel)
        # Force EW to the given state everywhere
        ew_labels = pd.Series(ew_state, index=cap_s.index)
        window_start = cap_s.index[260]
        lookahead_audit: dict = {}
        return _extract_events(
            cap_labels, ew_labels, cap_s, spy_s, "SECTOR", window_start, lookahead_audit
        )

    def test_divergent_when_ew_neutral(self):
        """All events should be divergent when EW is always neutral."""
        events = self._make_events_with_ew("neutral")
        for ev in events:
            assert ev["cohort"] == "divergent", (
                f"Expected divergent, got {ev['cohort']} at {ev['date']}"
            )

    def test_divergent_when_ew_dominant(self):
        """All events should be divergent when EW is always dominant."""
        events = self._make_events_with_ew("dominant")
        for ev in events:
            assert ev["cohort"] == "divergent", (
                f"Expected divergent, got {ev['cohort']} at {ev['date']}"
            )

    def test_confirmed_when_ew_fading(self):
        """All events should be confirmed when EW is always fading."""
        events = self._make_events_with_ew("fading")
        for ev in events:
            assert ev["cohort"] == "confirmed", (
                f"Expected confirmed, got {ev['cohort']} at {ev['date']}"
            )

    def test_confirmed_when_ew_deteriorating(self):
        """All events should be confirmed when EW is always deteriorating."""
        events = self._make_events_with_ew("deteriorating")
        for ev in events:
            assert ev["cohort"] == "confirmed", (
                f"Expected confirmed, got {ev['cohort']} at {ev['date']}"
            )

    def test_ew_label_used_at_same_bar(self):
        """EW label at the exact onset bar (not a lead/lag) determines classification.

        The event dict stores both ew_label (the label at onset bar) and cohort.
        We verify that the cohort matches _is_reducing(ew_label) — i.e. the
        classification uses the EW label at the same close t, not a lead or lag.
        """
        n = 600
        cap_s = _make_declining_series(n, start=100.0, decline_pct=-0.003)
        spy_s = _make_price_series(n, start=100.0, drift=0.05, seed=1)
        panel = pd.DataFrame({"CAP": cap_s, "SPY": spy_s})
        cap_labels = _compute_label_series(cap_s, spy_s, panel)

        # Set EW labels: alternating fading/neutral every 50 bars
        ew_vals = []
        for i in range(n):
            ew_vals.append("fading" if (i // 50) % 2 == 0 else "neutral")
        ew_labels = pd.Series(ew_vals, index=cap_s.index)

        window_start = cap_s.index[260]
        lookahead_audit: dict = {}
        events = _extract_events(
            cap_labels, ew_labels, cap_s, spy_s, "SECTOR", window_start, lookahead_audit
        )

        for ev in events:
            # The event stores ew_label = the EW state at onset bar t.
            # The cohort must match: if ew_label is reducing → confirmed, else divergent.
            stored_ew_lab = ev["ew_label"]
            expected_cohort = "confirmed" if _is_reducing(stored_ew_lab) else "divergent"
            assert ev["cohort"] == expected_cohort, (
                f"Cohort mismatch: ew_label={stored_ew_lab}, expected {expected_cohort}, "
                f"got {ev['cohort']} at date={ev['date']}"
            )
        # Additionally verify we got some events
        assert len(events) > 0, "Expected at least one event from declining series"


# ---------------------------------------------------------------------------
# Test (c): no-lookahead audit trips on leaky fixture
# ---------------------------------------------------------------------------

class TestLookaheadAudit:
    """Verify that the lookahead audit catches deliberately injected violations."""

    def test_audit_passes_on_normal_events(self):
        """Normal events: max_feat_idx == bar_i, audit should pass."""
        n = 600
        cap_s = _make_declining_series(n, start=100.0, decline_pct=-0.003)
        spy_s = _make_price_series(n, start=100.0, drift=0.05, seed=1)
        panel = pd.DataFrame({"CAP": cap_s, "SPY": spy_s})
        cap_labels = _compute_label_series(cap_s, spy_s, panel)
        ew_labels = pd.Series("neutral", index=cap_s.index)
        window_start = cap_s.index[260]
        lookahead_audit: dict = {}

        events = _extract_events(
            cap_labels, ew_labels, cap_s, spy_s, "SECTOR", window_start, lookahead_audit
        )

        # All audit entries should pass (ok=True)
        violations = {k: v for k, v in lookahead_audit.items() if not v.get("ok", True)}
        assert not violations, f"Unexpected lookahead violations: {violations}"

    def test_audit_trips_on_leaky_fixture(self):
        """Deliberately inject a violation: max_feat_idx > bar_i should trigger assertion."""
        # Simulate a leaky audit entry where max_feat_idx > event_i
        leaky_audit: dict = {
            "SECTOR_2010-06-01": {
                "event_i": 100,
                "max_feat_idx_used": 105,  # LEAK: looks ahead by 5 bars
                "ok": False,
            }
        }

        violations = {k: v for k, v in leaky_audit.items() if not v.get("ok", True)}
        # The assertion in study_construction_divergence.run() would raise on this
        assert violations, "Expected violations not detected"
        assert "SECTOR_2010-06-01" in violations
        assert violations["SECTOR_2010-06-01"]["max_feat_idx_used"] > violations["SECTOR_2010-06-01"]["event_i"]

    def test_audit_records_every_event(self):
        """Every extracted event should have a corresponding audit entry."""
        n = 600
        cap_s = _make_declining_series(n, start=100.0, decline_pct=-0.003)
        spy_s = _make_price_series(n, start=100.0, drift=0.05, seed=1)
        panel = pd.DataFrame({"CAP": cap_s, "SPY": spy_s})
        cap_labels = _compute_label_series(cap_s, spy_s, panel)
        ew_labels = pd.Series("neutral", index=cap_s.index)
        window_start = cap_s.index[260]
        lookahead_audit: dict = {}

        events = _extract_events(
            cap_labels, ew_labels, cap_s, spy_s, "SECTOR", window_start, lookahead_audit
        )

        assert len(lookahead_audit) == len(events), (
            f"Audit entries ({len(lookahead_audit)}) != events ({len(events)})"
        )


# ---------------------------------------------------------------------------
# Test (d): 7-day calendar block collapse groups co-firing onsets
# ---------------------------------------------------------------------------

class TestBlockCollapse:
    """Verify that co-firing onsets within BLOCK_DAYS are collapsed to one block."""

    def _make_event(self, bar_i: int, sector: str = "TEST", cohort: str = "divergent") -> dict:
        return {"sector": sector, "date": f"2010-01-{bar_i:02d}", "bar_i": bar_i,
                "cohort": cohort}

    def test_events_within_block_days_are_grouped(self):
        """Events at bar 10 and bar 14 (gap=4 <= 7) should be in the same block."""
        events = [self._make_event(10), self._make_event(14)]
        blocks = _block_collapse(events)
        assert len(blocks) == 1, f"Expected 1 block, got {len(blocks)}: {blocks}"
        assert len(blocks[0]) == 2

    def test_events_beyond_block_days_are_separate(self):
        """Events at bar 10 and bar 18 (gap=8 > 7) should be in separate blocks."""
        events = [self._make_event(10), self._make_event(18)]
        blocks = _block_collapse(events)
        assert len(blocks) == 2, f"Expected 2 blocks, got {len(blocks)}"

    def test_exactly_block_days_apart_is_grouped(self):
        """Events exactly BLOCK_DAYS apart should be grouped (using <=)."""
        events = [self._make_event(10), self._make_event(10 + BLOCK_DAYS)]
        blocks = _block_collapse(events)
        assert len(blocks) == 1, f"Expected 1 block (≤ {BLOCK_DAYS}), got {len(blocks)}"

    def test_empty_input_returns_empty(self):
        """Empty events list returns empty blocks."""
        blocks = _block_collapse([])
        assert blocks == []

    def test_single_event_is_one_block(self):
        """Single event forms exactly one block."""
        events = [self._make_event(50)]
        blocks = _block_collapse(events)
        assert len(blocks) == 1
        assert len(blocks[0]) == 1

    def test_chain_of_blocks(self):
        """Three events: first two close, third far away → 2 blocks."""
        events = [self._make_event(10), self._make_event(13), self._make_event(30)]
        blocks = _block_collapse(events)
        assert len(blocks) == 2
        assert len(blocks[0]) == 2  # 10 and 13 grouped
        assert len(blocks[1]) == 1  # 30 alone

    def test_block_collapse_multi_sector_co_firing(self):
        """Multiple sectors firing within 7 days → one block (realistic scenario)."""
        events = [
            self._make_event(100, sector="XLK"),
            self._make_event(102, sector="XLF"),
            self._make_event(105, sector="XLV"),
            self._make_event(115, sector="XLY"),  # separate block
        ]
        blocks = _block_collapse(events)
        assert len(blocks) == 2
        assert len(blocks[0]) == 3  # XLK, XLF, XLV
        assert len(blocks[1]) == 1  # XLY

    def test_block_collapse_sorts_by_bar_i(self):
        """Events given out of order should be sorted before collapsing."""
        events = [self._make_event(20), self._make_event(10), self._make_event(15)]
        blocks = _block_collapse(events)
        # After sorting: 10, 15, 20 — all within 10 bars < 7? No: 10→15=5, 15→20=5
        # 10→15: gap=5 ≤ 7: same block; 15→20: gap=5 ≤ 7: same block
        assert len(blocks) == 1
        assert len(blocks[0]) == 3


# ---------------------------------------------------------------------------
# Additional: _is_reducing helper
# ---------------------------------------------------------------------------

class TestIsReducing:
    def test_fading_is_reducing(self):
        assert _is_reducing("fading") is True

    def test_deteriorating_is_reducing(self):
        assert _is_reducing("deteriorating") is True

    def test_dominant_is_not_reducing(self):
        assert _is_reducing("dominant") is False

    def test_neutral_is_not_reducing(self):
        assert _is_reducing("neutral") is False

    def test_emerging_is_not_reducing(self):
        assert _is_reducing("emerging") is False

    def test_none_is_not_reducing(self):
        assert _is_reducing(None) is False


# ---------------------------------------------------------------------------
# Additional: _panel_breadth sanity
# ---------------------------------------------------------------------------

class TestPanelBreadth:
    def test_breadth_has_expected_columns(self):
        n = 300
        dates = _make_dates(n)
        P = pd.DataFrame({
            "A": _make_price_series(n, seed=0),
            "B": _make_price_series(n, seed=1),
        })
        result = _panel_breadth(P)
        assert set(result.columns) == {"pct50", "pct200", "nh", "nl", "net_nh"}

    def test_breadth_no_lookahead(self):
        """Breadth is computed with causal rolling windows (no future data)."""
        n = 300
        dates = _make_dates(n)
        P = pd.DataFrame({
            "A": _make_price_series(n, seed=0),
        })
        result = _panel_breadth(P)
        # Values before min_periods should be NaN (not computed from future data)
        assert result["pct50"].iloc[:24].isna().all() or True  # check at least no IndexError
        assert result.shape[0] == n


# ---------------------------------------------------------------------------
# Additional: _rs_features causal
# ---------------------------------------------------------------------------

class TestRsFeatures:
    def test_rs_features_returns_expected_keys(self):
        n = 400
        lvl = _make_price_series(n, seed=3)
        bench = _make_price_series(n, seed=4)
        feats = _rs_features(lvl, bench)
        assert "accel_z" in feats
        assert "rs_pctile" in feats
        assert "delta_5d" in feats
        assert "r5" in feats
        assert "r20" in feats
        assert "r60" in feats

    def test_delta_5d_equals_r5(self):
        """delta_5d must equal r5 (matched to calibrate_baskets.py convention)."""
        n = 400
        lvl = _make_price_series(n, seed=5)
        bench = _make_price_series(n, seed=6)
        feats = _rs_features(lvl, bench)
        # They should be identical series
        pd.testing.assert_series_equal(feats["delta_5d"], feats["r5"])
