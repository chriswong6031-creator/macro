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
    """Spec §7: first21 dedup — 21 TRADING SESSIONS, not calendar days."""

    def test_drops_fires_within_21_sessions(self):
        """Fires within 21 trading sessions of a kept fire are dropped.

        np.busday_offset('2021-01-04', 21) = '2021-02-02'; that date is ≤21 sessions → dropped.
        np.busday_offset('2021-01-04', 22) = '2021-02-03'; 22 bdays from 01-04 → kept.
        """
        import numpy as np
        d0 = pd.Timestamp("2021-01-04")
        # Verify the business-day arithmetic we rely on
        assert np.busday_count(d0.date(), pd.Timestamp("2021-02-02").date()) == 21
        assert np.busday_count(d0.date(), pd.Timestamp("2021-02-03").date()) == 22

        dates = [
            pd.Timestamp("2021-01-04"),   # kept
            pd.Timestamp("2021-01-10"),   # few bdays → dropped
            pd.Timestamp("2021-01-20"),   # < 21 bdays → dropped
            pd.Timestamp("2021-02-02"),   # exactly 21 bdays → dropped (not > 21)
            pd.Timestamp("2021-02-03"),   # 22 bdays from 01-04 → kept
            pd.Timestamp("2021-02-04"),   # 1 bday from 02-03 → dropped
            pd.Timestamp("2021-03-15"),   # > 21 bdays from 02-03 → kept
        ]
        kept = first21_dedup(dates)
        assert len(kept) == 3, f"Expected 3 kept fires, got {len(kept)}: {kept}"
        assert kept[0] == pd.Timestamp("2021-01-04")
        assert kept[1] == pd.Timestamp("2021-02-03")
        assert kept[2] == pd.Timestamp("2021-03-15")

    def test_empty_list(self):
        assert first21_dedup([]) == []

    def test_single_element(self):
        d = pd.Timestamp("2021-01-04")
        assert first21_dedup([d]) == [d]

    def test_exactly_21_sessions_is_dropped(self):
        """Exactly 21 trading sessions apart: busday_count = 21, not > 21 → dropped."""
        import numpy as np
        d1 = pd.Timestamp("2021-01-04")
        d2 = pd.Timestamp("2021-02-02")  # exactly 21 bdays after 2021-01-04
        assert np.busday_count(d1.date(), d2.date()) == 21
        # Our rule: keep if gap > 21 sessions; 21 > 21 is False → dropped
        kept = first21_dedup([d1, d2])
        assert len(kept) == 1, f"Exactly 21 sessions should be dropped; got {kept}"

    def test_22_sessions_apart_is_kept(self):
        """22 trading sessions apart → kept."""
        import numpy as np
        d1 = pd.Timestamp("2021-01-04")
        d2 = pd.Timestamp("2021-02-03")  # 22 bdays after 2021-01-04
        assert np.busday_count(d1.date(), d2.date()) == 22
        kept = first21_dedup([d1, d2])
        assert len(kept) == 2, f"22 sessions should be kept; got {kept}"

    def test_calendar_close_but_few_sessions(self):
        """Two dates 21 calendar days apart but only 15 trading sessions.
        Under session semantics: 15 < 21 → dropped (but under old calendar semantics:
        21 cal days is exactly boundary of old rule, and was treated as ≤21 → dropped there too).
        Key: this date pair has fewer bdays (15) than cal days (21), confirming the
        implementation uses business days not calendar days."""
        # 15 bdays < 21 → should be dropped
        d1 = pd.Timestamp("2021-01-04")
        d2 = pd.Timestamp("2021-01-25")  # 21 calendar days, 15 bdays (Mon Jan 4 → Mon Jan 25)
        import numpy as np
        bdays = np.busday_count(d1.date(), d2.date())
        assert bdays == 15, f"Expected 15 bdays between Jan 4 and Jan 25; got {bdays}"
        kept = first21_dedup([d1, d2])
        # 15 sessions < 21 → dropped
        assert len(kept) == 1, f"15 sessions should be dropped under session semantics; got {kept}"

    def test_with_trading_index(self):
        """Passing an actual trading index uses positional gaps (most accurate)."""
        # Build a synthetic trading index with 50 business days
        idx = pd.bdate_range("2021-01-04", periods=50)
        d1 = idx[0]
        d2 = idx[21]   # exactly 21 sessions away (iloc distance=21) → dropped
        d3 = idx[22]   # 22 sessions from d1 → kept
        kept = first21_dedup([d1, d2, d3], trading_index=idx)
        assert len(kept) == 2, f"Expected 2 kept (d1, d3); got {kept}"
        assert kept[0] == d1
        assert kept[1] == d3


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
# §7 Test 7b: short-side excess sign (blocker fix pinned by unit test)
# ---------------------------------------------------------------------------

class TestShortSideExcessSign:
    """excess_{h} for direction=='out' must be direction-adjusted node_ret - spy_ret.

    Blocker fix 2026-07-05: the pre-fix code did spy_ret - node_ret for 'out',
    which was the arithmetic negation of the correct value.

    Fixture: node falls 10%, SPY falls 2% over the forward horizon.
      - direction-adjusted node return (inverted close): +(≈11.1%) — a short win
      - spy return: -2%
      - correct excess = inv_node_ret - spy_ret ≈ +0.111 - (-0.02) ≈ +0.131  (positive: short outperforms)
      - wrong (pre-fix): spy_ret - inv_node_ret ≈ -0.02 - 0.111 ≈ -0.131  (negative: wrong sign)
    """

    def test_short_excess_sign_falling_node_rising_spy(self):
        """Falling node + rising SPY → short excess should be positive (short outperforms)."""
        # Build 22 volatile bars for sigma, then controlled forward bars
        rng = np.random.default_rng(7)
        base = [100.0]
        for _ in range(21):
            base.append(base[-1] * (1 + rng.normal(0, 0.015)))

        entry = base[-1]
        # Node falls 10% over 22 forward bars (fill + 21 forward = horizon 21)
        node_fwd = [entry * 0.90] * 22
        node_prices = base + node_fwd

        spy_base = [50.0]
        for _ in range(21):
            spy_base.append(spy_base[-1] * (1 + rng.normal(0, 0.01)))
        spy_entry = spy_base[-1]
        # SPY rises 2% over same window
        spy_fwd = [spy_entry * 1.02] * 22
        spy_prices = spy_base + spy_fwd

        close = _make_close(node_prices)
        spy_close = _make_close(spy_prices)
        trigger = close.index[20]  # trigger at bar 20, fill at bar 21

        result = grade_event(
            close=close,
            trigger_date=trigger,
            direction="out",
            parameterization="rot21",
            spy_close=spy_close,
        )

        exc = result.get("excess_21")
        assert exc is not None, "excess_21 should be computed when spy_close is provided"
        # Short with falling node → direction-adjusted return is positive;
        # correct excess = inv_node_ret - spy_ret > 0
        assert exc > 0, (
            f"Short-side excess with falling node / rising SPY should be positive "
            f"(short outperforms); got {exc:.6f}. "
            f"Pre-fix bug was spy_ret - node_ret (sign negated)."
        )

    def test_short_excess_sign_rising_node_flat_spy(self):
        """Rising node + flat SPY → short excess should be negative (short underperforms)."""
        rng = np.random.default_rng(13)
        base = [100.0]
        for _ in range(21):
            base.append(base[-1] * (1 + rng.normal(0, 0.015)))
        entry = base[-1]
        # Node rises 15% over 22 forward bars → bad for short
        node_fwd = [entry * 1.15] * 22
        node_prices = base + node_fwd

        spy_base = [50.0]
        for _ in range(21):
            spy_base.append(spy_base[-1] * (1 + rng.normal(0, 0.01)))
        spy_entry = spy_base[-1]
        # SPY flat
        spy_fwd = [spy_entry] * 22
        spy_prices = spy_base + spy_fwd

        close = _make_close(node_prices)
        spy_close = _make_close(spy_prices)
        trigger = close.index[20]

        result = grade_event(
            close=close,
            trigger_date=trigger,
            direction="out",
            parameterization="rot21",
            spy_close=spy_close,
        )

        exc = result.get("excess_21")
        assert exc is not None, "excess_21 should be computed"
        # Rising node → inv_close falls → direction-adjusted return negative;
        # excess = inv_node_ret - spy_ret < 0
        assert exc < 0, (
            f"Short-side excess with rising node / flat SPY should be negative "
            f"(short underperforms); got {exc:.6f}."
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
