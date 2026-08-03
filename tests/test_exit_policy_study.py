"""Tests for scripts/exit_policy_study.py — the exit-policy horse race (Learning Loop G3).

Two layers:

* SYNTHETIC PATHS pin every policy's arithmetic on paths whose answer is known by hand —
  the running-max anchor (not the entry anchor), the strict `<` stop test, the breakeven
  promotion timing, the same-bar stop-before-target ordering, the H cap, and the
  data_end flag. These are the tests that keep a refactor honest, so several of them are
  written as MUTATION PINS: they fail if a specific line is reordered or a comparison is
  loosened, not merely if the whole walker breaks.

* REAL DATA pins the two claims the report makes about itself: that P0 reproduces the
  shipped ledger key-for-key, and that every episode excluded from the cohort is counted.
  The study is read-only, so these tests write nothing (the repo's MM_DATA_GUARD tripwire
  would catch it if they did).
"""
import json
import math
import re
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import track_scoring as ts  # noqa: E402
from scripts.exit_policy_study import (  # noqa: E402
    BE_ARM_ATR,
    CAP_PLAN,
    CAP_TRAIL,
    DISPLAY_ND,
    HORIZON_LADDER,
    LEDGER_HORIZON,
    POLICY_KEYS,
    POLICY_SHORT,
    PLAN_ATR_MULT,
    PLAN_R_MULT,
    R_DATA_END,
    R_HORIZON,
    R_PLAN_STOP,
    R_PLAN_TARGET,
    R_TRAIL,
    _plan_geometry,
    build_cohort,
    decompose,
    evaluate,
    excursions,
    paired_delta,
    policy_metrics,
    reconcile_round,
    render_report,
    run_study,
    walk_fixed,
    walk_target_stop,
    walk_trail,
    wilder_atr,
    window_overlap,
)
from scripts.grade_us_board import _TROUGH_LB, _TROUGH_TOL  # noqa: E402


# --------------------------------------------------------------------------- #
# walk_fixed
# --------------------------------------------------------------------------- #
class TestWalkFixed:
    def test_exits_at_the_cap_not_at_the_end_of_the_path(self):
        w = walk_fixed([101, 102, 103, 104, 105], cap=3)
        assert (w["exit_bar"], w["exit_px"], w["reason"]) == (3, 103.0, R_HORIZON)

    def test_short_path_marks_at_the_last_bar_and_flags_data_end(self):
        w = walk_fixed([101, 102], cap=10)
        assert (w["exit_bar"], w["exit_px"], w["reason"]) == (2, 102.0, R_DATA_END)

    def test_exact_length_path_is_a_horizon_exit_not_a_data_end(self):
        # The off-by-one that would silently reclassify every fully-matured episode.
        w = walk_fixed([1, 2, 3], cap=3)
        assert w["reason"] == R_HORIZON

    def test_empty_path_raises(self):
        with pytest.raises(ValueError):
            walk_fixed([], cap=3)


# --------------------------------------------------------------------------- #
# walk_trail
# --------------------------------------------------------------------------- #
class TestWalkTrail:
    def test_monotone_rise_never_stops_out(self):
        w = walk_trail([101, 102, 103, 104], entry=100.0, atr=1.0, k=2.0, cap=10)
        assert w["reason"] == R_DATA_END and w["exit_bar"] == 4

    def test_anchor_is_the_RUNNING_MAX_close_not_the_entry(self):
        """The load-bearing pin. Path runs 100 -> 110, then falls to 107.

        Against a RUNNING-MAX anchor the stop is 110 - 2*1 = 108, so 107 exits.
        Against an ENTRY anchor it would be 100 - 2 = 98 and the position would ride on.
        A trailing stop that does not trail is the whole bug this test exists to catch.
        """
        prices = [102, 105, 110, 107, 106]
        w = walk_trail(prices, entry=100.0, atr=1.0, k=2.0, cap=10)
        assert (w["exit_bar"], w["exit_px"], w["reason"]) == (4, 107.0, R_TRAIL)

    def test_anchor_starts_at_the_entry_price(self):
        """Bar 1 gapping straight down must stop at entry - k*atr, so the anchor cannot
        start at the first forward close (which would set the stop 2 ATRs lower)."""
        w = walk_trail([97.0, 96.0], entry=100.0, atr=1.0, k=2.0, cap=10)
        assert (w["exit_bar"], w["reason"]) == (1, R_TRAIL)

    def test_close_exactly_at_the_stop_does_not_exit(self):
        """`p < stop`, never `<=`. A touch is not a break."""
        w = walk_trail([98.0, 98.0], entry=100.0, atr=1.0, k=2.0, cap=10)
        assert w["reason"] == R_DATA_END

    def test_one_tick_below_the_stop_does_exit(self):
        w = walk_trail([97.999, 98.0], entry=100.0, atr=1.0, k=2.0, cap=10)
        assert (w["exit_bar"], w["reason"]) == (1, R_TRAIL)

    def test_k_widens_the_stop(self):
        prices = [110.0, 107.0, 106.0, 105.0]
        tight = walk_trail(prices, entry=100.0, atr=1.0, k=2.0, cap=10)
        wide = walk_trail(prices, entry=100.0, atr=1.0, k=5.0, cap=10)
        assert tight["exit_bar"] == 2 and tight["reason"] == R_TRAIL
        assert wide["reason"] == R_DATA_END

    def test_hard_cap_binds_before_the_data_runs_out(self):
        prices = list(np.linspace(101, 160, 60))
        w = walk_trail(prices, entry=100.0, atr=1.0, k=2.0, cap=5)
        assert (w["exit_bar"], w["reason"]) == (5, R_HORIZON)

    def test_non_finite_bar_is_skipped_not_treated_as_a_break(self):
        w = walk_trail([105.0, float("nan"), 104.0], entry=100.0, atr=1.0, k=2.0, cap=10)
        assert w["reason"] == R_DATA_END and w["exit_bar"] == 3

    @pytest.mark.parametrize("atr", [0.0, -1.0, float("nan")])
    def test_bad_atr_raises(self, atr):
        with pytest.raises(ValueError):
            walk_trail([101.0], entry=100.0, atr=atr, k=2.0, cap=10)


class TestCloseOnlyStopDiagnostics:
    """The `lows` argument measures what the close-only convention costs (M5).

    It is a DIAGNOSTIC: it must never move an exit, and it must be measured against the
    stop that was RESTING before the session — not against a band the session's own close
    lifted into place.
    """

    def test_a_low_path_never_changes_the_exit(self):
        rng = np.random.default_rng(20260803)
        for _ in range(200):
            n = int(rng.integers(1, 30))
            path = 100.0 * np.cumprod(1.0 + rng.normal(0.001, 0.03, n))
            lows = path * (1.0 - np.abs(rng.normal(0.0, 0.02, n)))
            k, atr = float(rng.choice([2.0, 3.0])), float(rng.uniform(0.5, 4.0))
            blind = walk_trail(path, 100.0, atr, k, CAP_TRAIL)
            seeing = walk_trail(path, 100.0, atr, k, CAP_TRAIL, lows=lows)
            for key in ("exit_bar", "exit_px", "reason", "stop_level"):
                assert blind[key] == seeing[key], f"the low path moved {key}"

    def test_flags_a_low_through_the_resting_stop_that_no_close_ever_broke(self):
        # Bar 1: resting stop is 100 - 2*1 = 98; the low pierces it, the close does not.
        w = walk_trail([100.0, 99.0], entry=100.0, atr=1.0, k=2.0, cap=10,
                       lows=[97.5, 99.0])
        assert w["reason"] == R_DATA_END          # close-only: still holding
        assert w["intraday_bar"] == 1             # a real stop would have been hit

    def test_the_resting_stop_is_the_PREVIOUS_bars_band(self):
        """MUTATION PIN. Bar 1 closes at a new high, which lifts the band to 108.

        The low of 105 is under THAT band but nowhere near the 98 a resting order would
        have carried into the session. Test the low against the same-bar band instead and
        this goes red — it would manufacture an intraday break on every up-then-down day.
        """
        w = walk_trail([110.0, 109.0], entry=100.0, atr=1.0, k=2.0, cap=10,
                       lows=[105.0, 109.0])
        assert w["intraday_bar"] is None

    def test_stop_level_is_reported_on_a_stop_exit_and_nowhere_else(self):
        stopped = walk_trail([110.0, 107.0], entry=100.0, atr=1.0, k=2.0, cap=10)
        assert stopped["reason"] == R_TRAIL
        assert stopped["stop_level"] == pytest.approx(108.0)   # 110 anchor - 2*1
        assert walk_fixed([101.0, 102.0], cap=2)["stop_level"] is None
        assert walk_trail([101.0], entry=100.0, atr=1.0, k=2.0,
                          cap=10)["stop_level"] is None

    def test_plan_stop_intraday_test_is_inclusive_like_its_close_test(self):
        """`p <= stop` on closes, so `low <= stop` intraday — one convention, not two."""
        w = walk_target_stop([100.0, 100.0], stop=95.0, target=130.0, cap=21,
                             lows=[95.0, 100.0])
        assert w["reason"] == R_DATA_END and w["intraday_bar"] == 1

    def test_plan_walker_reports_the_level_that_fired(self):
        w = walk_target_stop([94.0], stop=95.0, target=130.0, cap=21)
        assert (w["reason"], w["stop_level"]) == (R_PLAN_STOP, 95.0)
        assert walk_target_stop([131.0], stop=95.0, target=130.0,
                                cap=21)["stop_level"] is None


class TestBreakevenPromotion:
    def test_floor_binds_only_AFTER_the_arm_level_is_reached(self):
        """Path pokes to +1 ATR, then slides back through the entry.

        Armed: the floor is the entry, so the first close below 100 exits at bar 3.
        Unarmed (same path, no breakeven): the trailing stop is 101 - 3 = 98, so 99.5
        rides on. The two must differ — that difference IS the policy.
        """
        prices = [100.5, 101.0, 99.5, 99.0]
        armed = walk_trail(prices, entry=100.0, atr=1.0, k=3.0, cap=10,
                           breakeven_arm_atr=1.0)
        plain = walk_trail(prices, entry=100.0, atr=1.0, k=3.0, cap=10)
        assert (armed["exit_bar"], armed["exit_px"], armed["reason"]) == (3, 99.5, R_TRAIL)
        assert plain["reason"] == R_DATA_END

    def test_never_reaching_the_arm_level_leaves_the_policy_identical(self):
        prices = [100.5, 100.9, 99.5, 99.0]          # never touches 101.0
        armed = walk_trail(prices, entry=100.0, atr=1.0, k=3.0, cap=10,
                           breakeven_arm_atr=1.0)
        plain = walk_trail(prices, entry=100.0, atr=1.0, k=3.0, cap=10)
        assert armed == plain

    def test_arm_level_is_inclusive(self):
        """`p >= trigger`. A close exactly at entry + m*atr arms the floor."""
        prices = [101.0, 99.5]
        w = walk_trail(prices, entry=100.0, atr=1.0, k=3.0, cap=10, breakeven_arm_atr=1.0)
        assert (w["exit_bar"], w["reason"]) == (2, R_TRAIL)

    def test_floor_never_un_arms(self):
        prices = [101.0, 100.2, 100.1, 99.9]
        w = walk_trail(prices, entry=100.0, atr=1.0, k=3.0, cap=10, breakeven_arm_atr=1.0)
        assert w["exit_bar"] == 4                      # still armed three bars later

    def test_arming_at_k_atrs_is_PROVABLY_a_no_op(self):
        """The documented degeneracy: reading P4's '+1R' as the trail's OWN initial risk
        (k x ATR) makes it identical to a plain k-trail on EVERY path.

        Once a close reaches entry + k*atr the anchor is at least that high, so the
        trailing stop is already >= entry and the breakeven floor can never bind. This is
        why the parameter is an ATR multiple, and this test is what stops a later
        'simplification' from reintroducing a policy that measures nothing.
        """
        rng = np.random.default_rng(20260802)
        for _ in range(200):
            n = int(rng.integers(1, 40))
            path = 100.0 * np.cumprod(1.0 + rng.normal(0.001, 0.03, n))
            k = float(rng.choice([1.5, 2.0, 3.0, 4.0]))
            atr = float(rng.uniform(0.5, 5.0))
            plain = walk_trail(path, 100.0, atr, k, CAP_TRAIL)
            degenerate = walk_trail(path, 100.0, atr, k, CAP_TRAIL, breakeven_arm_atr=k)
            assert plain == degenerate

    def test_p4s_shipped_arm_is_not_the_degenerate_one(self):
        assert BE_ARM_ATR < 3.0, "P4 arms below the k=3 trail's own risk, or it is a no-op"


# --------------------------------------------------------------------------- #
# walk_target_stop
# --------------------------------------------------------------------------- #
class TestWalkTargetStop:
    def test_target_first(self):
        w = walk_target_stop([101, 104, 90], stop=95.0, target=103.0, cap=21)
        assert (w["exit_bar"], w["exit_px"], w["reason"]) == (2, 104.0, R_PLAN_TARGET)

    def test_stop_first(self):
        w = walk_target_stop([101, 94, 110], stop=95.0, target=103.0, cap=21)
        assert (w["exit_bar"], w["exit_px"], w["reason"]) == (2, 94.0, R_PLAN_STOP)

    def test_stop_boundary_is_inclusive(self):
        w = walk_target_stop([95.0], stop=95.0, target=103.0, cap=21)
        assert w["reason"] == R_PLAN_STOP

    def test_target_boundary_is_inclusive(self):
        w = walk_target_stop([103.0], stop=95.0, target=103.0, cap=21)
        assert w["reason"] == R_PLAN_TARGET

    def test_same_bar_tie_resolves_as_the_STOP(self):
        """MUTATION PIN for the conservative ordering.

        Well-formed geometry (stop < entry < target) makes this unreachable on daily
        closes — one close cannot be both below the stop and above the target. So the
        ordering is pinned here at the walker level with a degenerate stop ABOVE the
        target, where both conditions are true on the same bar. Swap the two `if`s in
        walk_target_stop and this test goes red; nothing else in the suite would.
        """
        w = walk_target_stop([100.0], stop=105.0, target=99.0, cap=21)
        assert w["reason"] == R_PLAN_STOP

    def test_cap_and_data_end(self):
        flat = [100.0] * 30
        assert walk_target_stop(flat, 95.0, 103.0, cap=21)["exit_bar"] == 21
        assert walk_target_stop(flat, 95.0, 103.0, cap=21)["reason"] == R_HORIZON
        short = walk_target_stop([100.0] * 5, 95.0, 103.0, cap=21)
        assert (short["exit_bar"], short["reason"]) == (5, R_DATA_END)


# --------------------------------------------------------------------------- #
# ATR + plan geometry
# --------------------------------------------------------------------------- #
class TestWilderATR:
    def _bars(self, n, hi, lo, close):
        idx = pd.bdate_range("2026-01-01", periods=n)
        return (pd.Series([hi] * n, index=idx), pd.Series([lo] * n, index=idx),
                pd.Series([close] * n, index=idx))

    def test_constant_range_converges_to_that_range(self):
        h, l, c = self._bars(60, 102.0, 100.0, 101.0)
        atr = wilder_atr(h, l, c, n=14)
        assert atr.iloc[-1] == pytest.approx(2.0, abs=1e-9)

    def test_is_null_before_the_period_fills(self):
        h, l, c = self._bars(20, 102.0, 100.0, 101.0)
        atr = wilder_atr(h, l, c, n=14)
        assert atr.iloc[:13].isna().all() and math.isfinite(float(atr.iloc[13]))

    def test_true_range_uses_the_prior_close_gap(self):
        idx = pd.bdate_range("2026-01-01", periods=3)
        # Bar 3 gaps up: H-L is 1 but H - prev_close is 11, so TR must be 11.
        h = pd.Series([101.0, 101.0, 111.0], index=idx)
        lo = pd.Series([100.0, 100.0, 110.0], index=idx)
        c = pd.Series([100.5, 100.5, 110.5], index=idx)
        atr = wilder_atr(h, lo, c, n=1)
        assert float(atr.iloc[2]) == pytest.approx(10.5)

    def test_no_lookahead(self):
        """ATR[t] must not move when bars after t change."""
        idx = pd.bdate_range("2026-01-01", periods=40)
        rng = np.random.default_rng(7)
        c = pd.Series(100 + np.cumsum(rng.normal(0, 1, 40)), index=idx)
        h, lo = c + 1.0, c - 1.0
        full = wilder_atr(h, lo, c, n=14)
        trunc = wilder_atr(h.iloc[:25], lo.iloc[:25], c.iloc[:25], n=14)
        assert float(full.iloc[24]) == pytest.approx(float(trunc.iloc[24]))


class TestPlanGeometry:
    def _ep(self, plan_stop):
        return {"entry": 100.0, "atr": 2.0, "plan_stop": plan_stop}

    def test_uses_the_published_invalidation_when_it_sits_below_entry(self):
        stop, target, src = _plan_geometry(self._ep(90.0))
        assert (stop, src) == (90.0, "plan_invalidation")
        assert target == pytest.approx(100.0 + PLAN_R_MULT * 10.0)

    @pytest.mark.parametrize("bad", [None, 100.0, 120.0, float("nan")])
    def test_falls_back_to_the_atr_stop_when_the_level_is_absent_or_not_below_entry(self, bad):
        stop, target, src = _plan_geometry(self._ep(bad))
        assert src == "atr_fallback"
        assert stop == pytest.approx(100.0 - PLAN_ATR_MULT * 2.0)
        assert target == pytest.approx(100.0 + PLAN_R_MULT * PLAN_ATR_MULT * 2.0)

    def test_r_is_always_positive_so_the_target_is_above_entry(self):
        for v in (None, 99.9, 50.0, 100.0, float("nan")):
            stop, target, _ = _plan_geometry(self._ep(v))
            assert stop < 100.0 < target


# --------------------------------------------------------------------------- #
# decomposition + paired delta
# --------------------------------------------------------------------------- #
def _row(tk, day, pnl, held, **kw):
    r = {"ticker": tk, "board_date": day, "pnl": pnl, "held": held,
         "excess": None, "exit_reason": R_HORIZON, "censored": False,
         "matured": True, "mfe": abs(pnl) + 1.0, "mae": -abs(pnl) - 1.0}
    r.update(kw)
    return r


class TestDecompose:
    def test_buckets_are_keyed_on_exit_bar_and_on_the_ANCHORS_call(self):
        base = [_row("A", "d1", 5.0, 10), _row("B", "d1", -5.0, 10),
                _row("C", "d1", 4.0, 10), _row("D", "d1", -4.0, 10),
                _row("E", "d1", 1.0, 10)]
        rows = [_row("A", "d1", 9.0, 15),    # held longer, anchor green -> extended_winner
                _row("B", "d1", -9.0, 15),   # held longer, anchor red   -> extended_loser
                _row("C", "d1", 2.0, 4),     # cut early,  anchor green  -> cut_winner
                _row("D", "d1", -1.0, 4),    # cut early,  anchor red    -> cut_loser
                _row("E", "d1", 1.0, 10)]    # same bar
        d = decompose(rows, base)
        b = d["buckets"]
        assert (b["extended_winner"]["n"], b["extended_loser"]["n"]) == (1, 1)
        assert (b["cut_winner"]["n"], b["cut_loser"]["n"], b["same_bar"]["n"]) == (1, 1, 1)
        assert b["extended_winner"]["contribution_pp"] == pytest.approx(4.0 / 5)
        assert b["cut_loser"]["contribution_pp"] == pytest.approx(3.0 / 5)

    def test_the_winner_flag_is_the_ANCHORS_pnl_not_the_POLICYS(self):
        """MUTATION PIN for the bucket key — the sibling test above cannot see it.

        Up there every episode has the same SIGN in both legs, so keying on the policy's
        own P&L (`float(r[field]) > 0`) reproduces the identical five buckets and the
        test still passes. Here every pair CROSSES: the anchor's call and the policy's
        call disagree on all four, so the two keyings put every episode in a different
        bucket and the contributions separate.

          F  anchor +3 green, policy −2 red,  held longer -> extended_WINNER
          G  anchor −3 red,   policy +2 green,held longer -> extended_LOSER
          H  anchor +4 green, policy −1 red,  cut early   -> cut_WINNER
          I  anchor −4 red,   policy +1 green,cut early   -> cut_LOSER
          J  anchor  0.0 (a win is `> 0`, so NOT green)   -> extended_LOSER
        """
        base = [_row("F", "d1", 3.0, 10), _row("G", "d1", -3.0, 10),
                _row("H", "d1", 4.0, 10), _row("I", "d1", -4.0, 10),
                _row("J", "d1", 0.0, 10)]
        rows = [_row("F", "d1", -2.0, 15), _row("G", "d1", 2.0, 15),
                _row("H", "d1", -1.0, 4), _row("I", "d1", 1.0, 4),
                _row("J", "d1", -1.0, 15)]
        b = decompose(rows, base)["buckets"]
        assert (b["extended_winner"]["n"], b["extended_loser"]["n"]) == (1, 2)
        assert (b["cut_winner"]["n"], b["cut_loser"]["n"]) == (1, 1)
        # Keyed on the anchor: F alone extends a winner (Δ = −5), G and J extend losers
        # (Δ = +5 and −1). Keyed on the policy the two contributions would be +1.00 and
        # −1.20 instead.
        assert b["extended_winner"]["contribution_pp"] == pytest.approx(-1.0)
        assert b["extended_loser"]["contribution_pp"] == pytest.approx(0.8)
        assert b["cut_winner"]["contribution_pp"] == pytest.approx(-1.0)
        assert b["cut_loser"]["contribution_pp"] == pytest.approx(1.0)

    def test_a_flat_anchor_is_not_a_winner(self):
        """`> 0`, never `>= 0`. A 0.00% anchor row belongs to the LOSER side."""
        b = decompose([_row("J", "d1", -1.0, 15)], [_row("J", "d1", 0.0, 10)])["buckets"]
        assert (b["extended_loser"]["n"], b["extended_winner"]["n"]) == (1, 0)


class TestReconcileRound:
    def test_parts_sum_to_the_rounded_total(self):
        exact = {"a": -0.4463, "b": -0.1487, "c": 0.0531, "d": 0.0162, "e": 0.0}
        disp = reconcile_round(exact, 2)
        assert sum(round(v, 10) for v in disp.values()) == pytest.approx(
            round(sum(exact.values()), 2))

    def test_recovers_a_total_that_naive_rounding_throws_away(self):
        """Three parts that each round to zero still have to add up to their total."""
        exact = {"a": 0.004, "b": 0.004, "c": 0.004}
        disp = reconcile_round(exact, 2)
        assert sum(disp.values()) == pytest.approx(0.01)
        assert sorted(round(v, 2) for v in disp.values()) == [0.0, 0.0, 0.01]

    def test_no_part_moves_by_more_than_one_display_unit(self):
        rng = np.random.default_rng(3)
        for _ in range(300):
            exact = {k: float(rng.normal(0, 1)) for k in "abcde"}
            disp = reconcile_round(exact, 2)
            for k, v in exact.items():
                assert abs(disp[k] - v) < 0.01 + 1e-9
            assert sum(disp.values()) == pytest.approx(round(sum(exact.values()), 2))

    def test_is_deterministic_including_on_ties(self):
        exact = {"a": 0.005, "b": 0.005, "c": 0.005, "d": 0.005}
        assert reconcile_round(exact) == reconcile_round(exact)
        assert reconcile_round(exact) == reconcile_round(exact, DISPLAY_ND)


class TestWindowOverlap:
    """B4's measurement — the blocks the bootstrap treats as independent draws."""

    def _sessions(self, n=60):
        return pd.bdate_range("2026-01-01", periods=n)

    def _cohort(self, days):
        return [{"board_date": str(d.date()), "ticker": "X"} for d in days]

    def test_consecutive_board_days_overlap_by_all_but_one_bar(self):
        s = self._sessions()
        ov = window_overlap(self._cohort([s[10], s[11]]), s, horizon=10)
        assert ov["overlap_median_pct"] == pytest.approx(90.0)
        assert ov["max_disjoint_windows"] == 1        # they share tape: only one is free

    def test_board_days_a_full_horizon_apart_do_not_overlap(self):
        s = self._sessions()
        ov = window_overlap(self._cohort([s[10], s[20]]), s, horizon=10)
        assert ov["overlap_median_pct"] == pytest.approx(0.0)
        assert ov["max_disjoint_windows"] == 2
        assert ov["union_sessions"] == ov["total_window_bars"] == 20

    def test_the_union_of_windows_is_smaller_than_their_bar_count_when_they_overlap(self):
        s = self._sessions()
        ov = window_overlap(self._cohort(list(s[10:18])), s, horizon=10)
        assert ov["n_board_days"] == 8
        assert ov["union_sessions"] < ov["total_window_bars"]
        assert ov["max_disjoint_windows"] < ov["n_board_days"]

    def test_a_single_board_day_reports_no_neighbour_pairs(self):
        s = self._sessions()
        ov = window_overlap(self._cohort([s[10]]), s, horizon=10)
        assert ov["n_neighbour_pairs"] == 0 and ov["overlap_median_pct"] is None

    def test_contributions_sum_EXACTLY_to_the_mean_delta(self):
        """The identity that makes the decomposition a decomposition rather than five
        loosely related numbers."""
        rng = np.random.default_rng(11)
        base, rows = [], []
        for i in range(60):
            day = f"d{i % 5}"
            bp, rp = float(rng.normal(0, 5)), float(rng.normal(0, 5))
            bh, rh = int(rng.integers(1, 21)), int(rng.integers(1, 21))
            base.append(_row(f"T{i}", day, bp, bh))
            rows.append(_row(f"T{i}", day, rp, rh))
        d = decompose(rows, base)
        expected = paired_delta(rows, base)["mean_delta_pct"]
        assert d["total_contribution_pp"] == pytest.approx(expected, abs=5e-3)
        assert (d["winners_kept_net_pp"] + d["losers_cut_net_pp"]
                + d["buckets"]["same_bar"]["contribution_pp"]) == pytest.approx(
                    d["total_contribution_pp"], abs=5e-3)

    def test_same_bar_bucket_contributes_zero_when_the_policies_agree(self):
        base = [_row("A", "d1", 3.0, 10)]
        d = decompose([_row("A", "d1", 3.0, 10)], base)
        assert d["buckets"]["same_bar"]["contribution_pp"] == 0.0
        assert d["total_contribution_pp"] == 0.0


class TestPairedDelta:
    def test_pairs_on_ticker_AND_board_date(self):
        """The same name can hold two episodes from two runs; pairing on ticker alone
        would cross them."""
        base = [_row("A", "d1", 1.0, 10), _row("A", "d2", 5.0, 10)]
        rows = [_row("A", "d1", 3.0, 12), _row("A", "d2", 6.0, 12)]
        d = paired_delta(rows, base)
        assert d["n"] == 2 and d["n_board_days"] == 2
        assert d["mean_delta_pct"] == pytest.approx(1.5)

    def test_unmatched_rows_are_skipped_not_zero_filled(self):
        d = paired_delta([_row("A", "d1", 3.0, 12), _row("Z", "d9", 99.0, 12)],
                         [_row("A", "d1", 1.0, 10)])
        assert d["n"] == 1 and d["mean_delta_pct"] == pytest.approx(2.0)

    def test_single_block_yields_no_interval(self):
        """date_block_ci refuses to fabricate an interval from one block, and
        `separates` must not go true on a None interval."""
        d = paired_delta([_row("A", "d1", 3.0, 12)], [_row("A", "d1", 1.0, 10)])
        assert d["lo_pct"] is None and d["hi_pct"] is None and d["separates"] is False

    def test_separates_flag_tracks_the_sign_of_the_interval(self):
        rows = [_row(f"T{i}", f"d{i % 4}", 10.0, 12) for i in range(40)]
        base = [_row(f"T{i}", f"d{i % 4}", 1.0, 10) for i in range(40)]
        assert paired_delta(rows, base)["separates"] is True
        assert paired_delta(base, base)["separates"] is False


class TestPolicyMetrics:
    def test_counts_censored_rows_and_exit_reasons(self):
        rows = [_row("A", "d1", 1.0, 10), _row("B", "d1", -1.0, 12,
                                                exit_reason=R_DATA_END, censored=True),
                _row("C", "d2", 2.0, 8, exit_reason=R_TRAIL)]
        m = policy_metrics(rows)
        assert m["n_matured"] == 3 and m["n_board_days"] == 2
        assert m["n_censored"] == 1
        assert m["exit_reasons"] == {R_DATA_END: 1, R_HORIZON: 1, R_TRAIL: 1}
        assert m["max_hold"] == 12

    def test_censored_rows_report_the_session_they_were_MARKED_on(self):
        rows = [_row("A", "d1", 1.0, 10, exit_date="2026-07-30"),
                _row("B", "d1", -1.0, 12, exit_reason=R_DATA_END, censored=True,
                     exit_date="2026-07-31")]
        m = policy_metrics(rows)
        assert m["censor_dates"] == ["2026-07-31"]     # only the MARKS, not every exit
        assert m["censored_pct"] == 50.0


class TestCaptureGuard:
    """m17 — realised/MFE is meaningless when MFE <= 0; the row is null, not a number."""

    def _row_with(self, mfe, pnl):
        return _row("A", "d1", pnl, 10, mfe=mfe, mae=min(mfe, pnl) - 1.0)

    def test_a_negative_mfe_row_yields_a_null_capture_not_a_flattering_ratio(self):
        rows = [self._row_with(mfe=-3.0, pnl=-5.0)]
        # The defect being fixed: summarize's own filter is abs(mfe) > 1e-9, so it divides
        # two negatives and reports a HEALTHY-LOOKING +1.67 for a position that never once
        # traded above its entry.
        assert ts.summarize(rows, metric="pnl")["capture"] == pytest.approx(1.67, abs=0.01)
        m = policy_metrics(rows)
        assert m["capture"] is None
        assert (m["n_capture"], m["n_capture_undefined"]) == (0, 1)
        assert m["capture_undefined_pct"] == 100.0

    def test_a_zero_mfe_row_is_also_undefined(self):
        m = policy_metrics([self._row_with(mfe=0.0, pnl=-2.0)])
        assert m["capture"] is None and m["n_capture_undefined"] == 1

    def test_the_median_is_taken_over_the_defined_rows_only(self):
        rows = [self._row_with(mfe=10.0, pnl=5.0),      # capture 0.50
                self._row_with(mfe=4.0, pnl=1.0),       # capture 0.25
                self._row_with(mfe=-3.0, pnl=-5.0)]     # undefined, must not shift it
        m = policy_metrics(rows)
        assert m["capture"] == pytest.approx(0.38)      # median(0.50, 0.25), rounded
        assert (m["n_capture"], m["n_capture_undefined"]) == (2, 1)
        # Keeping the undefined row would make the meaningless +1.67 the MEDIAN.
        assert ts.summarize(rows, metric="pnl")["capture"] == pytest.approx(0.50)


# --------------------------------------------------------------------------- #
# synthetic cohort — the trough stop and the excursion window, end to end
# --------------------------------------------------------------------------- #
_HIST = 130          # < 200 bars, so _ob_mask returns None and P0 keeps only its stop leg


def _synthetic_cohort(forward: list[float], *, flat: float = 100.0, n_hist: int = _HIST):
    """One episode on a flat history, with a forward path chosen by the caller.

    Flat history => the 90-session trough IS ``flat``, so the incumbent's stop level is
    exactly ``flat * _TROUGH_TOL`` and a test can place a close on either side of it.
    """
    idx = pd.bdate_range("2026-01-01", periods=n_hist + 1 + len(forward))
    close = pd.Series([flat] * n_hist + [flat] + list(forward), index=idx, dtype=float)
    tk = "SYN"
    closes = close.to_frame(tk)
    highs, lows = (close + 0.5).to_frame(tk), (close - 0.5).to_frame(tk)
    board_date = str(idx[n_hist - 1].date())          # fill prints on the NEXT session
    cohort, _excl = build_cohort({board_date: {tk}}, {}, closes, highs, lows)
    return cohort


class TestTroughStopTolerance:
    """m16 — `_TROUGH_TOL` is load-bearing, so both sides of it are exercised.

    The incumbent stops out on a break of the 90-session trough × 0.97, NOT on a break of
    the trough. On a flat-100 history the two levels are 97.00 and 100.00, and the gap
    between them is the tolerance. Delete it (TOL = 1.0) and the second test below fires
    a stop that should not exist; widen it and the first stops firing.
    """

    def test_the_stop_level_is_the_trough_times_the_tolerance(self):
        ep = _synthetic_cohort([100.0] * 11)[0]
        assert ep["trough_stop"] == pytest.approx(100.0 * _TROUGH_TOL)
        assert _TROUGH_LB >= 10                        # the lookback must cover the flat

    def test_a_close_below_trough_x_tol_fires_the_stop(self):
        stop = 100.0 * _TROUGH_TOL
        fwd = [100.0, 100.0, stop - 0.01] + [100.0] * 8
        row = evaluate(_synthetic_cohort(fwd), None)["P0"][0]
        assert (row["exit_reason"], row["held"]) == ("stop", 3)

    def test_a_close_below_the_TROUGH_but_above_trough_x_tol_does_NOT_fire(self):
        """The tolerance is the whole point: 98.00 breaks the trough and is not a break.

        With `_TROUGH_TOL = 1.0` this episode would stop out on bar 3 instead of running
        to its horizon, and this test is what says so.
        """
        stop = 100.0 * _TROUGH_TOL
        below_trough = (stop + 100.0) / 2.0            # strictly between 97 and 100
        fwd = [100.0, 100.0, below_trough] + [100.0] * 8
        row = evaluate(_synthetic_cohort(fwd), None)["P0"][0]
        assert (row["exit_reason"], row["held"]) == (R_HORIZON, LEDGER_HORIZON)

    def test_a_close_exactly_at_the_stop_level_holds(self):
        """The grader's leg is `p < stop_level`. A touch is not a break."""
        fwd = [100.0, 100.0, 100.0 * _TROUGH_TOL] + [100.0] * 8
        row = evaluate(_synthetic_cohort(fwd), None)["P0"][0]
        assert row["exit_reason"] == R_HORIZON


class TestExcursionWindowIsShared:
    """M6 — one MFE/MAE/capture window for the whole headline table, P0 included."""

    def test_excursions_cover_the_held_window_only(self):
        ep = _synthetic_cohort([101.0, 102.0, 130.0] + [100.0] * 8)[0]
        mfe, mae = excursions(ep, 2)
        assert mfe == pytest.approx(2.0)               # bar 3's +30% is NOT in the window
        assert mae == pytest.approx(1.0)

    def test_P0_takes_its_excursions_from_its_own_hold_not_the_full_horizon(self):
        """MUTATION PIN for the unification.

        P0 stops out on bar 3 and the name then rallies 30% inside the same 10-bar
        forced-verdict window. `track_scoring.score_from_fill` — which still supplies
        P0's P&L — reports that 30% as the episode's MFE. Reading P0's mfe/mae from the
        grader again (`row["mfe"] = sc["mfe"]`) makes this test red, because the headline
        table would once more be mixing two window conventions.
        """
        stop = 100.0 * _TROUGH_TOL
        fwd = [101.0, 102.0, stop - 0.01, 130.0, 130.0, 130.0,
               130.0, 130.0, 130.0, 130.0, 130.0]
        cohort = _synthetic_cohort(fwd)
        row = evaluate(cohort, None)["P0"][0]
        assert (row["exit_reason"], row["held"]) == ("stop", 3)
        assert row["mfe"] == pytest.approx(2.0)        # best close WHILE HELD, not +30%
        assert row["mae"] == pytest.approx((stop - 0.01) / 100.0 * 100.0 - 100.0)
        grader = ts.score_from_fill(cohort[0]["series"],
                                    cohort[0]["series"].index[cohort[0]["i_fill"]],
                                    100.0, LEDGER_HORIZON,
                                    stop_level=cohort[0]["trough_stop"])
        assert grader["mfe"] == pytest.approx(30.0)    # the definition NOT used here
        assert row["pnl"] == pytest.approx(grader["pnl"])      # P&L still the grader's
        assert row["held"] == grader["held"]

    def test_every_policy_row_uses_the_same_window_definition(self):
        cohort = _synthetic_cohort([101.0, 102.0, 103.0] + [104.0] * 8)
        pol = evaluate(cohort, None)
        for key, rows in pol.items():
            r = rows[0]
            mfe, mae = excursions(cohort[0], int(r["held"]))
            assert r["mfe"] == pytest.approx(mfe), key
            assert r["mae"] == pytest.approx(mae), key


# --------------------------------------------------------------------------- #
# real-data integration
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def study():
    return run_study()


class TestCalibration:
    def test_p0_reproduces_the_shipped_ledger_key_for_key(self, study):
        """G3's calibration check. P0 is the incumbent rule run through track_scoring on
        the ledger's own cohort, so any non-zero delta means the reconstruction drifted —
        not that the cohorts differ."""
        cal = study["calibration"]
        if not cal["shipped"]:
            pytest.skip("site/factordata/us_track_ledger.json absent")
        bad = {k: v for k, v in cal["deltas"].items() if v not in (0, 0.0)}
        assert not bad, f"calibration drifted on {bad}"
        assert cal["exact_match"] is True

    def test_the_headline_keys_are_actually_present(self, study):
        """Guards the vacuous pass: an all-None delta dict would satisfy the loop above
        without comparing anything."""
        cal = study["calibration"]
        if not cal["shipped"]:
            pytest.skip("ledger absent")
        for key in ("n_matured", "win_pct", "expectancy_pct", "profit_factor"):
            assert cal["shipped"].get(key) is not None
            assert cal["rebuilt"].get(key) is not None


class TestCohortAndDisclosure:
    def test_every_policy_runs_the_IDENTICAL_cohort(self, study):
        n = study["cohort"]["n_episodes"]
        assert n > 0
        for k in POLICY_KEYS:
            assert study["metrics"][k]["n_matured"] == n, f"{k} lost episodes"

    def test_every_exclusion_reason_is_counted(self, study):
        counts = study["exclusions"]["counts"]
        for key in ("no_price_column", "empty_series", "fill_not_printed",
                    "immature", "no_atr", "bad_entry"):
            assert key in counts and isinstance(counts[key], int)

    def test_no_price_exclusions_name_their_tickers(self, study):
        n = study["exclusions"]["counts"]["no_price_column"]
        if n:
            assert study["exclusions"]["tickers"]["no_price_column"], \
                "a disclosed count with no names is not a disclosure"

    def test_ladder_prints_every_rung_including_the_empty_one(self, study):
        """NEVER silently truncate: the 63 rung must appear with its real count even when
        that count is zero."""
        for h in HORIZON_LADDER:
            assert h in study["ladder"]
            assert study["ladder"][h]["n_episodes"] >= 0
        assert study["ladder"][LEDGER_HORIZON]["n_episodes"] == study["cohort"]["n_episodes"]

    def test_censored_rows_are_marked_not_dropped(self, study):
        """A cap-63 policy on a record this young must carry data_end rows; if it carried
        none, something dropped them — the outcome-conditioned denominator rule 1
        forbids."""
        m = study["metrics"]["P2k3"]
        assert m["n_censored"] + sum(
            v for k, v in m["exit_reasons"].items() if k != R_DATA_END) == m["n_matured"]

    def test_cohort_board_days_are_reported_beside_episode_count(self, study):
        assert study["cohort"]["n_board_days"] >= 1
        assert study["cohort"]["n_board_days"] < study["cohort"]["n_episodes"]

    def test_p4_is_not_a_clone_of_p2k3_on_the_real_cohort(self, study):
        """The shipped arm level has to actually bind somewhere, or P4 measures nothing."""
        assert (study["metrics"]["P4"]["exit_reasons"]
                != study["metrics"]["P2k3"]["exit_reasons"])


class TestDeterminism:
    def test_two_runs_agree_including_the_seeded_intervals(self):
        a, b = run_study(), run_study()
        for k in POLICY_KEYS:
            assert a["metrics"][k] == b["metrics"][k]
        assert a["deltas_vs_p0"] == b["deltas_vs_p0"]
        assert a["decomposition"] == b["decomposition"]


class TestReport:
    def test_renders_with_the_required_disclosures(self, study):
        md = render_report(study)
        for needle in ("Calibration", "data_end", "n_board_days",
                       "promotion path", "Winners kept vs losers cut",
                       "Horizon ladder", "prereg"):
            assert needle.lower() in md.lower(), f"report is missing {needle!r}"

    def test_makes_no_validation_claim(self, study):
        """check_validated_claims does not scan reports/, so the discipline is pinned
        here instead of relying on a gate that never looks."""
        md = render_report(study).lower()
        assert "validated" not in md
        assert "已验证" not in md and "经验证" not in md

    def test_states_the_63_rung_explicitly_even_at_zero(self, study):
        md = render_report(study)
        n63 = study["ladder"][63]["n_episodes"]
        assert f"**63 sessions: {n63} episodes support it.**" in md

    def test_delta_table_reports_direction_not_just_separation(self, study):
        md = render_report(study)
        assert "excludes 0?" in md
        # A separating policy must be described with a direction word somewhere in Read.
        sep = [k for k, d in study["deltas_vs_p0"].items() if d.get("separates")]
        if sep:
            assert ("ABOVE zero" in md) or ("BELOW zero" in md)


def _section(md: str, heading: str) -> list[str]:
    """The lines of one report section, heading excluded, next same-or-higher stop."""
    lines = md.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == heading)
    depth = heading.split(" ")[0]
    end = len(lines)
    for j in range(start + 1, len(lines)):
        head = lines[j].split(" ")[0]
        if lines[j].startswith("#") and len(head) <= len(depth):
            end = j
            break
    return lines[start + 1:end]


_PP = re.compile(r"([+-]\d+\.\d{2}) pp")


class TestDecompositionTableReconcilesOnThePage:
    """m14 — the printed parts have to add up to the printed net, not just the exact ones.

    Rounding each contribution independently used to print P3 as −0.45 / −0.15 beside a
    net of −0.59 and five parts summing to −0.52 beside a total of −0.53. Exact numbers
    that print as an arithmetic error are not a disclosure.
    """

    def test_printed_parts_sum_to_the_printed_nets(self, study):
        md = render_report(study)
        rows = [l for l in _section(md, "## Winners kept vs losers cut")
                if l.startswith("| P") and "pp<br>" in l]
        assert rows, "no decomposition rows found — did the table move?"
        for line in rows:
            cells = [c.strip() for c in line.strip("|").split("|")]
            nums = [Decimal(_PP.search(c).group(1)) for c in cells[2:]]
            ew, el, wk, cl, cw, lc, same, total = nums
            assert ew + el == wk, f"winners-kept net does not match its parts: {line}"
            assert cl + cw == lc, f"losers-cut net does not match its parts: {line}"
            assert ew + el + cl + cw + same == total, f"parts do not sum to total: {line}"
            assert wk + lc + same == total, f"nets do not sum to total: {line}"

    def test_the_printed_total_matches_the_printed_delta_vs_p0f(self, study):
        """The same number lives in two tables; one rounding, so one figure."""
        md = render_report(study)
        deltas = {}
        for line in _section(md, "## Does anything separate from the incumbent?"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            # 8 columns = the paired-delta table; the sensitivity table below has 5.
            if line.startswith("| P") and len(cells) == 8:
                m = _PP.search(cells[5])              # the Δ-vs-P0f cell
                if m:
                    deltas[cells[0]] = Decimal(m.group(1))
        assert deltas, "no Δ-vs-P0f cells parsed — did the delta table change shape?"
        for line in _section(md, "## Winners kept vs losers cut"):
            if line.startswith("| P") and "pp<br>" in line:
                cells = [c.strip() for c in line.strip("|").split("|")]
                total = Decimal(_PP.search(cells[-1]).group(1))
                if cells[0] in deltas:
                    assert deltas[cells[0]] == total, f"two roundings of {cells[0]}"


class TestPrintedDisclosures:
    """The caveats a reader must not be able to miss — printed WHERE they bite."""

    def test_the_overlap_caveat_sits_beside_every_bolded_excludes_0_flag(self, study):
        """B4 — a reader who only sees the bold flag has to see the caveat too."""
        lines = render_report(study).splitlines()
        flags = [i for i, l in enumerate(lines) if "**yes**" in l]
        assert flags, "no separating policy in this run — the adjacency is untestable"
        for i in flags:
            near = " ".join(lines[i:i + 12]).lower()
            assert "blocks overlap" in near, \
                f"line {i} bolds a separation with no overlap caveat within 12 lines"

    def test_the_overlap_caveat_also_has_its_own_stats_section(self, study):
        md = render_report(study)
        ov = study["window_overlap"]
        assert f"blocks are not {ov['n_board_days']} independent bets" in md
        assert "effective sample is materially smaller" in md
        assert f"{ov['max_disjoint_windows']} of the {ov['n_board_days']} board days" in md

    def test_the_close_only_stop_convention_is_in_method_AND_limitations(self, study):
        """M5 — one disclosure in each place a reader might start."""
        md = render_report(study)
        method = " ".join(_section(md, "## Method — the conventions that decide the numbers"))
        limits = " ".join(_section(md, "## Limitations"))
        sc = study["stop_convention"]
        for text in (method, limits):
            assert "close-only" in text.lower()
            assert f"{sc['slip_mean_pct']:.2f}%" in text, "the measured slip is not printed"
            assert str(sc["n_stop_exits"]) in text
        assert f"{sc['intraday_earlier_pct_of_stops']:.1f}%" in method
        assert str(sc["n_held_through_intraday_breach"]) in method

    def test_the_terminal_mark_concentration_sits_beside_the_delta_table(self, study):
        """M4 — the marks all land on one session, and the sensitivity says what that buys."""
        sec = " ".join(_section(md := render_report(study),
                                "## Does anything separate from the incumbent?"))
        dates = sorted({d for k in POLICY_KEYS
                        for d in study["metrics"][k]["censor_dates"]})
        assert dates, "no data_end marks in this run"
        for d in dates:
            assert d in sec
        assert "not spread across the sample" in sec
        assert "One-session-back sensitivity" in sec
        assert f"{study['sensitivity']['max_abs_shift_pp']:.2f} pp" in sec
        assert "## Limitations" in md

    def test_censoring_rates_are_repeated_on_BOTH_tables(self, study):
        """m17c — a reader of either table has to meet the censoring rate."""
        md = render_report(study)
        for heading in ("## Does anything separate from the incumbent?",
                        "## Winners kept vs losers cut"):
            sec = _section(md, heading)
            rows = [l for l in sec if l.startswith("| P")]
            assert rows
            for k in POLICY_KEYS:
                m = study["metrics"][k]
                if m["n_censored"]:
                    stamp = f"{m['n_censored']} ({m['censored_pct']:.0f}%)"
                    assert any(stamp in l for l in rows), f"{k} in {heading}: {stamp}"

    def test_capture_nulls_are_printed_not_hidden(self, study):
        """m17 — a null disclosed as a count is the compliant form; a null averaged in
        as a positive-looking ratio is not."""
        md = render_report(study)
        assert "MFE ≤ 0" in md
        for k in POLICY_KEYS:
            n = study["metrics"][k]["n_capture_undefined"]
            if n:
                assert f"{POLICY_SHORT[k]} {n}" in md


class TestReportWording:
    def test_forward_bar_counts_say_AT_LEAST(self, study):
        """The ladder counts episodes with >= h bars; printing "have h bars" is wrong."""
        md = render_report(study)
        n = study["ladder"][LEDGER_HORIZON]["n_episodes"]
        assert f"**{n} have at least {LEDGER_HORIZON} forward bars**" in md
        assert "AT LEAST that many forward bars" in md

    def test_the_early_leg_counts_reconcile_with_the_exit_reason_mix(self, study):
        """The "89 + 1" figure. `before` + `on the horizon bar` must equal the mix, and
        `before` must equal what the decomposition buckets as "cut"."""
        legs, mix = study["p0_early_legs"], study["metrics"]["P0"]["exit_reasons"]
        for reason in set(legs["before"]) | set(legs["on_horizon_bar"]):
            assert (legs["before"].get(reason, 0)
                    + legs["on_horizon_bar"].get(reason, 0)) == mix[reason], reason
        cut = study["decomposition"]["P0"]["buckets"]
        assert legs["n_before"] == cut["cut_loser"]["n"] + cut["cut_winner"]["n"]
        md = render_report(study)
        assert f"exit {legs['n_before']} of the" in md
        if legs["n_on_horizon_bar"]:
            assert f"a further {legs['n_on_horizon_bar']} fire ON bar" in md

    def test_the_data_edge_paragraph_states_an_unknown_direction_not_a_double_negative(
            self, study):
        md = render_report(study)
        assert "biases nothing in a known direction" not in md
        assert "Which way that pushes the estimate is unknown" in md


class TestCommittedReportIsCurrent:
    def test_the_committed_report_matches_a_fresh_render(self, study):
        """The report is a committed artifact; a stale one is a wrong one. Only the
        generated-at stamp may differ."""
        path = Path(__file__).resolve().parent.parent / "reports" / "exit-policy-horserace.md"
        if not path.exists():
            pytest.skip("report not committed yet")
        fresh = render_report(study).splitlines()
        on_disk = path.read_text().splitlines()
        strip = lambda ls: [l for l in ls if "**Study date:**" not in l]  # noqa: E731
        assert strip(fresh) == strip(on_disk), \
            "reports/exit-policy-horserace.md is stale — re-run scripts/exit_policy_study.py"
