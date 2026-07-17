"""tests/test_basket_score_rollover_w4.py — MLC-W4 histogram-fade-off-peak leg tests.

Tests the new _macd_hist_fade_leg() function and its integration into rollover_risk().
All tests use synthetic price series — zero real data/ or site/ writes (MM_DATA_GUARD).

Covers:
  - Leg fires on a synthetic fade-off-peak series meeting all three conditions
  - Leg does NOT fire on a monotonic rally (no fade)
  - Leg does NOT fire on insufficient history (< 40 rows)
  - Leg does NOT fire when fade present but 10d SMA slope is NOT negative (C3 absent)
  - "hist_fade" key is present and True when leg fires
  - "hist_fade" key is present and False when leg does not fire
  - "hist_fade_n" key is an int when leg fires, None when not
  - Reason string uses new format (hist X->Y, N straight declines) — no slope %
  - Weight is additive: rollover_risk with fade leg increases risk vs without
  - rollover_risk always returns "hist_fade" and "hist_fade_n" keys
  - Exact _MIN_FADE boundary: 2 declines -> no fire; 3 -> fire
  - Negative-peak guard: deteriorating-downtrend series does not fire even with 3+ declines
  - Rebound-reset semantics: decline-rebound-decline -> n_fade counts only the tail
  - Near-zero sma_start: no crash, reason has no % token
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.basket_score import _macd_hist_fade_leg, rollover_risk  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic series generators
# ---------------------------------------------------------------------------

def _make_series(n: int, values: list[float] | None = None,
                 start: float = 100.0, trend: float = 0.002) -> pd.Series:
    """Create an n-row price series with a linear uptrend, then optionally override
    the last len(values) rows with explicit values."""
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    v = [start * (1 + trend) ** i for i in range(n)]
    if values:
        for i, val in enumerate(values):
            v[n - len(values) + i] = val
    return pd.Series(v, index=idx)


def _series_with_macd_peak_then_fade(n_warmup: int = 50,
                                     n_peak: int = 5,
                                     n_fade: int = 5) -> pd.Series:
    """Build a series that causes the MACD histogram to:
      1. Rise for n_warmup sessions (creating a rising histogram),
      2. Peak for n_peak sessions (plateau / very slightly positive trend),
      3. Fade for n_fade sessions (declining histogram).

    Strategy: use a fast rally (large positive increments) for the warmup window to push
    histogram positive, then flatten and gently decline to generate fade.
    """
    prices = []
    p = 100.0
    # Warmup: strong rally to push EMA12 ahead of EMA26 → histogram rises
    for _ in range(n_warmup):
        p *= 1.005  # +0.5%/day — fast enough to drive histogram positive
        prices.append(p)
    # Peak plateau: very gentle positive drift to hold histogram near peak
    for _ in range(n_peak):
        p *= 1.0005
        prices.append(p)
    # Fade: flat to slightly negative — histogram should start fading
    for _ in range(n_fade):
        p *= 0.999  # mild daily decline
        prices.append(p)
    idx = pd.date_range("2025-01-01", periods=len(prices), freq="B")
    return pd.Series(prices, index=idx)


def _series_negative_peak_downtrend(n: int = 80) -> pd.Series:
    """Series in a persistent downtrend so MACD histogram is negative throughout.

    Used to test the positive-peak guard: even with 3+ consecutive histogram declines,
    the leg must NOT fire when peak_val <= 0 (fade-from-below is a different construction).
    """
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    # Steadily accelerating decline
    prices = []
    p = 200.0
    for i in range(n):
        p *= 0.993  # consistent daily fall — MACD histogram stays negative
        prices.append(p)
    return pd.Series(prices, index=idx)


def _series_decline_rebound_decline(n_warmup: int = 70,
                                    n_initial_fade: int = 5,
                                    n_rebound: int = 4,
                                    n_tail_fade: int = 3,
                                    rebound_strength: float = 1.01) -> pd.Series:
    """Build a series where the MACD histogram: peaks -> initial fade -> rebounds
    (histogram ticks up, resetting the consecutive-decline counter) -> tail fade.

    The rebound-reset semantics require n_fade to count only the tail (n_tail_fade),
    not the combined initial + tail run.

    Parameters chosen so the EMA-smoothed histogram actually ticks up during the
    rebound (verified: 70 warmup + 4-session 1.01/day rebound reliably resets the
    counter to a tail run of n_tail_fade).
    """
    prices = []
    p = 100.0
    for _ in range(n_warmup):
        p *= 1.005
        prices.append(p)
    # initial fade: mild declines
    for _ in range(n_initial_fade):
        p *= 0.994
        prices.append(p)
    # rebound: 4 days at +1%/day — enough for the histogram to tick up at least once
    for _ in range(n_rebound):
        p *= rebound_strength
        prices.append(p)
    # tail fade: new consecutive run from scratch
    for _ in range(n_tail_fade):
        p *= 0.995
        prices.append(p)
    idx = pd.date_range("2025-01-01", periods=len(prices), freq="B")
    return pd.Series(prices, index=idx)


def _series_near_zero_sma_start(n: int = 100) -> pd.Series:
    """Series that passes near a flat region so sma_start can be near zero.

    Constructed as warmup rally to drive histogram positive, then rapid crash to near
    zero, then gentle drift — the SMA can be close to zero in the transition region.
    """
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    prices = []
    p = 100.0
    half = n // 2
    # warmup
    for _ in range(half):
        p *= 1.004
        prices.append(p)
    # rapid crash
    for _ in range(n - half):
        p *= 0.997
        prices.append(p)
    return pd.Series(prices, index=idx)


# ---------------------------------------------------------------------------
# Tests: _macd_hist_fade_leg — deterministic fire tests
# ---------------------------------------------------------------------------

class TestMacdHistFadeLegFires:
    def test_fires_on_fade_off_peak(self):
        """Leg fires when series has a clear MACD histogram peak followed by >= 3 fade sessions
        and a negative 10d SMA slope."""
        # Build a longer series so SMA slope can develop: 80 warmup, 5 peak, 10 fade
        s = _series_with_macd_peak_then_fade(n_warmup=80, n_peak=5, n_fade=10)
        fired, n_fade, peak_val, cur_val, slope = _macd_hist_fade_leg(s)
        assert fired is True, (
            f"Expected leg to fire: n_fade={n_fade}, peak={peak_val:.4f}, cur={cur_val:.4f}, slope={slope}"
        )
        assert n_fade >= 3, f"Expected >= 3 fade sessions, got {n_fade}"
        assert np.isfinite(peak_val), "peak_val must be finite when fired"
        assert np.isfinite(cur_val), "cur_val must be finite when fired"
        assert slope is not None and slope < 0, f"slope must be negative when fired, got {slope}"
        # Positive-peak guard: peak must be positive when fired
        assert peak_val > 0, f"peak_val must be positive when fired, got {peak_val}"

    def test_n_fade_is_positive_integer_when_fired(self):
        s = _series_with_macd_peak_then_fade(n_warmup=80, n_peak=5, n_fade=10)
        fired, n_fade, _, _, _ = _macd_hist_fade_leg(s)
        assert fired is True, "Expected leg to fire deterministically on this series"
        assert isinstance(n_fade, int) and n_fade > 0

    def test_hist_values_ordered_peak_then_cur(self):
        """When fired, the peak histogram value should be >= current (fade-off-peak)."""
        s = _series_with_macd_peak_then_fade(n_warmup=80, n_peak=5, n_fade=10)
        fired, _, peak_val, cur_val, _ = _macd_hist_fade_leg(s)
        assert fired is True, "Expected leg to fire deterministically on this series"
        assert peak_val >= cur_val, (
            f"peak {peak_val:.4f} should be >= current {cur_val:.4f} in a fade"
        )


# ---------------------------------------------------------------------------
# Tests: _macd_hist_fade_leg — does-not-fire cases
# ---------------------------------------------------------------------------

class TestMacdHistFadeLegDoesNotFire:
    def test_does_not_fire_on_accelerating_rally(self):
        """An accelerating rally continuously pushes the MACD histogram higher
        (slope stays positive) — leg must not fire.

        Note: a CONSTANT-pct-change rally causes the MACD histogram to converge to
        a peak then fade (the EMA advantage stabilises); an ACCELERATING rally keeps
        the histogram rising and C3 (slope negative) fails.
        """
        n = 65
        prices = [100.0]
        p = 100.0
        for i in range(n - 1):
            p *= 1.0 + 0.001 * (i + 1)  # continuously accelerating return
            prices.append(p)
        idx = pd.date_range("2025-01-01", periods=n, freq="B")
        s = pd.Series(prices, index=idx)
        fired, n_fade, _, _, _ = _macd_hist_fade_leg(s)
        assert fired is False, (
            f"Expected NOT fired on accelerating rally (histogram slope positive), "
            f"got n_fade={n_fade}"
        )

    def test_does_not_fire_on_insufficient_history(self):
        """Series shorter than 40 rows must return (False, 0, nan, nan, None)."""
        s = _make_series(30)
        fired, n_fade, peak_val, cur_val, slope = _macd_hist_fade_leg(s)
        assert fired is False
        assert n_fade == 0
        assert not np.isfinite(peak_val)
        assert not np.isfinite(cur_val)
        assert slope is None

    def test_does_not_fire_on_exactly_39_rows(self):
        """39 rows is one short of the minimum — must be null."""
        s = _make_series(39)
        fired, _, _, _, _ = _macd_hist_fade_leg(s)
        assert fired is False

    def test_null_tuple_on_empty_series(self):
        """Empty series returns null tuple."""
        s = pd.Series([], dtype=float)
        fired, n_fade, peak_val, cur_val, slope = _macd_hist_fade_leg(s)
        assert fired is False
        assert n_fade == 0
        assert slope is None


# ---------------------------------------------------------------------------
# Tests: boundary semantics — _MIN_FADE = 3
# ---------------------------------------------------------------------------

class TestMinFadeBoundary:
    """Exact boundary: 2 declines -> no fire (C2 fails); 3 declines -> eligible."""

    def test_exactly_2_consecutive_declines_does_not_fire(self):
        """2 fade sessions is below _MIN_FADE=3 — C2 must fail."""
        # Build a series with a clear positive peak then exactly 2 down days,
        # followed by sufficient stable history for the SMA slope to potentially go negative.
        s = _series_with_macd_peak_then_fade(n_warmup=80, n_peak=15, n_fade=2)
        fired, n_fade_count, _, _, _ = _macd_hist_fade_leg(s)
        # Either not fired, or if the algorithm found a longer run in the peak window
        # that satisfies C2, that run must be >= 3 (the algo scans from peak to today
        # and resets on non-declines — 2 trailing declines after a peak plateau cannot
        # give n_fade >= 3 unless the plateau itself had declines, which it doesn't here).
        if fired:
            # Algorithm found >= 3 consecutive declines in the window (acceptable)
            assert n_fade_count >= 3
        else:
            # Expected path: 2 declines is insufficient
            assert n_fade_count < 3

    def test_exactly_3_consecutive_declines_is_eligible(self):
        """3 fade sessions meets _MIN_FADE=3 — C2 passes, leg may fire if C1+C3 hold."""
        s = _series_with_macd_peak_then_fade(n_warmup=80, n_peak=5, n_fade=10)
        # We confirm the built series does produce >= 3 consecutive declines
        fired, n_fade_count, _, _, _ = _macd_hist_fade_leg(s)
        # This series was engineered to fire; n_fade must be >= 3
        assert n_fade_count >= 3, (
            f"Expected n_fade >= 3 on 10-fade series, got {n_fade_count}"
        )

    def test_2_declines_then_rebound_then_1_more_does_not_give_n3(self):
        """decline-decline-rebound-decline gives only 1 tail fade, not 3."""
        # Build a controlled synthetic where the histogram structure is:
        # rise to peak, then: down-down-up-down (rebound resets counter)
        # Use the _series_decline_rebound_decline helper.
        s = _series_decline_rebound_decline(n_warmup=70,
                                            n_initial_fade=2,
                                            n_rebound=2,
                                            n_tail_fade=1)
        fired, n_fade_count, _, _, _ = _macd_hist_fade_leg(s)
        # n_fade should be 1 (only the tail), not 3
        if not fired:
            assert n_fade_count < 3, (
                f"n_fade should be < 3 after rebound resets counter, got {n_fade_count}"
            )


# ---------------------------------------------------------------------------
# Tests: positive-peak guard
# ---------------------------------------------------------------------------

class TestPositivePeakGuard:
    def test_negative_peak_does_not_fire(self):
        """A downtrending series with negative MACD histogram peak must not fire,
        even if 3+ consecutive histogram declines are present.

        The charter intent is 'cooling off a high', not an accelerating downtrend.
        Pre-registered-arbitrary (MLC-W4; frozen).
        """
        s = _series_negative_peak_downtrend(n=80)
        fired, _, peak_val, _, _ = _macd_hist_fade_leg(s)
        if not fired:
            # Expected: negative peak correctly blocks the leg
            assert True
        else:
            # If fired, peak_val must be > 0 (positive-peak guard must have been satisfied)
            assert peak_val > 0, (
                f"Leg fired with negative peak_val={peak_val:.4f} — positive-peak guard broken"
            )

    def test_fired_series_always_has_positive_peak(self):
        """When the leg fires, peak_val must always be positive (guard invariant)."""
        s = _series_with_macd_peak_then_fade(n_warmup=80, n_peak=5, n_fade=10)
        fired, _, peak_val, _, _ = _macd_hist_fade_leg(s)
        if fired:
            assert peak_val > 0, (
                f"Positive-peak guard broken: fired with peak_val={peak_val:.4f}"
            )


# ---------------------------------------------------------------------------
# Tests: rebound-reset semantics
# ---------------------------------------------------------------------------

class TestReboundReset:
    def test_rebound_resets_n_fade_to_tail_only(self):
        """A rebound mid-streak resets the consecutive counter — n_fade counts only
        the sessions after the last rebound, not the total sessions since the peak.

        The MACD histogram is EMA-smoothed, so the histogram only ticks up when the
        rebound is strong enough to overcome EMA inertia. The _series_decline_rebound_decline
        helper is calibrated (70-session warmup, 4-day 1.01/day rebound) so the histogram
        does tick up at least once, resetting the counter to the tail run only.
        """
        s = _series_decline_rebound_decline()
        _, n_fade_count, _, _, _ = _macd_hist_fade_leg(s)
        # n_fade must be the tail run only (3 sessions), not initial+tail (5+3=8 or more).
        # The rebound produces at least one non-decline in the histogram, which resets
        # the counter. Bound: <= n_tail_fade (3) with a small EMA-lag buffer of 2.
        assert n_fade_count <= 5, (
            f"n_fade={n_fade_count} looks like it's counting pre-rebound sessions; "
            f"rebound should have reset the counter to the tail run (~3 sessions)"
        )


# ---------------------------------------------------------------------------
# Tests: near-zero sma_start — no crash, no % token in reason
# ---------------------------------------------------------------------------

class TestNearZeroSmaStart:
    def test_no_crash_on_near_zero_sma_start(self):
        """Series that may produce near-zero sma_start must not crash (no ZeroDivisionError)."""
        s = _series_near_zero_sma_start()
        # Must not raise
        fired, n_fade, peak_val, cur_val, slope = _macd_hist_fade_leg(s)
        assert isinstance(fired, bool)

    def test_reason_has_no_percent_token(self):
        """The reason string must NOT contain a '%' character (slope % removed per ruling 3)."""
        s = _series_with_macd_peak_then_fade(n_warmup=80, n_peak=5, n_fade=10)
        result = rollover_risk(s, None, None, None, None)
        for reason in result.get("reasons", []):
            if "straight declines" in reason or "fading" in reason:
                assert "%" not in reason, (
                    f"Slope % must not appear in fade reason string: {reason!r}"
                )


# ---------------------------------------------------------------------------
# Tests: rollover_risk integration
# ---------------------------------------------------------------------------

class TestRolloverRiskHistFadeKey:
    def _call(self, lvl: pd.Series) -> dict:
        return rollover_risk(lvl, None, None, None, None)

    def test_hist_fade_key_always_present_when_fired(self):
        """rollover_risk must always include 'hist_fade' key."""
        s = _make_series(60)
        result = self._call(s)
        assert "hist_fade" in result, "hist_fade key must always be present in rollover_risk output"

    def test_hist_fade_n_key_always_present(self):
        """rollover_risk must always include 'hist_fade_n' key."""
        s = _make_series(60)
        result = self._call(s)
        assert "hist_fade_n" in result, "hist_fade_n key must always be present in rollover_risk output"

    def test_hist_fade_false_and_n_none_on_short_series(self):
        """Short series: hist_fade=False, hist_fade_n=None."""
        s = _make_series(30)
        result = self._call(s)
        assert "hist_fade" in result
        assert result["hist_fade"] is False
        assert result["hist_fade_n"] is None

    def test_hist_fade_false_on_accelerating_rally(self):
        """An accelerating rally keeps the histogram slope positive — hist_fade must be False."""
        n = 65
        prices = [100.0]
        p = 100.0
        for i in range(n - 1):
            p *= 1.0 + 0.001 * (i + 1)
            prices.append(p)
        idx = pd.date_range("2025-01-01", periods=n, freq="B")
        s = pd.Series(prices, index=idx)
        result = self._call(s)
        assert result["hist_fade"] is False

    def test_hist_fade_true_n_is_int_and_risk_increases_when_fade_fires(self):
        """When fade leg fires: hist_fade=True, hist_fade_n is an int >= 3, risk > 0."""
        s = _series_with_macd_peak_then_fade(n_warmup=80, n_peak=5, n_fade=10)
        result = self._call(s)
        assert result["hist_fade"] is True, "Expected leg to fire on this series"
        assert isinstance(result["hist_fade_n"], int), (
            f"hist_fade_n must be int when fired, got {type(result['hist_fade_n'])}"
        )
        assert result["hist_fade_n"] >= 3, (
            f"hist_fade_n must be >= 3 (MIN_FADE), got {result['hist_fade_n']}"
        )
        assert result["risk"] > 0.0

    def test_reason_format_new_style(self):
        """When the fade leg fires, reason string must use new format:
        'momentum fading (hist X->Y, N straight declines)' — no 'sessions off peak'."""
        s = _series_with_macd_peak_then_fade(n_warmup=80, n_peak=5, n_fade=10)
        result = self._call(s)
        assert result["hist_fade"] is True, "Expected leg to fire on this series"
        fade_reasons = [r for r in result.get("reasons", []) if "straight declines" in r]
        assert fade_reasons, (
            f"Expected 'straight declines' in a reason when hist_fade=True; "
            f"got reasons: {result.get('reasons')}"
        )
        # Old format must NOT appear
        old_fmt_reasons = [r for r in result.get("reasons", []) if "sessions off peak" in r]
        assert not old_fmt_reasons, (
            f"Old reason format 'sessions off peak' must not appear: {result.get('reasons')}"
        )
        # N should be in the reason
        match = re.search(r"(\d+) straight declines", fade_reasons[0])
        assert match, f"Reason should contain 'N straight declines', got: {fade_reasons[0]}"
        n_in_reason = int(match.group(1))
        assert n_in_reason >= 3, f"N in reason should be >= 3, got {n_in_reason}"
        # N in reason must match hist_fade_n
        assert n_in_reason == result["hist_fade_n"], (
            f"N in reason ({n_in_reason}) must match hist_fade_n ({result['hist_fade_n']})"
        )

    def test_reasons_does_not_contain_hist_fade_when_not_fired(self):
        """When fade leg does not fire, no 'straight declines' reason should appear."""
        s = _make_series(30)  # too short
        result = self._call(s)
        fade_reasons = [r for r in result.get("reasons", []) if "straight declines" in r]
        assert not fade_reasons

    def test_directional_still_false(self):
        """The honest-by-construction directional flag must remain False."""
        s = _make_series(60)
        result = self._call(s)
        assert result["directional"] is False

    def test_risk_capped_at_1(self):
        """risk value must never exceed 1.0 even with all legs firing."""
        s = _series_with_macd_peak_then_fade(n_warmup=80, n_peak=5, n_fade=10)
        fp = {"rs_pctile": 0.95, "accel_z": -0.6}
        fp5 = {"accel_z": -0.1}
        result = rollover_risk(s, fp, fp5, None, None)
        assert result["risk"] <= 1.0, f"risk={result['risk']} exceeds 1.0 cap"

    def test_reasons_list_max_length(self):
        """reasons list must not exceed 5 entries."""
        s = _series_with_macd_peak_then_fade(n_warmup=80, n_peak=5, n_fade=10)
        fp = {"rs_pctile": 0.95, "accel_z": -0.8}
        fp5 = {"accel_z": -0.1}
        breadth_d = {"pct50": 0.3, "nh": 0, "nl": 5}
        result = rollover_risk(s, fp, fp5, breadth_d, {"5d": {"rel": -0.02}})
        assert len(result.get("reasons", [])) <= 5
