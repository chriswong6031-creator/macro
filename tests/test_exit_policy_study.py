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
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.exit_policy_study import (  # noqa: E402
    BE_ARM_ATR,
    CAP_PLAN,
    CAP_TRAIL,
    HORIZON_LADDER,
    LEDGER_HORIZON,
    POLICY_KEYS,
    PLAN_ATR_MULT,
    PLAN_R_MULT,
    R_DATA_END,
    R_HORIZON,
    R_PLAN_STOP,
    R_PLAN_TARGET,
    R_TRAIL,
    _plan_geometry,
    decompose,
    paired_delta,
    policy_metrics,
    render_report,
    run_study,
    walk_fixed,
    walk_target_stop,
    walk_trail,
    wilder_atr,
)


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
