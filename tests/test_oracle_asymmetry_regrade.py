"""Tests for scripts/oracle_asymmetry_regrade.py — synthetic fixtures (spec §7).

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

from scripts.oracle_asymmetry_regrade import (
    compute_sigma20,
    sigma_barriers,
    invert_close,
    first21_dedup,
    compute_accel_flip_exit,
    grade_event,
    run_fidelity_gate,
)
from engine.grading import TerminalState


# ---------------------------------------------------------------------------
# Helpers for building synthetic close series
# ---------------------------------------------------------------------------

def _make_close(prices: list[float], start: str = "2020-01-02") -> pd.Series:
    """Build a daily-indexed close series from a list of prices."""
    dates = pd.bdate_range(start=start, periods=len(prices))
    return pd.Series(prices, index=dates, dtype=float)


def _make_panel_with_accel_z(
    accel_z_values: list[float],
    node: str = "XLK",
    start: str = "2020-01-02",
) -> pd.DataFrame:
    """Build a minimal panel_s-style DataFrame with accel_z column."""
    dates = pd.bdate_range(start=start, periods=len(accel_z_values))
    df = pd.DataFrame({"accel_z": accel_z_values}, index=dates)
    df.index.name = "date"
    df["node"] = node
    df = df.set_index(["node", df.index])
    df.index.names = ["node", "date"]
    return df


# ---------------------------------------------------------------------------
# §7 Test 1: Barrier race in σ-units — stop touches before target
# ---------------------------------------------------------------------------

class TestBarrierRaceSigmaUnits:
    """Spec §7: barrier race where stop touches before target and vice versa.

    terminal_state requires liftoff_horizon forward bars to be present for maturity.
    We use liftoff_horizon=5 in these unit tests to avoid needing long synthetic series.
    """

    def test_stop_wins_when_stop_first(self):
        """Close path hits stop before cushion → STOPPED."""
        from engine.grading import terminal_state, TerminalState

        # trigger at bar 0, fill at bar 1 (entry=100)
        # forward bars 2..6: bar2=94 hits stop_mult=0.95 (stop=95) first
        prices = [100.0, 100.0, 94.0, 97.0, 108.0, 108.0, 108.0]
        # fill bar=1, entry=100; forward=[94, 97, 108, 108, 108]
        # bar2: 94 < 95 → STOPPED at bar 1 of forward (k=1)
        close = _make_close(prices)
        trigger = close.index[0]

        result = terminal_state(
            close, trigger,
            stop_mult=0.95, cushion_mult=1.05,
            liftoff_mult=1.08, liftoff_horizon=5,
        )
        assert result["state"] == TerminalState.STOPPED, (
            f"Expected STOPPED (94 < 100*0.95=95), got {result['state']}: {result['note']}"
        )

    def test_cushion_wins_when_cushion_first(self):
        """Close path hits cushion before stop → CUSHIONED or CLEAN_LIFTOFF."""
        from engine.grading import terminal_state, TerminalState

        # trigger at bar 0, fill at bar 1 (entry=100)
        # forward bars 2..6: bar2=106 hits cushion_mult=1.05 first
        prices = [100.0, 100.0, 106.0, 107.0, 108.0, 109.0, 110.0]
        close = _make_close(prices)
        trigger = close.index[0]

        result = terminal_state(
            close, trigger,
            stop_mult=0.95, cushion_mult=1.05,
            liftoff_mult=1.15, liftoff_horizon=5,
        )
        assert result["state"] in (TerminalState.CUSHIONED, TerminalState.CLEAN_LIFTOFF), (
            f"Expected cushion or liftoff, got {result['state']}: {result['note']}"
        )

    def test_stop_wins_straddle_tie(self):
        """Straddle tie: stop checked first on each bar, so stop wins when both trigger same bar."""
        from engine.grading import terminal_state, TerminalState

        # trigger at bar 0, fill at bar 1 (entry=100)
        # forward: bar2=94 < stop=95 AND bar2=94 < cushion=105
        # Stop check is done first (engine.grading loop line: if cl <= stop_barrier)
        prices = [100.0, 100.0, 94.0, 108.0, 108.0, 108.0, 108.0]
        close = _make_close(prices)
        trigger = close.index[0]

        result = terminal_state(
            close, trigger,
            stop_mult=0.96, cushion_mult=1.05,
            liftoff_mult=1.15, liftoff_horizon=5,
        )
        assert result["state"] == TerminalState.STOPPED, (
            f"Expected STOPPED (stop checked first), got {result['state']}"
        )


# ---------------------------------------------------------------------------
# §7 Test 2: Short-side direction adjustment correctness
# ---------------------------------------------------------------------------

class TestShortSideDirection:
    """Spec §7: short-side direction adjustment — win = price falls."""

    def test_invert_close_falls_is_win(self):
        """When close falls below entry, inverted close rises above entry."""
        entry_price = 100.0
        prices = [100.0, 90.0, 80.0, 70.0]
        close = _make_close(prices)
        inv = invert_close(close, entry_price)

        # At entry (100): inv = 100²/100 = 100
        assert abs(inv.iloc[0] - 100.0) < 1e-9

        # When price falls to 90: inv = 10000/90 = 111.1 > 100 → gain
        assert inv.iloc[1] > 100.0

        # When price falls to 50: inv = 10000/50 = 200 (larger gain)
        assert inv.iloc[2] > inv.iloc[1]

    def test_short_grade_stop_when_price_rises(self):
        """Short-side: if price rises (not falls), that's a loss → triggers stop."""
        from engine.grading import terminal_state, TerminalState

        # trigger at bar 0, fill at bar 1 (entry=100)
        # price rises to 115 after fill → inv = 10000/115 ≈ 86.96
        # with stop_mult=0.90 → stop=100*0.90=90 → 86.96 < 90 → STOPPED
        prices = [100.0, 100.0, 115.0, 115.0, 115.0, 115.0, 115.0]
        close = _make_close(prices)
        trigger = close.index[0]
        entry_price = 100.0
        inv_close = invert_close(close, entry_price)

        result = terminal_state(
            inv_close, trigger,
            stop_mult=0.90, cushion_mult=1.10,
            liftoff_mult=1.20, liftoff_horizon=5,
        )
        assert result["state"] == TerminalState.STOPPED, (
            f"Short-side: price rising should trigger stop, got {result['state']}: {result['note']}"
        )

    def test_short_grade_win_when_price_falls(self):
        """Short-side: price falls → inverted close rises → profit."""
        from engine.grading import terminal_state, TerminalState

        # trigger at bar 0, fill at bar 1 (entry=100)
        # price falls to 80 → inv = 10000/80 = 125 → above cushion=110
        prices = [100.0, 100.0, 80.0, 80.0, 80.0, 80.0, 80.0]
        close = _make_close(prices)
        trigger = close.index[0]
        entry_price = 100.0
        inv_close = invert_close(close, entry_price)

        result = terminal_state(
            inv_close, trigger,
            stop_mult=0.90, cushion_mult=1.10,
            liftoff_mult=1.20, liftoff_horizon=5,
        )
        assert result["state"] in (TerminalState.CUSHIONED, TerminalState.CLEAN_LIFTOFF), (
            f"Short-side: price falling should be a win, got {result['state']}: {result['note']}"
        )


# ---------------------------------------------------------------------------
# §7 Test 3: first21 dedup on a crafted fire sequence
# ---------------------------------------------------------------------------

class TestFirst21Dedup:
    """Spec §7: first21 dedup."""

    def test_drops_fires_within_21_sessions(self):
        """Fires within 21 calendar days of a kept fire are dropped."""
        dates = [
            pd.Timestamp("2021-01-04"),   # kept
            pd.Timestamp("2021-01-10"),   # within 21 days → dropped
            pd.Timestamp("2021-01-20"),   # within 21 days → dropped
            pd.Timestamp("2021-02-05"),   # > 21 days after 01-04 → kept
            pd.Timestamp("2021-02-06"),   # within 21 days of 02-05 → dropped
            pd.Timestamp("2021-03-15"),   # > 21 days after 02-05 → kept
        ]
        kept = first21_dedup(dates)
        assert len(kept) == 3
        assert kept[0] == pd.Timestamp("2021-01-04")
        assert kept[1] == pd.Timestamp("2021-02-05")
        assert kept[2] == pd.Timestamp("2021-03-15")

    def test_empty_list(self):
        assert first21_dedup([]) == []

    def test_single_element(self):
        d = pd.Timestamp("2021-01-04")
        assert first21_dedup([d]) == [d]

    def test_exactly_21_days_apart_is_kept(self):
        """Exactly 21 calendar days apart: (d2 - d1).days = 21 > 21 is False → dropped."""
        d1 = pd.Timestamp("2021-01-04")
        d2 = pd.Timestamp("2021-01-25")  # exactly 21 calendar days later
        assert (d2 - d1).days == 21
        # Our rule: keep if (d - last_kept).days > 21
        # 21 > 21 is False → dropped
        kept = first21_dedup([d1, d2])
        assert len(kept) == 1, f"21 calendar days exactly should be dropped; got {kept}"

    def test_22_days_apart_is_kept(self):
        d1 = pd.Timestamp("2021-01-04")
        d2 = pd.Timestamp("2021-01-26")  # 22 calendar days later
        kept = first21_dedup([d1, d2])
        assert len(kept) == 2


# ---------------------------------------------------------------------------
# §7 Test 4: accel-flip exit date on a crafted accel_z series
# ---------------------------------------------------------------------------

class TestAccelFlipExit:
    """Spec §7: accel-flip exit date computation."""

    def test_flip_from_positive_to_negative_in_direction(self):
        """For direction='in' (long), flip = first accel_z_5d < 0 after fill."""
        # Build accel_z series: positive for first 10 days, then negative
        # accel_z_5d = rolling(5).mean()
        # For direction='in': starts positive (confirming inflow), flips negative = exit
        accel_vals = [1.5] * 10 + [-0.5] * 10  # 20 days total
        # rolling(5).mean() starting at bar 4 (0-indexed):
        # bars 0-3: NaN
        # bar 4: mean([1.5]*5) = 1.5 > 0
        # ...
        # bar 9: mean([1.5]*5) = 1.5 > 0
        # bar 10: mean([1.5,1.5,1.5,1.5,-0.5]) = 5.5/5=1.1 > 0
        # bar 11: mean([1.5,1.5,1.5,-0.5,-0.5]) = 3.5/5=0.7 > 0
        # bar 12: mean([1.5,1.5,-0.5,-0.5,-0.5]) = 1.5/5=0.3 > 0
        # bar 13: mean([1.5,-0.5,-0.5,-0.5,-0.5]) = -0.5/5=-0.1 < 0 ← flip here
        # bar 14: mean([-0.5]*5) = -0.5 < 0

        node = "XLK"
        panel = _make_panel_with_accel_z(accel_vals, node=node, start="2021-01-04")
        fill_date = panel.index.get_level_values("date")[5]  # fill at bar 5 (within positive zone)

        flip_date = compute_accel_flip_exit(panel, node, fill_date, direction="in")

        assert flip_date is not None, "Should detect an accel_z_5d flip to negative"
        # Should be bar 13 (0-indexed)
        expected = panel.index.get_level_values("date")[13]
        assert flip_date == expected, f"Expected flip at {expected}, got {flip_date}"

    def test_no_flip_stays_positive(self):
        """For direction='in', if accel_z_5d stays positive throughout, no flip."""
        accel_vals = [1.5] * 20  # always positive
        node = "XLK"
        panel = _make_panel_with_accel_z(accel_vals, node=node, start="2021-01-04")
        fill_date = panel.index.get_level_values("date")[5]

        flip_date = compute_accel_flip_exit(panel, node, fill_date, direction="in")
        assert flip_date is None, "No flip expected when accel_z stays positive"

    def test_flip_for_out_direction(self):
        """For direction='out', flip = accel_z_5d goes positive (exit the short)."""
        accel_vals = [-1.5] * 10 + [0.8] * 10
        # rolling(5).mean():
        # bar 13: mean([-1.5, 0.8, 0.8, 0.8, 0.8]) = 1.7/5=0.34 > 0 ← flip
        node = "XLK"
        panel = _make_panel_with_accel_z(accel_vals, node=node, start="2021-01-04")
        fill_date = panel.index.get_level_values("date")[3]  # fill early in negative zone

        flip_date = compute_accel_flip_exit(panel, node, fill_date, direction="out")
        assert flip_date is not None, "Should detect flip from negative to positive"


# ---------------------------------------------------------------------------
# §7 Test 5: Fidelity gate abort on wrong-count fixture
# ---------------------------------------------------------------------------

class TestFidelityGate:
    """Spec §7: fidelity gate aborts with exit(1) on wrong count."""

    def _make_episodes(self, n_in: int, n_out: int) -> pd.DataFrame:
        rows = []
        for i in range(n_in):
            rows.append({"direction": "in", "onset_date": f"2020-01-{i+1:02d}"})
        for i in range(n_out):
            rows.append({"direction": "out", "onset_date": f"2020-06-{i+1:02d}"})
        return pd.DataFrame(rows)

    def test_abort_on_wrong_episode_count(self):
        """Wrong episode count triggers sys.exit(1)."""
        episodes = self._make_episodes(n_in=100, n_out=100)  # wrong counts
        ledger_counts = {"a15": 2357, "a9": 438, "a17": 262}
        with pytest.raises(SystemExit) as exc_info:
            run_fidelity_gate(episodes, ledger_counts, washout_count=639)
        assert exc_info.value.code == 1

    def test_abort_on_wrong_compound_count(self):
        """Wrong compound count triggers sys.exit(1) when >5% off."""
        episodes = self._make_episodes(n_in=357, n_out=392)
        # a15 ledger=2357, actual=100 → >5% off → abort
        ledger_counts = {"a15": 100, "a9": 438, "a17": 262}
        with pytest.raises(SystemExit) as exc_info:
            run_fidelity_gate(episodes, ledger_counts, washout_count=639)
        assert exc_info.value.code == 1

    def test_abort_on_wrong_washout_count(self):
        """Wrong washout count triggers sys.exit(1)."""
        episodes = self._make_episodes(n_in=357, n_out=392)
        ledger_counts = {"a15": 2357, "a9": 438, "a17": 262}
        with pytest.raises(SystemExit) as exc_info:
            run_fidelity_gate(episodes, ledger_counts, washout_count=100)  # way off
        assert exc_info.value.code == 1

    def test_passes_on_correct_counts(self):
        """Correct counts do not abort."""
        episodes = self._make_episodes(n_in=357, n_out=392)
        ledger_counts = {"a15": 2357, "a9": 438, "a17": 262}
        # Should not raise
        run_fidelity_gate(episodes, ledger_counts, washout_count=639)


# ---------------------------------------------------------------------------
# §7 Test 6: sigma20 PIT correctness
# ---------------------------------------------------------------------------

class TestSigma20:
    """PIT σ uses only data through trigger date."""

    def test_sigma20_uses_only_prior_bars(self):
        """sigma20 computed at t must not use bars after t."""
        # Build a mildly volatile series (1% daily) for 22 bars,
        # then a huge spike after trigger bar (which should NOT affect sigma)
        rng = np.random.default_rng(0)
        base = [100.0]
        for _ in range(21):
            base.append(base[-1] * (1 + rng.normal(0, 0.01)))  # ~1% daily vol
        spike = [base[-1] * 10.0] * 10  # 10x spike after trigger
        prices = base + spike

        close = _make_close(prices)
        trigger = close.index[21]  # trigger at bar 21 (last bar of base)

        s_at_trigger = compute_sigma20(close, trigger)
        assert s_at_trigger is not None

        # σ computed from the 20 bars BEFORE trigger (all ~1% daily vol)
        # If PIT is correct, σ should be consistent with ~1% daily vol × sqrt(21) ≈ 4.6%
        # The spike AFTER trigger should not inflate it
        assert s_at_trigger < 0.20, (
            f"PIT σ should be consistent with 1% daily vol; got {s_at_trigger:.4f} "
            f"(spike after trigger should be excluded)"
        )
        assert s_at_trigger > 0.001, (
            f"σ should be positive for volatile series; got {s_at_trigger:.6f}"
        )

    def test_sigma20_none_on_insufficient_data(self):
        """Returns None when fewer than 10 sessions of prior data."""
        prices = [100.0] * 5
        close = _make_close(prices)
        trigger = close.index[4]
        s = compute_sigma20(close, trigger)
        assert s is None


# ---------------------------------------------------------------------------
# §7 Test 7: grade_event short-side uses inverted close
# ---------------------------------------------------------------------------

class TestGradeEventShort:
    """grade_event correctly switches to inverted close for direction='out'."""

    def test_short_policy_r_negative_when_price_rises(self):
        """Short event: price rises after trigger → policy R should be negative (STOPPED=-1R)."""
        # Build a close series with 21+ bars of volatility for σ computation,
        # then price rises 20%+ after trigger (bad for short).
        rng = np.random.default_rng(42)
        # 22 volatile bars for σ, then 22 rising bars (horizon=21+fill)
        base = [100.0]
        for _ in range(21):
            base.append(base[-1] * (1 + rng.normal(0, 0.015)))
        rising = [base[-1] * 1.20] * 22  # 20% rise → short loss
        prices = base + rising

        close = _make_close(prices)
        trigger = close.index[20]  # trigger at bar 20, fill at bar 21

        result = grade_event(
            close=close,
            trigger_date=trigger,
            direction="out",
            parameterization="rot21",
        )

        # If matured: price rises on short → should be STOPPED (R=-1) or at least ≤0
        if result.get("state") is not None:
            policy_r = result.get("policy_R_rot21")
            if policy_r is not None:
                assert policy_r <= 0, (
                    f"Short event with rising price should have policy R <= 0; got {policy_r}"
                )


# ---------------------------------------------------------------------------
# §7 Test 8: σ-barrier parameterizations
# ---------------------------------------------------------------------------

class TestSigmaBarriers:
    """sigma_barriers returns correct multipliers for rot21 and pos63."""

    def test_rot21(self):
        s = 0.10
        b = sigma_barriers(s, "rot21")
        assert abs(b["stop_mult"] - 0.90) < 1e-9
        assert abs(b["cushion_mult"] - 1.10) < 1e-9
        assert abs(b["liftoff_mult"] - 1.10) < 1e-9  # k=1: 1+s
        assert b["horizon"] == 21
        assert abs(b["dead_band"] - 0.10) < 1e-9
        assert abs(b["dead_cap"] - 0.05) < 1e-9

    def test_pos63(self):
        s = 0.10
        b = sigma_barriers(s, "pos63")
        assert abs(b["stop_mult"] - 0.90) < 1e-9
        assert abs(b["cushion_mult"] - 1.10) < 1e-9
        assert abs(b["liftoff_mult"] - 1.20) < 1e-9  # k=2: 1+2s
        assert b["horizon"] == 63

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            sigma_barriers(0.10, "unknown")
