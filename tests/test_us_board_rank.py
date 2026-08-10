"""tests/test_us_board_rank.py — engine/us_board_rank.py (us_prophet_v1).

Spec: research/PROPHET_BOARD_PRIORITY_ENGINE_MASTERPLAN_BY_FABLE.md §3.
Evidence for the design choices: research/US_BOARD_MEASUREMENT.md §1/§3/§5.

The frozen constants are pinned by VALUE, not recomputed from the module, so a
silent re-tune of a weight or a map entry fails here instead of shipping.
"""
from __future__ import annotations

import json

import pytest

from engine import us_board_rank as ubr


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _verdict(tier="T2", ticks=1, *, provisional=False, eligible=True,
             above200=True, weekly_bull=True, asof=None, last=None):
    v = {"eligible": eligible, "tier_cascade": tier, "ticks": ticks,
         "provisional": provisional, "above200": above200,
         "weekly_bull": weekly_bull}
    if asof is not None:
        v["asof"] = asof
    if last is not None:
        v["last"] = last
    return v


def _row(ticker="AAA", *, status="buy_now", tier="T2", ticks=1, alpha=1.0,
         sector="Information Technology", provisional=False, ext_z=None,
         coiled=None, asof="2026-07-31", **extra):
    row = {
        "ticker": ticker,
        "name": f"{ticker} Inc",
        "sector": sector,
        "alpha": alpha,
        "entry_signal": {"status": status},
        "signal": _verdict(tier, ticks, provisional=provisional, asof=asof),
    }
    if ext_z is not None:
        row["ext_z"] = ext_z
    if coiled is not None:
        row["coiled"] = coiled
    row.update(extra)
    return row


def assert_runway_coverage_consistent(board, rows):
    """The era-independent M1 contract: the artifact's disclosed runway coverage must
    DESCRIBE the rows it shipped with.

    Deliberately not "the leg is dead" — deadness was a property of one wiring era
    (the builder's extension panel mixed the equity calendar with 24/7 crypto, so on
    any non-session build date every equity's `ext_z` was NaN and no board row carried
    the leg's input).  A test pinned to `nonzero == 0` goes red on the next render for
    the RIGHT behaviour, which is a time bomb rather than a guard.

    Returns the recomputed bucket so callers can assert further on it.
    """
    recomputed = ubr.component_coverage(rows)["runway"]
    assert recomputed["n"] == len(board["buy"]), (
        "every buy row must be scored on runway — a row missing the component reads "
        "as 'not measured', which is a different claim from 'measured zero'")
    ranking = board.get("ranking")
    if ranking is None:
        # Artifact predates us_prophet_v1: the board gained its `ranking` block in
        # #4331. Pin the absence explicitly rather than skipping silently — when a
        # render writes the block this branch stops firing and the comparison below
        # takes over, with no wall-clock or "is it a weekday" dependence.
        assert "ranking" not in board, "ranking present but null — unexpected shape"
        return recomputed
    disclosed = ranking["component_coverage"]["runway"]
    assert disclosed == recomputed, (
        f"the artifact discloses runway coverage {disclosed} but its own buy rows "
        f"score {recomputed} — the receipt drifted from the board it describes")
    return recomputed


# ---------------------------------------------------------------------------
# 1. frozen constants
# ---------------------------------------------------------------------------

class TestFrozenConstants:
    def test_weights_sum_to_100_and_hold_their_split(self):
        assert ubr.SCORE_WEIGHTS == {
            "signal": 30.0, "entry": 25.0, "edge": 25.0,
            "runway": 10.0, "quality": 10.0,
        }
        assert sum(ubr.SCORE_WEIGHTS.values()) == 100.0

    def test_definition_string(self):
        """The ERA FENCE.  Bumped v1 -> v2 on 2026-08-10 with the ratified counter-trend
        reclaim waiver (`research/RECLAIM_VETO_CONDITIONAL_PREREG.md` §4 Arm P / §5, notch
        20; fence pre-specified by `research/prophet_us_audit/RECLAIM_VETO_PACKET_
        2026-08-05.md` §7).  An ADMISSION change makes v1 and v2 different products, so this
        string is what keeps their forward ledgers from pooling — the same move HK made at
        `hk_prophet_v2` (#4470).  Do not update this assertion to match the constant without
        a ratified admission change to point at."""
        assert ubr.BOARD_DEFINITION == "us_prophet_v2"

    def test_the_displaced_era_stamp_was_appended_in_the_same_pr(self):
        """A bump that forgets the displaced stamp orphans every row already written under
        it: #4509 did exactly that on the CN board and 72 rows fell out of every cohort
        (`scripts/build_china_library._CN_SUPERSEDED_ERA_STAMPS` carries that scar).  The
        live stamp must never appear in the superseded list, and the list must never be
        empty once a bump has happened."""
        assert "us_prophet_v1" in ubr.SUPERSEDED_ERA_STAMPS
        assert ubr.BOARD_DEFINITION not in ubr.SUPERSEDED_ERA_STAMPS
        assert len(set(ubr.SUPERSEDED_ERA_STAMPS)) == len(ubr.SUPERSEDED_ERA_STAMPS)

    def test_the_waiver_that_earned_the_bump_is_wired_to_the_ratified_notch(self):
        """The fence and the admission change are one act — a stamp bump with no waiver
        behind it (or a waiver at an unratified notch) is a fence around nothing."""
        from engine import signal_quality as sq
        assert sq.WASHOUT_NOTCH == "20"
        assert sq.RECLAIM_WAIVED and sq.RECLAIM_WAIVED != sq.CT_RECLAIM_FAIL

    def test_caps(self):
        assert (ubr.FEATURED_CAP, ubr.SECTOR_CAP, ubr.RAN_CAP) == (12, 4, 12)

    def test_conviction_has_zero_score_authority(self):
        """The measured anti-predictive leg must be named as scoreless, explicitly."""
        assert "conviction_composite" in ubr.ZERO_SCORE_AUTHORITY
        assert "theme" in ubr.ZERO_SCORE_AUTHORITY

    def test_score_copy_carries_no_forecast_claim(self):
        text = ubr.SCORE_KIND.lower()
        assert "priority" in text
        assert "not a calibrated return forecast" in text
        for banned in ("validated", "win rate", "win-rate", "expected return"):
            assert banned not in text


# ---------------------------------------------------------------------------
# 2. score legs — frozen values
# ---------------------------------------------------------------------------

class TestSignalLeg:
    @pytest.mark.parametrize("tier,expected", [
        ("T2", 1.0), ("T1", 0.9), ("T3", 0.7), ("T4", 0.0), (None, 0.0),
    ])
    def test_tier_base(self, tier, expected):
        assert ubr.signal_value(_verdict(tier, ticks=1)) == pytest.approx(expected)

    def test_provisional_costs_a_tenth(self):
        assert ubr.signal_value(
            _verdict("T2", 1, provisional=True)) == pytest.approx(0.9)

    def test_two_ticks_decays_fifteen_percent(self):
        assert ubr.signal_value(_verdict("T2", 2)) == pytest.approx(0.85)
        assert ubr.signal_value(_verdict("T1", 2)) == pytest.approx(0.9 * 0.85)

    def test_ticks_zero_is_the_freshest_and_is_not_decayed(self):
        """ticks == 0 is a same-day cross. Truthiness testing would decay it."""
        assert ubr.signal_value(_verdict("T2", 0)) == pytest.approx(1.0)

    def test_one_and_three_ticks_are_not_decayed(self):
        assert ubr.signal_value(_verdict("T2", 1)) == pytest.approx(1.0)
        assert ubr.signal_value(_verdict("T2", 3)) == pytest.approx(1.0)

    def test_empty_verdict_scores_zero(self):
        assert ubr.signal_value(None) == 0.0
        assert ubr.signal_value({}) == 0.0


class TestEntryLeg:
    def test_the_admissible_statuses_are_flat(self):
        """NEUTRALITY IS THE RULING — this test exists to fail on any re-introduced
        ordering, in EITHER direction.

        Era history, because this constant has now been all four things:
          * pre-2026-08-04 the US and CN maps were IDENTICAL, on the premise that
            the entry-status vocabulary is market-independent;
          * 2026-08-04 the CN V1 loser audit refuted that premise for the VALUES —
            in the legacy split-adjusted A-share comparator the patience statuses were
            the era's best cohort
            (bounce_wait 6.9% loser rate) and the action statuses its worst
            (buy_now 30.0%; CN masterplan §2.3/§2.11).  This was ordinary return
            context, not exact legal-band evidence.  cn_prophet_v3 adopted that
            order; the US map kept the trend-tape order;
          * 2026-08-08, first draft of A2: the US map adopted the CN ordering on
            the parity anatomy's evidence.  It never reached main;
          * 2026-08-08, this amendment: the §6.6 US re-measurement's first run
            (`research/prophet_us_audit/US_STATUS_REMEASUREMENT_2026-08-08.md`,
            2,816 statused episodes, 23 board dates 06-15..07-30) read ADVERSE —
            buy lane H=5 `bounce_wait` 54.9% loser (n=153) vs `buy_now` 39.0%
            (n=95), H=10 `bounce_wait` 65.4% (n=52), and the watch lane repeating
            55.3% (n=76) on an independent population.  AND `bounce_wait` has ZERO
            marks at H=21 anywhere out of 345 episodes, with H=63 never matured for
            any status — so the horizon the patience thesis actually claims has no
            US data at all.

        The short ruler refutes the CN order; the right ruler is unmeasured.  So the
        map claims NOTHING about the order among admissible statuses, and this test
        is what keeps it that way.  Re-introducing an ordering — patience-first,
        chase-first, or any other — must go through the pre-registered revision rule
        in the module comment (chartered horizon, n >= 50 per cell, sign-stable
        across two half-splits, on `anticipation-v1` era-stamped episodes), not
        through an edit that quietly greens this file.
        """
        values = [ubr._ENTRY_VALUE[s] for s in ubr.ENTRY_NEUTRAL_STATUSES]
        assert ubr.ENTRY_NEUTRAL_STATUSES == (
            "bounce_wait", "wait_pullback", "hold", "buy_now", "partial")
        assert set(values) == {ubr.ENTRY_NEUTRAL_VALUE}, dict(
            zip(ubr.ENTRY_NEUTRAL_STATUSES, values))
        # Named both ways round, so a failure reads as the ruling rather than as a
        # number mismatch: neither end of the old argument may reappear.
        assert ubr._ENTRY_VALUE["bounce_wait"] == ubr._ENTRY_VALUE["buy_now"]
        assert ubr._ENTRY_VALUE["hold"] == ubr._ENTRY_VALUE["partial"]

    def test_the_flat_leg_still_separates_admissible_from_the_rest(self):
        """Falsifier: flat must not mean INERT.  If every status collapsed to one
        value the leg would carry no information at all — what it still says is
        "this row is in the admissible set", and that claim is measured upstream by
        the confluence gate rather than by the §6.6 ledger."""
        for status in ubr.ENTRY_NEUTRAL_STATUSES:
            for other in ("later", "await", "await_confluence", "watch", "buy_soon",
                          "extended", "topping", "blocked", "exit", "avoid"):
                assert ubr._ENTRY_VALUE[status] > ubr._ENTRY_VALUE[other], (
                    status, other)

    def test_the_neutral_cohort_matches_the_featured_set_today(self):
        """The two sets coincide, and they are separate constants on purpose —
        "which statuses may be featured" and "which statuses the evidence cannot
        rank" are different questions.  Pinned so the day they diverge it is a
        decision someone made, not a drift nobody saw."""
        assert set(ubr.ENTRY_NEUTRAL_STATUSES) == ubr._FEATURED_ENTRY_STATUSES

    def test_the_flat_level_keeps_the_attainable_range_and_deflates_nothing(self):
        """The LEVEL is a downstream-safety choice, pinned separately from the ruling.

        Neutrality is the five being EQUAL; it holds at any value.  1.0 is chosen so
        that (a) the attainable range stays 0-100 rather than stepping every score
        down for no informational reason, and (b) no consumer holding an ABSOLUTE
        score floor — a featured requirement, a caution-mode conviction floor, a
        downstream chip cutoff — sees the confirmation class silently deflated under
        it.  At the 0.75 this briefly carried, `buy_now` lost 6.25 points and
        `partial` 3.75 against the pre-era map; both are pinned below as zero-or-lift.

        THE FENCE COVERS EVERY STATUS, NOT ONLY THE ADMISSIBLE FIVE (orchestrator
        ruling 2026-08-09).  It used to loop over `ENTRY_NEUTRAL_STATUSES` and then
        assert that `buy_soon` had gone DOWN — which excluded from the "nothing
        deflates" claim the one status that deflated, by construction.  A guard that
        exempts the case it exists to catch is not a guard.  `buy_soon` 0.8 -> 0.35 was
        CN-derived (CN's table puts it near the bottom) and this module's whole
        argument is that CN's status VALUES do not transfer to the US tape — the §6.6
        re-measurement refuted the transfer at H=5/H=10.  It is also outside the five
        statuses §6.6 ranges over, so it sits under "refused-class values unchanged".
        Restored to 0.8, and the fence now ranges over the WHOLE map: no status, in any
        class, may score below its pre-era value without its own US measurement.
        """
        ceiling = sum(
            ubr.SCORE_WEIGHTS[leg] * (ubr.ENTRY_NEUTRAL_VALUE if leg == "entry" else 1.0)
            for leg in ubr.SCORE_WEIGHTS)
        assert ceiling == pytest.approx(100.0)

        # NO status may score below what the pre-era trend-tape map paid it — the
        # leg-level constant must not move a row across a threshold it cannot see, and
        # a refused-class row's score is as visible to a downstream floor as an
        # admissible one's.  These are the pre-era values, quoted so the comparison is a
        # fact in this file rather than an appeal to git history.
        pre_era = {"buy_now": 1.0, "partial": 0.9, "buy_soon": 0.8, "hold": 0.65,
                   "wait_pullback": 0.55, "later": 0.55, "await": 0.45,
                   "await_confluence": 0.45, "watch": 0.4, "bounce_wait": 0.35,
                   "extended": 0.0, "topping": 0.0, "blocked": 0.0, "exit": 0.0,
                   "avoid": 0.0}
        assert set(pre_era) == set(ubr._ENTRY_VALUE), (
            "a status was added or removed — decide its pre-era baseline explicitly "
            "rather than letting it fall outside this fence")
        for status, was in pre_era.items():
            assert ubr._ENTRY_VALUE[status] >= was, (
                f"{status} deflated {was} -> {ubr._ENTRY_VALUE[status]}; the §6.6 "
                "ruling moves the five admissible statuses UP and moves nothing down")
        # `buy_now` specifically holds station: byte-identical, so a row that was on a
        # floor before is still exactly on it.
        assert ubr._ENTRY_VALUE["buy_now"] == pre_era["buy_now"]
        # ... and so does `buy_soon`, the one this fence used to exempt.  Named
        # explicitly so a re-attempted CN-derived demotion fails on the ruling rather
        # than on an anonymous loop iteration.
        assert ubr._ENTRY_VALUE["buy_soon"] == pre_era["buy_soon"] == 0.8

    def test_the_values_are_the_v1_constants(self):
        """The VALUES, pinned separately from the flatness — the revision rule may
        move the numbers (all five together) without touching the ruling above, and
        the two failures should be readable apart."""
        assert ubr._ENTRY_VALUE == {
            "bounce_wait": 1.0,
            "wait_pullback": 1.0,
            "hold": 1.0,
            "buy_now": 1.0,
            "partial": 1.0,
            "later": 0.55,
            "await": 0.45,
            "await_confluence": 0.45,
            "watch": 0.4,
            "buy_soon": 0.8,
            "extended": 0.0,
            "topping": 0.0,
            "blocked": 0.0,
            "exit": 0.0,
            "avoid": 0.0,
        }
        assert ubr.ENTRY_NEUTRAL_VALUE == 1.0

    def test_the_vocabulary_is_shared_with_china_but_the_map_is_not_a_copy(self):
        """One status set, two different maps — and from 2026-08-08 they are not even
        the same KIND of map.  CN's is an ordering measured on CN episodes; the US
        one declines to order.  A future "just import CN's map" shortcut has to be a
        decision rather than an accident, and importing it would now also import a
        claim the US ledger has refuted at H=5/H=10."""
        from engine import china_board_rank as cn

        assert set(ubr._ENTRY_VALUE) == set(cn._ENTRY_VALUE)
        assert ubr._ENTRY_VALUE != cn._ENTRY_VALUE
        assert ubr._ENTRY_VALUE["extended"] == 0.0 and cn._ENTRY_VALUE["extended"] == 0.3
        # The historical CN adjusted-return comparator still orders patience first —
        # context only, with no legal-band or US-map authority.
        assert max(cn._ENTRY_VALUE, key=cn._ENTRY_VALUE.get) == "bounce_wait"
        # ... and the US map no longer has a single leader at all.
        top = max(ubr._ENTRY_VALUE.values())
        assert sum(1 for v in ubr._ENTRY_VALUE.values() if v == top) == 5

    @pytest.mark.parametrize("status,expected", [
        ("bounce_wait", 1.0), ("wait_pullback", 1.0), ("hold", 1.0),
        ("buy_now", 1.0), ("partial", 1.0), ("await_confluence", 0.45),
        ("watch", 0.4), ("buy_soon", 0.8),
        ("extended", 0.0), ("topping", 0.0), ("blocked", 0.0), ("avoid", 0.0),
    ])
    def test_values(self, status, expected):
        assert ubr.entry_value({"status": status}) == pytest.approx(expected)

    def test_unknown_and_missing_score_zero(self):
        assert ubr.entry_value({"status": "banana"}) == 0.0
        assert ubr.entry_value({}) == 0.0
        assert ubr.entry_value(None) == 0.0

    def test_status_is_case_insensitive(self):
        assert ubr.entry_value({"status": "BOUNCE_WAIT"}) == pytest.approx(1.0)
        assert ubr.entry_value({"status": "BUY_NOW"}) == pytest.approx(1.0)


class TestEdgeLeg:
    def test_top_of_pool_is_full_credit_bottom_is_zero(self):
        rows = [_row("A", alpha=3.0), _row("B", alpha=1.0), _row("C", alpha=-1.0)]
        pct = ubr.alpha_percentiles(rows)
        assert pct[0] == pytest.approx(1.0)
        assert pct[2] == pytest.approx(0.0)
        assert ubr.edge_value(pct[0]) == pytest.approx(1.0)
        assert ubr.edge_value(pct[2]) == pytest.approx(0.0)

    def test_bottom_quartile_earns_nothing(self):
        assert ubr.edge_value(0.24) == 0.0
        assert ubr.edge_value(0.25) == 0.0
        assert ubr.edge_value(0.625) == pytest.approx(0.5)

    def test_missing_alpha_is_out_of_the_pool_and_earns_zero(self):
        rows = [_row("A", alpha=1.0), _row("B", alpha=None), _row("C", alpha=0.0)]
        pct = ubr.alpha_percentiles(rows)
        assert pct[1] is None
        assert ubr.edge_value(pct[1]) == 0.0
        # B did not occupy a rank: A and C still span the full range.
        assert pct[0] == pytest.approx(1.0)
        assert pct[2] == pytest.approx(0.0)

    def test_ties_break_on_ticker_deterministically(self):
        rows = [_row("ZZZ", alpha=1.0), _row("AAA", alpha=1.0)]
        pct = ubr.alpha_percentiles(rows)
        assert pct[1] == pytest.approx(1.0)   # AAA wins the tie
        assert pct[0] == pytest.approx(0.0)

    def test_single_row_pool_has_no_percentile_and_earns_no_edge(self):
        """m3: a cross-section of one has no cross-sectional reading.

        The row is simultaneously the top AND the bottom of its own pool, so 1.0 was
        an artifact of the degenerate pool, not evidence — and it handed the full
        25-point edge leg to a name that had out-ranked nothing.
        """
        pct = ubr.alpha_percentiles([_row("A", alpha=0.1)])
        assert pct[0] is None
        assert ubr.edge_value(pct[0]) == 0.0

    def test_a_lone_scored_row_gets_zero_edge_points_end_to_end(self):
        scored = ubr.score_rows([_row("A", alpha=5.0)], board_asof="2026-07-31")
        assert scored[0]["prophet"]["points"]["edge"] == 0.0
        assert scored[0]["prophet"]["alpha_percentile"] is None

    def test_a_pool_of_two_still_spans_the_full_range(self):
        """The n==1 guard must not swallow the smallest REAL cross-section."""
        pct = ubr.alpha_percentiles([_row("A", alpha=2.0), _row("B", alpha=1.0)])
        assert pct[0] == pytest.approx(1.0) and pct[1] == pytest.approx(0.0)

    def test_one_finite_alpha_among_many_rows_is_still_a_pool_of_one(self):
        """The pool is the SCORED rows, not the row count: two alpha-less rows do not
        turn a single reading into a cross-section."""
        rows = [_row("A", alpha=1.0), _row("B", alpha=None), _row("C", alpha=None)]
        assert ubr.alpha_percentiles(rows) == {0: None, 1: None, 2: None}

    def test_nan_alpha_is_treated_as_missing(self):
        rows = [_row("A", alpha=float("nan")), _row("B", alpha=1.0)]
        assert ubr.alpha_percentiles(rows)[0] is None


class TestRunwayLeg:
    def test_unknown_extension_earns_zero_not_full_marks(self):
        """CN's fail-closed rule: never best-case an unknown."""
        assert ubr.runway_value({"ticker": "A"}) == 0.0

    def test_not_extended_is_full_runway(self):
        assert ubr.runway_value({"ext_z": 0.0}) == pytest.approx(1.0)
        assert ubr.runway_value({"ext_z": -1.5}) == pytest.approx(1.0)

    def test_parabolic_is_no_runway(self):
        assert ubr.runway_value({"ext_z": 2.0}) == 0.0
        assert ubr.runway_value({"ext_z": 4.0}) == 0.0

    def test_linear_between(self):
        assert ubr.runway_value({"ext_z": 1.0}) == pytest.approx(0.5)
        assert ubr.runway_value({"ext_z": 0.5}) == pytest.approx(0.75)

    def test_antichase_flag_overrides_a_benign_ext_z(self):
        assert ubr.runway_value(
            {"ext_z": 0.0, "antichase_shadow_blocked": True}) == 0.0


class TestQualityLeg:
    def test_ladder(self):
        assert ubr.quality_value({"coiled": {"star": True}}) == pytest.approx(1.0)
        assert ubr.quality_value({"coiled": {"coiled": True}}) == pytest.approx(0.8)
        assert ubr.quality_value(
            {"coiled": {"washout_ctx": True}}) == pytest.approx(0.4)
        assert ubr.quality_value({"washout_ctx": True}) == pytest.approx(0.4)
        assert ubr.quality_value({}) == 0.0

    def test_star_outranks_coiled(self):
        assert ubr.quality_value(
            {"coiled": {"star": True, "coiled": True}}) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 3. stage bucketing
# ---------------------------------------------------------------------------

class TestStages:
    @pytest.mark.parametrize("status", ["buy_now", "partial", "buy_soon"])
    def test_live(self, status):
        assert ubr.stage_for({}, {"status": status}) == "live"

    @pytest.mark.parametrize("status", ["await_confluence", "bounce_wait", "watch"])
    def test_setting_up(self, status):
        assert ubr.stage_for({}, {"status": status}) == "setting_up"

    @pytest.mark.parametrize("status", ["extended", "topping", "hold"])
    def test_ran(self, status):
        assert ubr.stage_for({}, {"status": status}) == "ran"

    @pytest.mark.parametrize("status", ["blocked", "exit", "avoid"])
    def test_blocked(self, status):
        assert ubr.stage_for({}, {"status": status}) == "blocked"

    def test_downtrend_with_no_entry_status_is_blocked(self):
        assert ubr.stage_for({"dir": "down"}, {}) == "blocked"
        assert ubr.stage_for({"dir": "down"}, None) == "blocked"

    @pytest.mark.parametrize("status", [
        "buy_now", "partial", "buy_soon",           # would have been live
        "await_confluence", "bounce_wait", "watch",  # would have been setting_up
        "extended", "topping", "hold",               # would have been ran
        "banana", "",                                # unknown -> setting_up default
    ])
    def test_downtrend_blocks_regardless_of_entry_status(self, status):
        """m1 / masterplan §3.1: `blocked` is {blocked, exit, avoid} OR label DOWNTREND,
        and the DOWNTREND clause is UNCONDITIONAL.

        The engine used to apply it only to rows with NO status at all, so a falling
        name carrying `bounce_wait` — the literal catch-the-knife row — rendered in
        `setting_up`, ABOVE the blocked bucket. tests/test_us_board_priority_ui.py's
        `_stage_of` (the rendered-HTML contract) has asserted the unconditional rule
        since it was written; the engine was the side that disagreed.
        """
        assert ubr.stage_for({"dir": "down"}, {"status": status}) == "blocked"
        assert ubr.stage_for({"label": "DOWNTREND"}, {"status": status}) == "blocked"

    def test_downtrend_label_alone_blocks_without_a_dir(self):
        assert ubr.stage_for({"label": "DOWNTREND"}, {"status": "buy_now"}) == "blocked"
        assert ubr.stage_for({"label": "downtrend"}, {}) == "blocked"

    def test_a_suffixed_downtrend_label_still_blocks(self):
        """_enforce_blocked_buy_invariant appends ' (blocked)' to shipped labels — the
        07-31 artifact carries 'UPTREND (blocked)'-shaped strings — so an equality test
        would read a suffixed DOWNTREND as an unknown label."""
        assert ubr.stage_for({"label": "DOWNTREND (blocked)"},
                             {"status": "buy_now"}) == "blocked"
        assert ubr.is_downtrend({"label": "DOWNTREND （受阻）"}) is True

    def test_an_uptrend_row_is_not_downtrended_by_the_label_match(self):
        """Mutation guard: the label test must not fire on every trend label."""
        for label in ("UPTREND", "UPTREND (blocked)", "BOTTOMING", "BUY ZONE",
                      "NEARING A HIGH", "UNCONFIRMED TURN"):
            assert ubr.is_downtrend({"label": label}) is False, label
        assert ubr.stage_for({"label": "UPTREND"}, {"status": "buy_now"}) == "live"

    def test_downtrend_row_scores_and_sorts_into_the_blocked_bucket(self):
        rows = [_row("FALL", status="buy_now", alpha=9.0, dir="down"),
                _row("OK", status="buy_now", alpha=-1.0)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        assert [r["ticker"] for r in scored] == ["OK", "FALL"]
        assert scored[1]["stage"] == "blocked"
        assert scored[1]["featured"] is False

    def test_blocked_status_beats_everything(self):
        assert ubr.stage_for({"dir": "up"}, {"status": "avoid"}) == "blocked"

    def test_unknown_or_missing_status_is_setting_up_never_live(self):
        for entry in ({}, None, {"status": ""}, {"status": "banana"}):
            assert ubr.stage_for({}, entry) == "setting_up"

    def test_stage_rank_order(self):
        ranks = [ubr.stage_rank(s) for s in
                 ("live", "setting_up", "ran", "basing", "blocked")]
        assert ranks == sorted(ranks) == [0, 1, 2, 3, 4]

    def test_unknown_stage_sorts_last(self):
        assert ubr.stage_rank("banana") > ubr.stage_rank("blocked")

    def test_reads_the_row_when_no_entry_is_passed(self):
        assert ubr.stage_for({"entry_signal": {"status": "buy_now"}}) == "live"


# ---------------------------------------------------------------------------
# 3b. the `basing` shelf — BOTTOM WATCH stops hiding inside `blocked` (W-E.1 / D18)
# ---------------------------------------------------------------------------

_BASING = {"bottom_watch_stage": ubr.STAGE_BASING}

# Every other ladder state, as (state, display label) — engine.cycles.STATE_DISPLAY.
# BOTTOM WATCH is deliberately absent: this is the "must NOT fire" list.
_OTHER_LADDER_STATES = [
    ("DECLINE", "DOWNTREND"),
    ("ROLLING OVER", "TOPPING"),
    ("TURN SIGNALED", "BOTTOMING"),
    ("FRESH BUY", "BUY ZONE"),
    ("RALLY ON", "UPTREND"),
    ("TOP WATCH", "NEARING A HIGH"),
    ("COUNTERTREND BOUNCE", "UNCONFIRMED TURN"),
    ("CONFIRMING TURN", "TURN IN PROGRESS"),
]


class TestBasingStage:
    """D18: BOTTOM WATCH carries dir='down', so the DOWNTREND clause swallowed the one
    ladder state that names a name working on a low.  Measured on the board's own
    ledger (data/us_board_ledger/snapshots.jsonl, 2026-06-30..07-31): 41 buy-lane rows
    over 13 of 17 board days, every one filed under `blocked`."""

    def test_bottom_watch_state_routes_to_basing(self):
        row = {"state": "BOTTOM WATCH", "label": "NEARING A LOW", "dir": "down"}
        assert ubr.stage_for(row, {"status": "wait_pullback"}, **_BASING) == "basing"

    def test_the_display_label_alone_is_enough(self):
        """A row carrying only what the template renders still lands on the shelf."""
        assert ubr.stage_for({"label": "NEARING A LOW", "dir": "down"},
                             {"status": "wait_pullback"}, **_BASING) == "basing"

    def test_a_suffixed_bottom_watch_label_still_bases(self):
        """_enforce_blocked_buy_invariant appends the marker AFTER staging, but the
        ledger's own rows carry it (7 of the 41), so re-staging a shipped row must
        agree with what the nightly decided."""
        for label in ("NEARING A LOW (blocked)", "NEARING A LOW （受阻）"):
            assert ubr.is_bottom_watch({"label": label}) is True, label

    @pytest.mark.parametrize("state,label", _OTHER_LADDER_STATES)
    def test_no_other_ladder_state_is_read_as_basing(self, state, label):
        """Mutation guard.  A predicate that answered True for every down row, or for
        every label, would pass the test above and quietly move DECLINE onto the shelf
        this wave exists to keep clean."""
        assert ubr.is_bottom_watch({"state": state, "label": label}) is False

    @pytest.mark.parametrize("state,label", [("DECLINE", "DOWNTREND"),
                                             ("ROLLING OVER", "TOPPING")])
    def test_decline_and_rolling_over_stay_blocked_with_the_shelf_on(self, state, label):
        """The falling knife and the topping roll keep their stand-aside verdict —
        that is the whole point of splitting the bucket rather than widening it."""
        row = {"state": state, "label": label, "dir": "down"}
        assert ubr.stage_for(row, {"status": "wait_pullback"}, **_BASING) == "blocked"
        assert ubr.stage_for(row, {"status": "wait_pullback"}) == "blocked"

    def test_the_default_is_the_pre_basing_behaviour(self):
        """No opt-in, no change: the default protects any caller that has not built
        the shelf, so its rendering stays byte-identical.  Both boards now opt in
        EXPLICITLY at their own builders (US 2026-08-05, HK the same day), which is
        why the opt-in is a parameter and not a flag day — the delegating HK module
        below still reads `blocked` when nobody asks for the shelf."""
        row = {"state": "BOTTOM WATCH", "label": "NEARING A LOW", "dir": "down"}
        assert ubr.stage_for(row, {"status": "wait_pullback"}) == "blocked"
        from engine import hk_board_rank as hbr
        assert hbr.stage_for(row, {"status": "wait_pullback"}) == "blocked"

    @pytest.mark.parametrize("status", ["blocked", "exit", "avoid"])
    def test_an_explicit_blocked_entry_verdict_still_wins(self, status):
        """The entry status is a decision about THIS name; the cycle read is context.
        Ordering the two the other way would let the shelf launder an avoid."""
        row = {"state": "BOTTOM WATCH", "label": "NEARING A LOW", "dir": "down"}
        assert ubr.stage_for(row, {"status": status}, **_BASING) == "blocked"

    def test_basing_sorts_after_ran_and_before_blocked(self):
        assert (ubr.stage_rank("ran") < ubr.stage_rank("basing")
                < ubr.stage_rank("blocked"))

    def test_a_basing_row_is_never_featured(self):
        rows = [_row("BASE", status="buy_now", alpha=9.0, tier="T1", ticks=0,
                     state="BOTTOM WATCH", label="NEARING A LOW", dir="down"),
                _row("OK", status="buy_now", alpha=-1.0)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31", **_BASING)
        by_ticker = {r["ticker"]: r for r in scored}
        assert by_ticker["BASE"]["stage"] == "basing"
        assert by_ticker["BASE"]["featured"] is False
        # R2 names the refusing bucket rather than "not live": after the relax there
        # are three buckets that can refuse and the receipt has to say which one did.
        assert "stage_basing" in by_ticker["BASE"]["featured_blocked_by"]
        # …and it still sorts below the actionable row despite the better score.
        assert [r["ticker"] for r in scored] == ["OK", "BASE"]

    def test_the_shelf_moves_rows_only_between_display_buckets(self):
        """G0.3 population fence, at row grain: the SAME pool through score_rows with
        and without the opt-in differs in exactly one key — ``stage`` — on exactly the
        BOTTOM WATCH rows.  Scores, featured flags and every other stamped field are
        recomputed identically.

        The rendered SEQUENCE does change, and that is the feature, not a leak: a
        basing row now sorts above a blocked one because its shelf sits above the
        blocked shelf.  What must hold is that the new sequence is fully explained by
        the bucket split — same rows, same scores, same within-bucket order — which is
        what the last assertion pins.  ``display_rank``/``score_rank`` are positions,
        so they move with it and are compared separately from the rest of the row.
        """
        def _pool():
            return [
                _row("BASE1", status="wait_pullback", alpha=2.0,
                     state="BOTTOM WATCH", label="NEARING A LOW", dir="down"),
                _row("KNIFE", status="wait_pullback", alpha=1.0,
                     state="DECLINE", label="DOWNTREND", dir="down"),
                _row("BASE2", status="watch", alpha=0.5,
                     state="BOTTOM WATCH", label="NEARING A LOW", dir="down"),
                _row("LIVE", status="buy_now", alpha=3.0, label="BUY ZONE"),
            ]

        before = ubr.score_rows(_pool(), board_asof="2026-07-31")
        after = ubr.score_rows(_pool(), board_asof="2026-07-31", **_BASING)

        moved = {"BASE1", "BASE2"}
        assert {r["ticker"] for r in before if r["stage"] == "blocked"} == (
            moved | {"KNIFE"}), "fixture must exercise the split to mean anything"
        assert {r["ticker"] for r in after if r["stage"] == "basing"} == moved
        assert {r["ticker"] for r in after if r["stage"] == "blocked"} == {"KNIFE"}

        # Membership is untouched, and matched BY TICKER every row is identical
        # except `stage`, the two position stamps, and the stage TOKEN inside
        # `featured_blocked_by` (R2: the veto reason names the refusing bucket, so for
        # a bottom-watch row it moves with the bucket exactly as `stage` does — the
        # featured FLAG below is what must not move, and it does not).
        _positional = {"stage", "display_rank", "score_rank", "featured_blocked_by"}
        by_before = {r["ticker"]: r for r in before}
        by_after = {r["ticker"]: r for r in after}
        assert set(by_before) == set(by_after)
        for tk, lhs in by_before.items():
            rhs = by_after[tk]
            assert rhs["stage"] == ("basing" if tk in moved else lhs["stage"]), tk
            assert {k: v for k, v in lhs.items() if k not in _positional} == {
                k: v for k, v in rhs.items() if k not in _positional}, tk
            # The excluded field is not waved through: the flag is identical, and the
            # ONLY reason that may differ is the stage token.
            assert lhs["featured"] == rhs["featured"], tk
            assert ([r for r in (lhs.get("featured_blocked_by") or [])
                     if not r.startswith("stage_")]
                    == [r for r in (rhs.get("featured_blocked_by") or [])
                        if not r.startswith("stage_")]), tk

        # The new sequence is exactly the old rows re-grouped by the new bucket rank.
        assert [r["ticker"] for r in after] == [
            r["ticker"] for r in sorted(
                before,
                key=lambda r: (ubr.stage_rank(by_after[r["ticker"]]["stage"]),
                               -r["prophet"]["score"], r["ticker"]))]

    def test_stage_counts_and_labels_cover_the_new_bucket(self):
        scored = ubr.score_rows(
            [_row("BASE", status="wait_pullback", state="BOTTOM WATCH",
                  label="NEARING A LOW", dir="down")],
            board_asof="2026-07-31", **_BASING)
        assert ubr.stage_counts(scored)["basing"] == 1
        assert set(ubr.STAGE_LABELS[ubr.STAGE_BASING]) == {"en", "zh"}
        assert ubr.STAGE_LABELS[ubr.STAGE_BASING]["zh"].strip()

    def test_no_buy_word_in_the_basing_label(self):
        """P2 / G0.4: watch-lane vocabulary only — this shelf never makes a claim."""
        text = " ".join(ubr.STAGE_LABELS[ubr.STAGE_BASING].values()).lower()
        for banned in ("buy", "entry", "买入", "入场"):
            assert banned not in text, banned


# ---------------------------------------------------------------------------
# 4. freshness
# ---------------------------------------------------------------------------

class TestFreshness:
    def test_days_since_signal_is_zero_on_the_same_session(self):
        assert ubr.days_since_signal("2026-07-31", "2026-07-31") == 0

    def test_days_since_signal_counts_calendar_days(self):
        assert ubr.days_since_signal("2026-07-29", "2026-07-31") == 2

    def test_days_since_signal_unknown_is_none_not_zero(self):
        assert ubr.days_since_signal(None, "2026-07-31") is None
        assert ubr.days_since_signal("2026-07-31", None) is None
        assert ubr.days_since_signal("not-a-date", "2026-07-31") is None

    def test_verdict_asof_wins_over_the_row(self):
        row = {"signal": {"asof": "2026-07-01"}}
        assert ubr.signal_asof(row, {"asof": "2026-07-31"}) == "2026-07-31"
        assert ubr.signal_asof(row, {}) == "2026-07-01"

    def test_new_flag_is_same_session_only(self):
        rows = ubr.score_rows(
            [_row("A", asof="2026-07-31"), _row("B", asof="2026-07-30")],
            board_asof="2026-07-31")
        by = {r["ticker"]: r for r in rows}
        assert by["A"]["new"] is True and by["A"]["days_since_signal"] == 0
        assert by["B"]["new"] is False and by["B"]["days_since_signal"] == 1

    def test_unknown_signal_date_is_not_new(self):
        rows = ubr.score_rows([_row("A", asof=None)], board_asof="2026-07-31")
        assert rows[0]["new"] is False
        assert rows[0]["days_since_signal"] is None


class TestSignalAgeBasis:
    """m4: `days_since_signal` is read as SESSIONS by templates/stocktable.js
    (`FRESH_DAYS = 2` gates the NEW dot + the fresh-only filter), so the resolver
    answers in sessions when it can and DISCLOSES the basis when it cannot."""

    def test_fresh_bars_is_the_session_answer(self):
        assert ubr.signal_age({"fresh_bars": 13}, "2026-07-01", "2026-07-31") == (
            13, "sessions")

    def test_zero_fresh_bars_is_a_same_session_cross_not_a_missing_reading(self):
        assert ubr.signal_age({"fresh_bars": 0}, "2026-07-01", "2026-07-31") == (
            0, "sessions")

    def test_calendar_is_the_disclosed_fallback(self):
        assert ubr.signal_age({}, "2026-07-29", "2026-07-31") == (2, "calendar")
        assert ubr.signal_age(None, "2026-07-29", "2026-07-31") == (2, "calendar")

    def test_neither_basis_is_a_null_not_a_zero(self):
        assert ubr.signal_age({}, None, "2026-07-31") == (None, None)
        assert ubr.signal_age({"fresh_bars": None}, "x", "2026-07-31") == (None, None)

    def test_a_negative_fresh_bars_falls_through_to_calendar(self):
        assert ubr.signal_age({"fresh_bars": -3}, "2026-07-29", "2026-07-31") == (
            2, "calendar")

    def test_the_two_bases_disagree_by_more_than_units_on_real_shapes(self):
        """Why the basis has to be disclosed rather than the units quietly swapped.

        `signal.asof` is the ticker's LAST CLOSE BAR, not the date the signal fired
        (engine.signal_quality.analyze stamps `str(idx[-1].date())`). On the committed
        07-31 board NUE reads asof=2026-07-31 while its own last marker fired
        2026-06-16 — calendar-only would call that 45-day-old signal 0 days old and
        light the NEW dot.
        """
        nue_like = {"fresh_bars": 32}
        age, basis = ubr.signal_age(nue_like, "2026-07-31", "2026-07-31")
        assert (age, basis) == (32, "sessions")
        assert ubr.days_since_signal("2026-07-31", "2026-07-31") == 0

    def test_score_rows_stamps_both_the_age_and_its_basis(self):
        rows = ubr.score_rows(
            [_row("SESS", asof="2026-07-31",
                  signal={**_verdict("T2", 1, asof="2026-07-31"), "fresh_bars": 9}),
             _row("CAL", asof="2026-07-29")],
            board_asof="2026-07-31")
        by = {r["ticker"]: r for r in rows}
        assert by["SESS"]["days_since_signal"] == 9
        assert by["SESS"]["days_since_signal_basis"] == "sessions"
        assert by["CAL"]["days_since_signal"] == 2
        assert by["CAL"]["days_since_signal_basis"] == "calendar"

    def test_an_unknown_age_carries_no_basis_claim(self):
        rows = ubr.score_rows([_row("A", asof=None)], board_asof=None)
        assert rows[0]["days_since_signal"] is None
        assert rows[0]["days_since_signal_basis"] is None


# ---------------------------------------------------------------------------
# 5. featured
# ---------------------------------------------------------------------------

class TestFeatured:
    def test_a_clean_live_row_qualifies(self):
        assert ubr.featured_shortfalls(_row("A", ext_z=0.0)) == []

    def test_ticks_zero_qualifies(self):
        """REGRESSION: `(v.get("ticks") or 99) <= 2` treats a same-day cross — the
        freshest and best signal there is — as missing, and un-features exactly the
        rows the board most wants to feature."""
        assert ubr.featured_shortfalls(_row("A", ticks=0, ext_z=0.0)) == []

    def test_ticks_none_does_not_qualify(self):
        assert "ticks_unknown" in ubr.featured_shortfalls(_row("A", ticks=None))

    def test_ticks_three_is_stale(self):
        assert "ticks_stale" in ubr.featured_shortfalls(_row("A", ticks=3))
        assert ubr.featured_shortfalls(_row("A", ticks=2, ext_z=0.0)) == []

    def test_buy_soon_is_live_but_not_featured(self):
        reasons = ubr.featured_shortfalls(_row("A", status="buy_soon"))
        assert "entry_status_buy_soon" in reasons
        assert "stage_not_live" not in reasons     # it IS live, just not featurable

    def test_t4_and_unknown_tier_are_out(self):
        assert "tier_T4" in ubr.featured_shortfalls(_row("A", tier="T4"))
        assert "tier_unknown" in ubr.featured_shortfalls(_row("A", tier=None))

    def test_provisional_is_out(self):
        assert "provisional" in ubr.featured_shortfalls(_row("A", provisional=True))

    def test_negative_alpha_is_out_and_zero_is_in(self):
        assert "alpha_below_floor" in ubr.featured_shortfalls(_row("A", alpha=-0.01))
        assert ubr.featured_shortfalls(_row("A", alpha=0.0, ext_z=0.0)) == []

    def test_unknown_alpha_is_out(self):
        assert "alpha_unknown" in ubr.featured_shortfalls(_row("A", alpha=None))

    def test_extension_and_antichase_block(self):
        assert "extended" in ubr.featured_shortfalls(_row("A", ext_z=2.5))
        assert ubr.featured_shortfalls(_row("A", ext_z=2.0)) == []   # not > 2
        # ANTICIPATION v1: an UNKNOWN reading is disclosed, not vetoed — the veto
        # fires on evidence past the line and never on absence.  Both branches are
        # asserted together so neither can be relaxed without the other showing up.
        assert ubr.featured_shortfalls(_row("A")) == []
        assert "antichase_blocked" in ubr.featured_shortfalls(
            _row("A", antichase_shadow_blocked=True))

    def test_earnings_blackout_blocks_from_either_source(self):
        assert "earnings_blackout" in ubr.featured_shortfalls(
            _row("A", earnings_soon={"in_blackout": True}))
        assert "earnings_blackout" in ubr.featured_shortfalls(
            _row("A"), in_blackout=True)

    def test_board_cap(self):
        # every alpha non-negative, so the cap is the only thing that can bind
        rows = [_row(f"T{i:02d}", sector=f"S{i}", alpha=20.0 - i, ext_z=0.0)
                for i in range(20)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        featured = [r for r in scored if r["featured"]]
        assert len(featured) == ubr.FEATURED_CAP
        assert ["featured_cap"] in [
            r.get("featured_blocked_by") for r in scored if not r["featured"]]

    def test_sector_cap(self):
        rows = [_row(f"T{i:02d}", sector="Utilities", alpha=8.0 - i, ext_z=0.0)
                for i in range(8)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        featured = [r for r in scored if r["featured"]]
        assert len(featured) == ubr.SECTOR_CAP
        assert ["sector_cap"] in [
            r.get("featured_blocked_by") for r in scored if not r["featured"]]

    def test_featured_is_taken_by_score_desc(self):
        rows = [_row("LOW", alpha=0.1, sector="A", ext_z=0.0),
                _row("HIGH", alpha=5.0, sector="B", ext_z=0.0)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31",
                                featured_cap=1, sector_cap=4)
        featured = [r["ticker"] for r in scored if r["featured"]]
        assert featured == ["HIGH"]

    def test_featured_never_changes_membership(self):
        rows = [_row("A"), _row("B", status="avoid", alpha=-2.0)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        assert {r["ticker"] for r in scored} == {"A", "B"}


# ---------------------------------------------------------------------------
# 5b. ANTICIPATION v1 — the widened featured set, and what still binds
# ---------------------------------------------------------------------------

class TestFeaturedEntryStatuses:
    """The featured entry set is CN's from 2026-08-08, and R2 (2026-08-09) made it LIVE.

    #4976 widened the set and left it inert behind a stage veto that ran FIRST and
    passed only `live`; the inertness was pinned by a test whose docstring said it
    would go red the day the follow-up landed.  This is that day, and these are the
    replacement pins: which statuses the widening actually opened, and which of them
    the stage veto still refuses.
    """

    def test_the_set_is_chinas(self):
        from engine import china_board_rank as cn

        assert ubr._FEATURED_ENTRY_STATUSES == frozenset(
            ("bounce_wait", "wait_pullback", "hold", "buy_now", "partial"))
        assert ubr._FEATURED_ENTRY_STATUSES == cn._FEATURED_ENTRY_STATUSES

    @pytest.mark.parametrize("status", ["bounce_wait", "wait_pullback", "hold"])
    def test_a_patience_status_clears_the_entry_veto(self, status):
        reasons = ubr.featured_shortfalls(_row("A", status=status, ext_z=0.0))
        assert f"entry_status_{status}" not in reasons

    @pytest.mark.parametrize("status", ["bounce_wait", "wait_pullback"])
    def test_the_setting_up_patience_statuses_are_now_featurable(self, status):
        """R2: the widening stops being inert for the two `setting_up` statuses."""
        row = _row("A", status=status, ext_z=0.0)
        assert ubr.stage_for(row) == ubr.STAGE_SETTING_UP
        assert ubr.featured_shortfalls(row) == []
        scored = ubr.score_rows([row], board_asof="2026-07-31")
        assert scored[0]["featured"] is True

    def test_but_hold_is_still_refused_because_ran_means_dont_chase(self):
        """The relax is {live, setting_up}, NOT CN's "no stage gate at all".

        `hold` routes to `ran`, whose own rendered shelf label is "Ran — don't chase".
        Featuring a row while its bucket tells the reader not to chase it is a
        contradiction the board would publish about itself, so `ran` stays vetoed —
        and the receipt names the bucket that refused it, not a generic "not live".
        """
        row = _row("A", status="hold", ext_z=0.0)
        assert ubr.stage_for(row) == ubr.STAGE_RAN
        assert "stage_ran" in ubr.featured_shortfalls(row)
        scored = ubr.score_rows([row], board_asof="2026-07-31")
        assert scored[0]["featured"] is False

    def test_status_is_the_first_gate_and_stage_only_prunes_what_it_admits(self):
        """THE R2 ORDERING RULING, at its own grain.

        A row whose entry status was never featurable is refused on the STATUS and is
        not also charged a stage reason.  Before R2 the stage veto ran first and
        reported `stage_not_live` on such a row, so `featured_blocked_by` named a gate
        that was not the binding one.  This is the assertion that fails on the old
        ordering: `watch` is a `setting_up` status, so the old code emitted BOTH
        reasons and the new code emits only the status.
        """
        row = _row("A", status="watch", ext_z=0.0)
        reasons = ubr.featured_shortfalls(row)
        assert reasons == ["entry_status_watch"]
        assert not any(r.startswith("stage_") for r in reasons)

    def test_an_admissible_status_in_a_stand_aside_bucket_is_still_refused(self):
        """The pruning half: status admission does not survive blocked/basing.

        `stage_for`'s DOWNTREND clause is unconditional by design — a falling name does
        not reach the featured shelf because its entry status happens to read
        `bounce_wait`.  R2 reordered the gates; it did not delete one.
        """
        row = _row("A", status="bounce_wait", ext_z=0.0,
                   state="DECLINE", label="DOWNTREND", dir="down")
        assert ubr.stage_for(row) == ubr.STAGE_BLOCKED
        assert "stage_blocked" in ubr.featured_shortfalls(row)

    @pytest.mark.parametrize("status", ["buy_soon", "extended", "topping", "watch",
                                        "await_confluence", "avoid"])
    def test_the_widening_did_not_open_the_door_to_everything(self, status):
        """Falsifier: `buy_soon` is LIVE and still not featurable (CN's era-worst
        cohort), and nothing outside the set slipped in with the three that did."""
        reasons = ubr.featured_shortfalls(_row("A", status=status, ext_z=0.0))
        assert f"entry_status_{status}" in reasons

    def test_buy_now_and_partial_are_still_featurable(self):
        for status in ("buy_now", "partial"):
            row = _row("A", status=status, ext_z=0.0)
            assert ubr.featured_shortfalls(row) == []
            assert ubr.score_rows([row], board_asof="2026-07-31")[0]["featured"] is True


# ---------------------------------------------------------------------------
# 5c. ANTICIPATION v1 — an unknown extension is disclosed, not vetoed
# ---------------------------------------------------------------------------

class TestExtensionUnknownIsDisclosed:
    """The 2026-08-06 shape, pinned: one upstream gap must not dark the lane.

    Historical cause (`site/factordata/us_standouts.json` @3cbef39a6ea): the equity
    close panel's newest row carried 6 of 3,034 members and the pre-#4979 positional
    reader selected it, so all 69 buy rows came back `ext_z` None and the B3 veto
    published `featured: 0`.  #4979 now coverage-anchors and age-bounds that read; this
    class pins the remaining policy for honest nulls, not a claim that the defect remains.
    """

    def test_unknown_is_eligible_and_flagged(self):
        row = _row("A")                     # no ext_z at all
        assert ubr.featured_shortfalls(row) == []
        scored = ubr.score_rows([row], board_asof="2026-07-31")
        assert scored[0]["featured"] is True
        assert scored[0]["ext_unknown"] is True

    def test_nan_counts_as_unknown_not_as_a_reading(self):
        """The 07-31 defect delivered a float that is not a number."""
        row = _row("A", ext_z=float("nan"))
        assert ubr.ext_unknown(row) is True
        assert ubr.featured_shortfalls(row) == []
        assert ubr.score_rows([row], board_asof="2026-07-31")[0]["ext_unknown"] is True

    def test_a_known_extended_reading_still_blocks_exactly_as_before(self):
        """The other half of the branch — the veto still fires on EVIDENCE."""
        row = _row("A", ext_z=2.5)
        assert ubr.ext_unknown(row) is False
        assert "extended" in ubr.featured_shortfalls(row)
        scored = ubr.score_rows([row], board_asof="2026-07-31")
        assert scored[0]["featured"] is False
        assert "extended" in scored[0]["featured_blocked_by"]
        assert scored[0]["ext_unknown"] is False

    def test_the_boundary_is_unchanged(self):
        assert ubr.featured_shortfalls(_row("A", ext_z=2.0)) == []
        assert "extended" in ubr.featured_shortfalls(_row("A", ext_z=2.001))

    def test_the_score_leg_still_fails_closed_on_an_unknown_reading(self):
        """Fail-closed moved for the LANE, never for the POINTS: an unmeasured row
        still earns 0 runway.  If this ever pays out, an outage starts INFLATING
        scores, which is strictly worse than the lane going dark."""
        scored = ubr.score_rows([_row("A")], board_asof="2026-07-31")
        assert scored[0]["prophet"]["components"]["runway"] == 0.0

    def test_the_2026_08_06_shape_no_longer_darks_the_lane(self):
        """69 rows, every ext_z unknown — the board that shipped `featured: 0`."""
        rows = [_row(f"T{i:02d}", sector=f"S{i % 9}", alpha=1.0 + i)
                for i in range(69)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        featured = [r for r in scored if r["featured"]]
        assert len(featured) == ubr.FEATURED_CAP
        assert all(r["ext_unknown"] is True for r in featured)
        block = ubr.ranking_block(scored)
        assert block["ext_unknown_coverage"] == {
            "unknown": 69, "n": 69, "featured_with_unknown": ubr.FEATURED_CAP}
        # The B3 key survives and is still recomputed — it just reads 0 now, which is
        # accurate and is exactly why `ext_unknown_coverage` had to exist.
        assert block["featured_blocked_unknown_extension"] == 0

    def test_the_coverage_receipt_moves_with_the_data(self):
        """Mutation: give them readings and the disclosure must move (a frozen number
        would pass the test above and lie on every later board)."""
        alive = ubr.score_rows(
            [_row(f"T{i}", ext_z=0.0) for i in range(3)], board_asof="2026-07-31")
        assert ubr.ranking_block(alive)["ext_unknown_coverage"] == {
            "unknown": 0, "n": 3, "featured_with_unknown": 0}

    def test_a_dark_board_raises_a_line_start_warning(self, capsys):
        ubr.score_rows([_row(f"T{i}") for i in range(4)], board_asof="2026-07-31")
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "featured-ext-z-unknown" in ln]
        assert lines, "a fully dark extension input raised no alarm"
        # House law: the annotation must START the line, or GitHub drops it silently.
        assert lines[0].startswith("::warning title=featured-ext-z-unknown::"), lines[0]
        assert "4/4" in lines[0]
        assert "coverage- and age-bounded reader" in lines[0]
        assert ".iloc[-1]" not in lines[0]

    def test_a_healthy_board_stays_quiet(self, capsys):
        """Falsifier: the alarm must be a majority test, not an any-unknown test —
        otherwise it fires on every board and stops meaning anything."""
        rows = [_row(f"T{i}", ext_z=0.0) for i in range(4)]
        rows[0].pop("ext_z")
        ubr.score_rows(rows, board_asof="2026-07-31")
        assert "featured-ext-z-unknown" not in capsys.readouterr().out

    def test_the_alarm_fires_strictly_above_the_line(self):
        """Exactly half unknown is not a majority — the boundary is open."""
        assert ubr.EXT_UNKNOWN_ALARM_FRACTION == 0.5

    def test_a_board_with_no_extension_panel_is_not_alarmed_every_night(self, capsys):
        """An OUTAGE alarm on a market that has no input is a permanent false alarm.

        `engine.hk_board_rank` delegates `score_rows` here, and HK has no `ext_z`
        wiring anywhere — so unscoped, this alarm fired at 100% on every single HK
        build, telling the reader that HK is HK, in remediation words naming a US
        equity close panel HK does not build.  An annotation that is always on trains
        people to skip the annotation, including on the night the US panel really is
        dark.  Scoped to `EXTENSION_PANEL_MARKETS`.
        """
        assert ubr.BOARD_DEFINITION in ubr.EXTENSION_PANEL_MARKETS
        assert "hk_prophet_v2" not in ubr.EXTENSION_PANEL_MARKETS
        ubr.score_rows([_row(f"T{i}") for i in range(4)],
                       board_asof="2026-07-31", definition="hk_prophet_v2")
        assert "featured-ext-z-unknown" not in capsys.readouterr().out

    def test_the_scoping_silences_only_the_alarm_never_the_disclosure(self, capsys):
        """Falsifier for the test above: scoping must not become a way to HIDE the gap.

        The artifact-side receipt is what a no-panel market owes its reader, and it is
        computed identically on every board — only the Actions annotation is scoped.
        """
        scored = ubr.score_rows([_row(f"T{i}") for i in range(4)],
                                board_asof="2026-07-31", definition="hk_prophet_v2")
        capsys.readouterr()
        assert all(r["ext_unknown"] is True for r in scored)
        block = ubr.ranking_block(scored, definition="hk_prophet_v2")
        assert block["ext_unknown_coverage"] == {
            "unknown": 4, "n": 4, "featured_with_unknown": block["featured_count"]}

    def test_fewer_than_the_cap_is_honest_emptiness(self):
        scored = ubr.score_rows([_row("A", status="extended")],
                                board_asof="2026-07-31")
        assert [r for r in scored if r["featured"]] == []


# ---------------------------------------------------------------------------
# 6. the scoring pass + ordering
# ---------------------------------------------------------------------------

class TestScoreRows:
    def test_sort_is_stage_then_score_then_ticker(self):
        rows = [
            _row("BLOCK", status="avoid", alpha=9.0),
            _row("RAN", status="extended", alpha=8.0),
            _row("SETUP", status="bounce_wait", alpha=7.0),
            _row("LIVE", status="buy_now", alpha=0.0),
        ]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        assert [r["ticker"] for r in scored] == ["LIVE", "SETUP", "RAN", "BLOCK"]

    def test_a_blocked_row_never_outranks_a_live_row_however_high_its_alpha(self):
        rows = [_row("BLOCK", status="blocked", alpha=99.0),
                _row("LIVE", status="partial", alpha=-1.0)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        assert scored[0]["ticker"] == "LIVE"

    def test_ticker_breaks_a_score_tie(self):
        rows = [_row("ZZZ", alpha=1.0), _row("AAA", alpha=1.0)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        # AAA wins the alpha tie -> higher edge -> higher score; on a true tie the
        # ticker is the tiebreak. Either way the order is deterministic.
        assert [r["ticker"] for r in scored] == ["AAA", "ZZZ"]
        assert [r["score_rank"] for r in scored] == [1, 2]

    def test_ranks_are_dense_and_start_at_one(self):
        scored = ubr.score_rows([_row(f"T{i}") for i in range(5)],
                                board_asof="2026-07-31")
        assert [r["score_rank"] for r in scored] == [1, 2, 3, 4, 5]
        assert [r["display_rank"] for r in scored] == [1, 2, 3, 4, 5]

    def test_score_is_finite_bounded_and_one_decimal(self):
        scored = ubr.score_rows(
            [_row("A", alpha=1.0, ext_z=0.0, coiled={"star": True})],
            board_asof="2026-07-31")
        score = scored[0]["prophet"]["score"]
        assert 0.0 <= score <= 100.0
        assert round(score, 1) == score

    @pytest.mark.parametrize("status", list(ubr.ENTRY_NEUTRAL_STATUSES))
    def test_a_best_case_row_scores_the_flat_ceiling(self, status):
        """A best-case row still scores 100: the flat entry leg pays 1.0, so the
        published range is unchanged by ANTICIPATION v1 (2026-08-08).  100 needs a
        real cross-section — `edge` is a percentile and a pool of ONE has no
        percentile at all — hence the second row.

        Parametrized over all five admissible statuses because that IS the ruling:
        every one of them must produce the SAME score from the same inputs.  A
        re-introduced ordering fails here on four of the five.  Before this era only
        `buy_now` could reach 100; now any admissible status can, and none can beat
        another.

        Asserted on `points` as well as `score` so the test is about the arithmetic
        rather than about the one-decimal rounding `score` carries.
        """
        scored = ubr.score_rows(
            [_row("A", status=status, tier="T2", ticks=1, alpha=1.0,
                  ext_z=0.0, coiled={"star": True}),
             _row("Z", status=status, tier="T2", ticks=1, alpha=0.0,
                  ext_z=0.0, coiled={"star": True})],
            board_asof="2026-07-31")
        assert scored[0]["ticker"] == "A"
        assert sum(scored[0]["prophet"]["points"].values()) == pytest.approx(100.0)
        assert scored[0]["prophet"]["points"]["entry"] == pytest.approx(25.0)
        assert scored[0]["prophet"]["score"] == pytest.approx(100.0)

    def test_a_lone_best_case_row_tops_out_at_the_scoreable_range(self):
        scored = ubr.score_rows(
            [_row("A", status="bounce_wait", tier="T2", ticks=1, alpha=1.0,
                  ext_z=0.0, coiled={"star": True})],
            board_asof="2026-07-31")
        assert sum(scored[0]["prophet"]["points"].values()) == pytest.approx(75.0)
        assert scored[0]["prophet"]["score"] == pytest.approx(75.0)

    def test_points_reconstruct_the_score(self):
        scored = ubr.score_rows([_row("A", ext_z=1.0, coiled={"coiled": True})],
                                board_asof="2026-07-31")
        prophet = scored[0]["prophet"]
        assert sum(prophet["points"].values()) == pytest.approx(
            prophet["score"], abs=0.05)

    def test_rows_are_stamped_in_place(self):
        """The US builder shares one row object across lanes; copying would strand
        every later enrichment."""
        row = _row("A")
        scored = ubr.score_rows([row], board_asof="2026-07-31")
        assert scored[0] is row
        assert row["stage"] == "live"

    def test_legacy_score_fields_are_left_alone(self):
        row = _row("A", setup=1.23, alpha=0.5,
                   conviction={"score_edge": 7, "score_timing": 3})
        ubr.score_rows([row], board_asof="2026-07-31")
        assert row["setup"] == 1.23 and row["alpha"] == 0.5
        assert row["conviction"] == {"score_edge": 7, "score_timing": 3}
        assert "score" not in row      # prophet.score is the new authority

    def test_verdict_map_overrides_the_row_signal(self):
        row = _row("A", tier="T3")
        ubr.score_rows([row], verdict_by={"A": _verdict("T2", 1)},
                       board_asof="2026-07-31")
        assert row["prophet"]["components"]["signal"] == pytest.approx(1.0)

    def test_stage_counts_report_every_bucket(self):
        scored = ubr.score_rows([_row("A")], board_asof="2026-07-31")
        assert ubr.stage_counts(scored) == {
            "live": 1, "setting_up": 0, "ran": 0, "basing": 0, "blocked": 0}

    def test_empty_pool_is_not_a_crash(self):
        assert ubr.score_rows([], board_asof="2026-07-31") == []


class TestRankingBlock:
    def test_the_block_stamps_the_selection_era(self):
        """ANTICIPATION §6.2 item 4 — a forward-ledger row must be readable against
        the SELECTION rule that produced it, not against today's constants.  The
        stamp covers the selected population and admission regime, and deliberately
        survives a value-map or featured-set revision so H=63 episodes can mature; the
        module constant and published field are pinned together so it cannot drift."""
        block = ubr.ranking_block(
            ubr.score_rows([_row("A", ext_z=0.0)], board_asof="2026-07-31"))
        assert ubr.SELECTION_ERA == "anticipation-v1-2026-08-08"
        assert block["selection_era"] == ubr.SELECTION_ERA
        # It ships on an empty board too — an era is a property of the RULE.
        assert ubr.ranking_block([])["selection_era"] == ubr.SELECTION_ERA

    def test_the_entry_leg_provenance_is_not_the_stale_china_claim(self):
        """The basis string read "frozen status map, shared with the China board"
        from before the 2026-08-04 fork until 2026-08-08 — false for four days and
        false in a new way after this era.  What it must now do: name the ladder it
        actually applies, keep the vocabulary/values distinction, and say out loud
        that the US re-measurement has run and licenses no ordering."""
        entry = [p for p in ubr.ranking_block([])["formula_points"]
                 if p["component"] == "entry"][0]
        assert entry["basis"] != "frozen status map, shared with the China board"
        assert "map, shared with the China board" not in entry["basis"]
        # The surviving mention must be scoped to the VOCABULARY — the values are not
        # shared, and that distinction is the whole point of the rewrite.
        assert "vocabulary shared with the China board" in entry["basis"]
        assert ubr.SELECTION_ERA in entry["basis"]
        # It must publish the FLATNESS, the adverse §6.6 read and the empty horizon —
        # a board that ships a non-ordering must say that is what it is shipping.
        assert "flat value" in entry["basis"]
        assert "ADVERSE" in entry["basis"]
        assert "H=21/H=63" in entry["basis"]
        for boundary in ("split-adjusted cross-market context", "not exact legal-band",
                         "no status/ranking/Prophet/Neural Web authority", "TuShare daily",
                         "stk_limit", "integer-cent equality"):
            assert boundary in entry["basis"], boundary
        # ... and the LEVEL's consequence: the range is unchanged and the
        # confirmation class is not deflated.  A reader comparing two eras' scores
        # needs that said, not inferred.
        assert "0-100" in entry["basis"]
        for status in ubr.ENTRY_NEUTRAL_STATUSES:
            assert status in entry["basis"], status

    def test_a_sibling_market_inherits_the_ladder_but_never_the_measurement(self):
        """The receipt is SHARED code; the evidence behind it is not shared evidence.

        `engine.hk_board_rank.ranking_block` delegates straight to this function, so
        whatever this string says about WHY the entry leg is flat is published on the
        HK board too.  Written as one sentence it told an HK reader that the HK leg is
        flat because a US re-measurement over US board episodes read adverse — a
        measurement that has never been run on an HK episode.  The ladder really is
        inherited; the claim to have measured it is not inheritable.

        Both halves are pinned: the US board still states its own basis, and a sibling
        states inheritance and says out loud that its own market is unmeasured.
        """
        basis_of = lambda block: [p for p in block["formula_points"]  # noqa: E731
                                  if p["component"] == "entry"][0]["basis"]
        own = basis_of(ubr.ranking_block([]))
        inherited = basis_of(ubr.ranking_block([], definition="hk_prophet_v2"))
        assert own != inherited

        # The shared FACT survives on both — a sibling reader still learns what the leg
        # does, which is the half that IS transferable.
        for text in (own, inherited):
            assert "flat value" in text
            assert ubr.SELECTION_ERA in text
            assert "vocabulary shared with the China board" in text
            assert "split-adjusted cross-market context" in text
            assert "not exact legal-band evidence" in text
            assert "no status/ranking/Prophet/Neural Web authority" in text

        # The US board keeps the direct attribution ...
        assert "the §6.6 US re-measurement read ADVERSE" in own
        assert "INHERITS" not in own
        # ... and the sibling gets the honest one: structural inheritance, plus the
        # explicit null that its own market has not been measured.
        assert "INHERITS it structurally" in inherited
        assert "no equivalent re-measurement has been run on this market's own " \
               "episodes" in inherited

    def test_the_entry_basis_prints_the_restored_buy_soon_value(self):
        """The receipt must agree with the map it describes.  `buy_soon` reads 0.8
        (restored 2026-08-09 — the CN-derived demotion was withdrawn), and a printed
        0.35 would be a wrong number on a user-reachable artifact."""
        entry = [p for p in ubr.ranking_block([])["formula_points"]
                 if p["component"] == "entry"][0]
        assert "buy_soon 0.8" in entry["basis"]
        assert "buy_soon 0.35" not in entry["basis"]
        assert ubr._ENTRY_VALUE["buy_soon"] == 0.8

    def test_block_discloses_the_formula_and_the_scoreless_inputs(self):
        # ext_z=0.0: a KNOWN un-extended reading, so the `extended` veto is provably
        # not what lets this row through; featured_count == 1 either way now.
        scored = ubr.score_rows([_row("A", ext_z=0.0)], board_asof="2026-07-31")
        block = ubr.ranking_block(scored)
        # Read from the PRODUCER, not a literal: this assertion exists to prove the block
        # carries the live era stamp, and a hand-copied string turns that into a test of
        # the copy (the exact drift `tests/test_china_standouts_serialization.py` documents).
        assert block["definition"] == ubr.BOARD_DEFINITION == "us_prophet_v2"
        assert block["score_kind"] == ubr.SCORE_KIND
        assert {p["component"] for p in block["formula_points"]} == set(
            ubr.SCORE_WEIGHTS)
        assert sum(p["points"] for p in block["formula_points"]) == 100.0
        assert block["zero_score_authority"] == list(ubr.ZERO_SCORE_AUTHORITY)
        assert block["featured_count"] == 1
        assert block["stage_order"] == [
            "live", "setting_up", "ran", "basing", "blocked"]

    def test_block_is_json_serialisable(self):
        scored = ubr.score_rows([_row("A")], board_asof="2026-07-31")
        json.dumps(ubr.ranking_block(scored), allow_nan=False)

    def test_no_forecast_or_validation_language_anywhere_in_the_block(self):
        scored = ubr.score_rows([_row("A")], board_asof="2026-07-31")
        text = json.dumps(ubr.ranking_block(scored)).lower()
        for banned in ("validated", "win rate", "win-rate", "forecast return",
                       "expected return", "backtested"):
            assert banned not in text, f"{banned!r} must not appear in board copy"

    def test_bilingual_stage_labels(self):
        block = ubr.ranking_block([])
        for stage, label in block["stage_labels"].items():
            assert label["en"] and label["zh"], stage

    def test_the_us_edge_leg_prints_the_us_default_and_nothing_else(self):
        """MUTATION-VISIBLE PIN on a US-DEFAULTED parameter.

        `edge_reads` became a parameter when the HK board was ported off this module.
        Its US default is the sentence the US board publishes on its own disclosure
        block — and nothing asserted that the default was still what the US caller
        wants, so a change made for HK's benefit could silently rewrite the US
        board's published formula.  Both halves are pinned: the constant's text, and
        that the block prints exactly it when nobody overrides.
        """
        assert ubr.EDGE_READS_US == "residual alpha percentile inside this buy pool"
        block = ubr.ranking_block(ubr.score_rows([_row("A")],
                                                 board_asof="2026-07-31"))
        edge = [p for p in block["formula_points"] if p["component"] == "edge"][0]
        assert edge["reads"] == ubr.EDGE_READS_US
        # the override reaches the same slot — so the pin above is about the DEFAULT,
        # not about the parameter being ignored
        other = ubr.ranking_block([], edge_reads="something else")
        other_edge = [p for p in other["formula_points"]
                      if p["component"] == "edge"][0]
        assert other_edge["reads"] == "something else"

    def test_the_us_featured_requirements_carry_no_market_extras(self):
        """MUTATION-VISIBLE PIN on the other US-DEFAULTED parameter.

        `featured_requirements_extra` defaults to () for the US board — HK appends a
        turnover floor through it.  Nothing asserted the US list stays free of a
        market extra, so an extra added for one market could have quietly appeared on
        the US board's published requirements.  The appended-item test is what makes
        this non-vacuous: the parameter demonstrably reaches the list.
        """
        base = ubr.ranking_block([])["featured_requirements"]
        assert not any("turnover" in req for req in base), base
        assert base[-1].startswith("at most "), (
            "the caps line is the last US requirement; an extra would follow it")
        with_extra = ubr.ranking_block(
            [], featured_requirements_extra=["a market-specific floor"]
        )["featured_requirements"]
        assert with_extra == base + ["a market-specific floor"]


class TestComponentCoverage:
    """M1b: the score's own coverage receipt, recomputed every build.

    A hardcoded "runway is 0" note outlives its recompute; a counted one cannot.
    """

    def test_every_leg_is_reported_even_when_it_is_dead(self):
        scored = ubr.score_rows([_row("A", alpha=1.0), _row("B", alpha=0.0)],
                                board_asof="2026-07-31")
        cov = ubr.component_coverage(scored)
        assert set(cov) == set(ubr.SCORE_WEIGHTS)
        for name, bucket in cov.items():
            assert set(bucket) == {"nonzero", "n"}, name
            assert bucket["n"] == 2, name

    def test_a_dead_leg_counts_zero_not_absent(self):
        """The live board's shape: no row carries ext_z, so runway is 0 everywhere.
        A MISSING bucket would read 'not measured' — a different claim from
        'measured zero'."""
        scored = ubr.score_rows([_row(f"T{i}", alpha=float(i)) for i in range(4)],
                                board_asof="2026-07-31")
        cov = ubr.component_coverage(scored)
        assert cov["runway"] == {"nonzero": 0, "n": 4}

    def test_a_live_leg_counts_its_nonzero_rows(self):
        scored = ubr.score_rows(
            [_row("EXT", alpha=2.0, ext_z=2.5), _row("ROOM", alpha=1.0, ext_z=0.0),
             _row("NONE", alpha=0.0)],
            board_asof="2026-07-31")
        cov = ubr.component_coverage(scored)
        # ext_z 2.5 -> fully extended -> 0 runway; 0.0 -> full runway; absent -> 0
        assert cov["runway"] == {"nonzero": 1, "n": 3}

    def test_an_unscored_row_is_not_counted_as_a_zero(self):
        cov = ubr.component_coverage([{"ticker": "RAW"}])
        assert cov["signal"] == {"nonzero": 0, "n": 0}

    def test_the_block_carries_the_coverage_and_stays_json_safe(self):
        scored = ubr.score_rows([_row("A")], board_asof="2026-07-31")
        block = ubr.ranking_block(scored)
        assert block["component_coverage"]["runway"] == {"nonzero": 0, "n": 1}
        json.dumps(block, allow_nan=False)

    def test_coverage_is_computed_not_hardcoded(self):
        """Mutation check: change the input, the number must move."""
        dead = ubr.ranking_block(
            ubr.score_rows([_row("A", alpha=1.0), _row("B", alpha=0.0)],
                           board_asof="2026-07-31"))
        alive = ubr.ranking_block(
            ubr.score_rows([_row("A", alpha=1.0, ext_z=0.0),
                            _row("B", alpha=0.0, ext_z=0.5)],
                           board_asof="2026-07-31"))
        assert dead["component_coverage"]["runway"]["nonzero"] == 0
        assert alive["component_coverage"]["runway"]["nonzero"] == 2


class TestRunwayCoverageContract:
    """Both eras of `assert_runway_coverage_consistent`, exercised NOW.

    The committed artifact currently takes the pre-us_prophet_v1 branch, so without
    these the comparison branch would ship unexecuted and first run on the render that
    writes a `ranking` block — exactly the situation the rewrite exists to avoid.
    """

    @staticmethod
    def _board(rows, *, ranking=True, **over):
        board = {"as_of": "2026-07-31", "buy": rows}
        if ranking:
            board["ranking"] = ubr.ranking_block(rows)
            board["ranking"]["component_coverage"]["runway"].update(over)
        return board

    def test_a_dead_era_board_is_consistent(self):
        rows = ubr.score_rows([_row("A", alpha=1.0), _row("B", alpha=0.0)],
                              board_asof="2026-07-31")
        assert assert_runway_coverage_consistent(self._board(rows), rows) == {
            "nonzero": 0, "n": 2}

    def test_a_healed_era_board_is_consistent(self):
        """The shape the next render produces: ext_z present, the leg alive. The old
        `nonzero == 0` assertion failed here — this is the time bomb, defused."""
        rows = ubr.score_rows(
            [_row("A", alpha=1.0, ext_z=0.0), _row("B", alpha=0.0, ext_z=0.5),
             _row("C", alpha=0.5, ext_z=2.5)],
            board_asof="2026-07-31")
        assert assert_runway_coverage_consistent(self._board(rows), rows) == {
            "nonzero": 2, "n": 3}          # ext_z 2.5 is fully extended -> 0 runway

    def test_an_artifact_without_a_ranking_block_pins_the_absence(self):
        rows = ubr.score_rows([_row("A", alpha=1.0)], board_asof="2026-07-31")
        board = self._board(rows, ranking=False)
        assert "ranking" not in board
        assert assert_runway_coverage_consistent(board, rows) == {"nonzero": 0, "n": 1}

    def test_a_drifted_disclosure_is_caught(self):
        """Mutation guard: the comparison must be able to SEE a stale receipt, or the
        healed-era branch is decoration."""
        rows = ubr.score_rows([_row("A", alpha=1.0, ext_z=0.0)],
                              board_asof="2026-07-31")
        with pytest.raises(AssertionError, match="receipt drifted"):
            assert_runway_coverage_consistent(self._board(rows, nonzero=0), rows)

    def test_a_null_ranking_key_is_not_read_as_a_missing_block(self):
        rows = ubr.score_rows([_row("A", alpha=1.0)], board_asof="2026-07-31")
        with pytest.raises(AssertionError, match="unexpected shape"):
            assert_runway_coverage_consistent(
                {"as_of": "2026-07-31", "buy": rows, "ranking": None}, rows)

    def test_an_unscored_row_fails_the_denominator_check(self):
        rows = ubr.score_rows([_row("A", alpha=1.0)], board_asof="2026-07-31")
        board = {"as_of": "2026-07-31", "buy": rows + [{"ticker": "RAW"}]}
        with pytest.raises(AssertionError, match="not measured"):
            assert_runway_coverage_consistent(board, rows)


# ---------------------------------------------------------------------------
# 7. theme loader
# ---------------------------------------------------------------------------

def _write_baskets(tmp_path, themes, baskets):
    root = tmp_path / "baskets"
    root.mkdir(parents=True, exist_ok=True)
    (root / "latest.json").write_text(
        json.dumps({"as_of": "2026-07-31", "themes": themes}))
    (root / "membership.json").write_text(json.dumps({"baskets": baskets}))
    return tmp_path


_THEMES = [
    {"id": "us_sector_energy", "name": "Energy", "reco": "accumulate", "rank": 1,
     "bull_days": 238, "clean_entry": False},
    {"id": "ai_software", "name": "AI SW", "reco": "accumulate", "rank": 3,
     "bull_days": 5, "clean_entry": True},
    {"id": "regional_banks", "name": "Banks", "reco": "trim", "rank": 5,
     "bull_days": 40, "clean_entry": False},
    {"id": "robotics", "name": "Robots", "reco": "accumulate", "rank": 7,
     "bull_days": 85, "clean_entry": True},
]
_BASKETS = {
    "us_sector_energy": {"name": "Energy (EW)", "name_zh": "能源",
                         "members": [{"ticker": "XOM", "removed": None}]},
    "ai_software": {"name": "AI Software & Platforms", "name_zh": "AI 软件与平台",
                    "members": [{"ticker": "MSFT", "removed": None},
                                {"ticker": "PLTR", "removed": None},
                                {"ticker": "OLD", "removed": "2025-01-01"}]},
    "regional_banks": {"name": "Regional Banks", "name_zh": "区域银行",
                       "members": [{"ticker": "VLY", "removed": None}]},
    "robotics": {"name": "Robotics", "name_zh": "机器人",
                 "members": [{"ticker": "MSFT", "removed": None},
                             {"ticker": "ABB", "removed": None}]},
}


class TestThemeLoader:
    def test_selects_in_favour_non_sector_themes_by_rank(self, tmp_path):
        ctx = ubr.load_theme_context(_write_baskets(tmp_path, _THEMES, _BASKETS))
        assert [t["id"] for t in ctx["themes"]] == ["ai_software", "robotics"]
        assert ctx["as_of"] == "2026-07-31"

    def test_sector_pseudo_baskets_are_excluded(self, tmp_path):
        ctx = ubr.load_theme_context(_write_baskets(tmp_path, _THEMES, _BASKETS))
        assert "XOM" not in ctx["by_ticker"]

    def test_out_of_favour_recos_are_excluded(self, tmp_path):
        ctx = ubr.load_theme_context(_write_baskets(tmp_path, _THEMES, _BASKETS))
        assert "VLY" not in ctx["by_ticker"]

    def test_highest_ranked_theme_wins_a_shared_ticker(self, tmp_path):
        ctx = ubr.load_theme_context(_write_baskets(tmp_path, _THEMES, _BASKETS))
        assert ctx["by_ticker"]["MSFT"]["id"] == "ai_software"    # rank 3 beats 7
        assert ctx["by_ticker"]["ABB"]["id"] == "robotics"

    def test_removed_members_are_dropped(self, tmp_path):
        ctx = ubr.load_theme_context(_write_baskets(tmp_path, _THEMES, _BASKETS))
        assert "OLD" not in ctx["by_ticker"]

    def test_chip_shape(self, tmp_path):
        chip = ubr.load_theme_map(_write_baskets(tmp_path, _THEMES, _BASKETS))["MSFT"]
        assert set(chip) >= {"id", "name", "name_zh", "rank", "reco",
                             "bull_days", "clean_entry"}
        assert chip["name_zh"] == "AI 软件与平台"
        assert chip["bull_days"] == 5 and chip["clean_entry"] is True

    def test_top_n_is_respected(self, tmp_path):
        ctx = ubr.load_theme_context(
            _write_baskets(tmp_path, _THEMES, _BASKETS), top_n=1)
        assert [t["id"] for t in ctx["themes"]] == ["ai_software"]

    def test_absent_files_are_fail_soft(self, tmp_path, capsys):
        ctx = ubr.load_theme_context(tmp_path / "nothing-here")
        assert ctx == {"as_of": None, "themes": [], "by_ticker": {}}
        out = capsys.readouterr().out
        assert any(line.startswith("::notice") for line in out.splitlines()), (
            "the notice must START the line — a logger prefix makes GitHub drop it")

    def test_malformed_files_are_fail_soft(self, tmp_path, capsys):
        root = tmp_path / "baskets"
        root.mkdir(parents=True)
        (root / "latest.json").write_text("{not json")
        (root / "membership.json").write_text("{}")
        ctx = ubr.load_theme_context(tmp_path)
        assert ctx["by_ticker"] == {}
        assert capsys.readouterr().out.startswith("::notice")

    def test_no_in_favour_themes_is_fail_soft(self, tmp_path, capsys):
        themes = [{"id": "x", "name": "X", "reco": "avoid", "rank": 1}]
        ctx = ubr.load_theme_context(_write_baskets(tmp_path, themes, {"x": {}}))
        assert ctx["by_ticker"] == {}
        assert capsys.readouterr().out.startswith("::notice")


class TestThemeConfirmed:
    def test_young_bull_run_is_confirmed(self):
        assert ubr.theme_confirmed({"bull_days": 0}) is True
        assert ubr.theme_confirmed({"bull_days": 7}) is True

    def test_old_bull_run_is_not(self):
        assert ubr.theme_confirmed({"bull_days": 8}) is False
        assert ubr.theme_confirmed({"bull_days": 238}) is False

    def test_unknown_bull_days_is_not_confirmed(self):
        assert ubr.theme_confirmed({}) is False
        assert ubr.theme_confirmed(None) is False

    def test_stamp_themes_chips_and_flags(self):
        rows = [{"ticker": "MSFT"}, {"ticker": "NOPE"}]
        theme_by = {"MSFT": {"id": "ai_software", "bull_days": 5}}
        assert ubr.stamp_themes(rows, theme_by, confirmed_flag=True) == 1
        assert rows[0]["theme"]["id"] == "ai_software"
        assert rows[0]["theme_confirmed"] is True
        assert "theme" not in rows[1]

    def test_stamp_themes_without_the_flag_leaves_it_off(self):
        rows = [{"ticker": "MSFT"}]
        ubr.stamp_themes(rows, {"MSFT": {"id": "x", "bull_days": 1}})
        assert "theme_confirmed" not in rows[0]

    def test_stamp_themes_with_no_map_is_a_no_op(self):
        rows = [{"ticker": "MSFT"}]
        assert ubr.stamp_themes(rows, None) == 0
        assert ubr.stamp_themes(rows, {}) == 0
        assert rows == [{"ticker": "MSFT"}]


# ---------------------------------------------------------------------------
# 7b. total-return momentum (the leaders lane's rank key)
# ---------------------------------------------------------------------------

class TestTotalReturnZ:
    """The leaders rank key. Deliberately NOT residual alpha and NOT the composite's
    `momentum` leg — that leg is fed by residual alpha (measured corr 0.984 on the
    2026-07-31 board), so ranking by it would be the old rule under a new name."""

    @staticmethod
    def _ramp(start, end, n=64):
        step = (end - start) / (n - 1)
        return [start + step * i for i in range(n)]

    def test_stronger_total_return_scores_higher(self):
        z = ubr.total_return_z(
            {"UP": self._ramp(100, 200), "FLAT": self._ramp(100, 100),
             "DOWN": self._ramp(100, 50)}, sessions=63)
        assert z["UP"] > z["FLAT"] > z["DOWN"]

    def test_output_is_a_z_score(self):
        z = ubr.total_return_z(
            {t: self._ramp(100, 100 + i * 10) for i, t in enumerate("ABCDE")},
            sessions=63)
        assert len(z) == 5
        assert sum(z.values()) == pytest.approx(0.0, abs=1e-3)

    def test_only_the_window_is_read(self):
        """A long history and its 64-value tail must produce the same reading."""
        tail = self._ramp(100, 150)
        long = [1.0] * 500 + tail
        z_tail = ubr.total_return_z({"A": tail, "B": self._ramp(100, 100)},
                                    sessions=63)
        z_long = ubr.total_return_z({"A": long, "B": self._ramp(100, 100)},
                                    sessions=63)
        assert z_tail == z_long

    def test_short_history_is_omitted_not_zeroed(self):
        z = ubr.total_return_z(
            {"SHORT": [100.0, 110.0], "OK": self._ramp(100, 150),
             "OK2": self._ramp(100, 120)}, sessions=63)
        assert "SHORT" not in z
        assert set(z) == {"OK", "OK2"}

    def test_nans_are_dropped_before_the_window_is_measured(self):
        clean = self._ramp(100, 150)
        dirty = clean[:10] + [float("nan")] * 5 + clean[10:]
        z = ubr.total_return_z({"A": dirty, "B": self._ramp(100, 100)}, sessions=63)
        z_clean = ubr.total_return_z({"A": clean, "B": self._ramp(100, 100)},
                                     sessions=63)
        assert z["A"] == pytest.approx(z_clean["A"])

    def test_non_positive_base_is_omitted(self):
        bad = [0.0] + self._ramp(100, 150)[1:]
        z = ubr.total_return_z({"BAD": bad, "OK": self._ramp(100, 120),
                                "OK2": self._ramp(100, 130)}, sessions=63)
        assert "BAD" not in z

    def test_degenerate_cross_sections_return_nothing(self):
        assert ubr.total_return_z({}) == {}
        assert ubr.total_return_z({"ONLY": self._ramp(100, 150)}) == {}
        # zero dispersion -> no usable z, and never a divide-by-zero
        same = {t: self._ramp(100, 150) for t in "ABC"}
        assert ubr.total_return_z(same) == {}

    def test_window_is_the_lane_s_chartered_three_months(self):
        assert ubr.LEADERS_MOMENTUM_SESSIONS == 63

    def test_real_universe_shape_is_not_required(self):
        """Pure and pandas-free: plain lists in, plain floats out."""
        z = ubr.total_return_z({"A": self._ramp(1, 2), "B": self._ramp(1, 3)},
                               sessions=63)
        assert all(isinstance(v, float) for v in z.values())
        json.dumps(z, allow_nan=False)


# ---------------------------------------------------------------------------
# 8. ran lane
# ---------------------------------------------------------------------------

_UNSET = object()


def _ran_verdict(ticks, *, eligible=False, above200=True, weekly_bull=True,
                 last=None, asof="2026-07-31", fresh_bars=_UNSET):
    """A ran-lane verdict.

    ``fresh_bars`` is what signal_gate stamps when the last marker is a buy/rebuy —
    the count of DAILY bars since that marker — and it is the ran lane's fallback
    anchor. It defaults to ``ticks`` here purely so the 10-bar fixture series can
    resolve a MOVE as well as an age; on real names it runs ~3x larger (measured AEE
    29 vs ticks 11), and the tick-vs-session divergence has its own tests below rather
    than riding on this default. Pass ``fresh_bars=None`` for the real no-anchor shape
    (last marker is a sell/cut), which the fail-closed rule must DROP.
    """
    v = {"eligible": eligible, "ticks": ticks, "above200": above200,
         "weekly_bull": weekly_bull, "asof": asof}
    if last is not None:
        v["last"] = last
    v["fresh_bars"] = ticks if fresh_bars is _UNSET else fresh_bars
    return v


class TestRanAdmission:
    @pytest.mark.parametrize("ticks,admitted", [
        (0, False), (1, False), (2, False),      # still inside the fresh window
        (3, True), (9, True), (15, True),        # the ran window
        (16, False), (40, False),                # too far gone
    ])
    def test_ticks_window_edges(self, ticks, admitted):
        assert ubr.ran_admits(_ran_verdict(ticks)) is admitted

    def test_unknown_ticks_excluded(self):
        assert ubr.ran_admits(_ran_verdict(None)) is False

    def test_still_gate_eligible_is_excluded(self):
        """An eligible name belongs on the buy shelf, not on the ran lane."""
        assert ubr.ran_admits(_ran_verdict(5, eligible=True)) is False

    def test_unknown_eligibility_is_excluded(self):
        assert ubr.ran_admits({"ticks": 5, "above200": True,
                               "weekly_bull": True}) is False

    @pytest.mark.parametrize("key", ["above200", "weekly_bull"])
    @pytest.mark.parametrize("value", [False, None])
    def test_broken_or_unknown_trend_excluded(self, key, value):
        v = _ran_verdict(5)
        v[key] = value
        assert ubr.ran_admits(v) is False

    def test_dir_down_excluded(self):
        assert ubr.ran_admits(_ran_verdict(5), {"dir": "down"}) is False
        assert ubr.ran_admits(_ran_verdict(5), {"dir": "up"}) is True


class TestCrossRead:
    _DATES = [f"2026-07-{d:02d}" for d in (20, 21, 22, 23, 24, 27, 28, 29, 30, 31)]
    _CLOSES = [100.0, 101, 102, 103, 104, 105, 106, 107, 108, 110.0]

    def test_sessions_back_anchor(self):
        read = ubr.cross_read(self._DATES, self._CLOSES, sessions_back=4)
        assert read["sessions_since"] == 4
        assert read["cross_date"] == "2026-07-27"
        assert read["pct_since"] == pytest.approx(round((110 / 105 - 1) * 100, 1))
        assert read["anchor"] == "approx"

    def test_cross_date_anchor_wins(self):
        read = ubr.cross_read(self._DATES, self._CLOSES,
                              cross_date="2026-07-22", sessions_back=1)
        assert read["cross_date"] == "2026-07-22"
        assert read["sessions_since"] == 7
        assert read["pct_since"] == pytest.approx(round((110 / 102 - 1) * 100, 1))
        assert read["anchor"] == "marker"

    def test_pct_since_is_measured_from_the_same_bar_as_the_age(self):
        """The age and the move must never describe different anchors — on either
        path. `pct_since` off the ticks bar while `sessions_since` counts from the
        marker is the half of B3 that survives a units fix."""
        for kwargs in ({"cross_date": "2026-07-22"}, {"sessions_back": 7}):
            read = ubr.cross_read(self._DATES, self._CLOSES, **kwargs)
            bar = len(self._CLOSES) - 1 - read["sessions_since"]
            assert read["cross_date"] == self._DATES[bar]
            assert read["pct_since"] == pytest.approx(
                round((self._CLOSES[-1] / self._CLOSES[bar] - 1) * 100, 1))

    def test_every_read_declares_its_anchor(self):
        for kwargs in ({"cross_date": "2026-07-22"}, {"sessions_back": 3},
                       {"cross_date": "2020-01-01", "sessions_back": 2}):
            read = ubr.cross_read(self._DATES, self._CLOSES, **kwargs)
            assert read["anchor"] in ("marker", "approx")

    def test_cross_date_between_sessions_anchors_to_the_last_one_at_or_before(self):
        read = ubr.cross_read(self._DATES, self._CLOSES, cross_date="2026-07-26")
        assert read["cross_date"] == "2026-07-24"

    def test_cross_date_before_the_series_falls_back_to_sessions_back(self):
        read = ubr.cross_read(self._DATES, self._CLOSES,
                              cross_date="2020-01-01", sessions_back=2)
        assert read["cross_date"] == "2026-07-29"
        assert read["anchor"] == "approx", (
            "a marker date that could not be resolved must not be reported as an "
            "exact marker anchor")

    def test_zero_sessions_back_is_the_latest_bar(self):
        read = ubr.cross_read(self._DATES, self._CLOSES, sessions_back=0)
        assert read["sessions_since"] == 0 and read["pct_since"] == 0.0

    def test_a_fall_since_the_cross_is_reported_negative(self):
        read = ubr.cross_read(self._DATES, [110.0] * 9 + [99.0], sessions_back=3)
        assert read["pct_since"] == pytest.approx(-10.0)

    def test_nans_are_dropped_before_anchoring(self):
        dates = ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06"]
        read = ubr.cross_read(dates, [100.0, float("nan"), 110.0, 121.0],
                              sessions_back=1)
        assert read["cross_date"] == "2026-07-03"
        assert read["pct_since"] == pytest.approx(10.0)

    def test_too_little_history_is_none(self):
        assert ubr.cross_read(["2026-07-01"], [100.0], sessions_back=0) is None
        assert ubr.cross_read([], [], sessions_back=0) is None

    def test_anchor_before_the_start_of_the_series_is_none(self):
        assert ubr.cross_read(self._DATES, self._CLOSES, sessions_back=99) is None

    def test_no_anchor_at_all_is_none(self):
        assert ubr.cross_read(self._DATES, self._CLOSES) is None

    def test_zero_price_at_cross_is_none(self):
        assert ubr.cross_read(["2026-07-01", "2026-07-02"], [0.0, 10.0],
                              sessions_back=1) is None


class TestBuildRanRows:
    _DATES = [f"2026-07-{d:02d}" for d in (20, 21, 22, 23, 24, 27, 28, 29, 30, 31)]

    def _closes(self, last=110.0):
        return (self._DATES, [100.0, 101, 102, 103, 104, 105, 106, 107, 108, last])

    def _close_of(self, _ticker):
        return self._closes()

    def test_membership_and_row_shape(self):
        rows = ubr.build_ran_rows(
            {"MSFT": _ran_verdict(4), "FRESH": _ran_verdict(1),
             "STALE": _ran_verdict(40), "BROKE": _ran_verdict(4, above200=False)},
            meta_by={"MSFT": {"name": "Microsoft Corp", "sector": "IT",
                              "price": 110.0, "spark_svg": "<svg/>"}},
            close_of=self._close_of, board_asof="2026-07-31")
        assert [r["ticker"] for r in rows] == ["MSFT"]
        row = rows[0]
        assert row["name"] == "Microsoft Corp" and row["sector"] == "IT"
        assert row["price"] == 110.0 and row["spark_svg"] == "<svg/>"
        assert row["ticks"] == 4
        assert row["label"] == "RAN" and row["label_zh"] == "已启动"
        assert row["stage"] == "ran" and row["lane"] == "ran"
        assert row["pct_since"] == pytest.approx(round((110 / 105 - 1) * 100, 1))
        assert row["sessions_since"] == 4
        assert row["anchor"] == "approx"
        assert row["days_since_signal"] == 4          # sessions, from fresh_bars
        assert row["days_since_signal_basis"] == "sessions"

    def test_ran_rows_carry_no_entry_claim(self):
        rows = ubr.build_ran_rows({"A": _ran_verdict(4)}, close_of=self._close_of)
        for banned in ("entry_signal", "conviction", "prophet", "featured", "score"):
            assert banned not in rows[0], f"a ran row must not carry {banned!r}"

    def test_exclusions_are_case_insensitive(self):
        rows = ubr.build_ran_rows({"MSFT": _ran_verdict(4)}, exclude=["msft"],
                                  close_of=self._close_of)
        assert rows == []

    def test_order_is_ticks_asc_then_pct_since_desc(self):
        def close_of(ticker):
            return self._closes({"A": 110.0, "B": 130.0, "C": 120.0}[ticker])
        rows = ubr.build_ran_rows(
            {"A": _ran_verdict(3), "B": _ran_verdict(9), "C": _ran_verdict(9)},
            close_of=close_of)
        assert [r["ticker"] for r in rows] == ["A", "B", "C"]

    def test_theme_confirmed_sorts_first_and_carries_bilingual_copy(self):
        rows = ubr.build_ran_rows(
            {"OLD": _ran_verdict(3), "NEWTHEME": _ran_verdict(14)},
            close_of=self._close_of,
            theme_by={"NEWTHEME": {"id": "ai_software", "bull_days": 5},
                      "OLD": {"id": "robotics", "bull_days": 85}})
        assert [r["ticker"] for r in rows] == ["NEWTHEME", "OLD"]
        assert rows[0]["theme_confirmed"] is True
        assert rows[0]["theme_note"] and rows[0]["theme_note_zh"]
        assert "theme_confirmed" not in rows[1]
        assert "theme_note" not in rows[1]

    def test_theme_is_stamped_even_when_not_confirmed(self):
        rows = ubr.build_ran_rows({"A": _ran_verdict(4)}, close_of=self._close_of,
                                  theme_by={"A": {"id": "robotics", "bull_days": 85}})
        assert rows[0]["theme"]["id"] == "robotics"

    def test_cap(self):
        verdicts = {f"T{i:02d}": _ran_verdict(3 + (i % 13)) for i in range(30)}
        rows = ubr.build_ran_rows(verdicts, close_of=self._close_of)
        assert len(rows) == ubr.RAN_CAP
        rows = ubr.build_ran_rows(verdicts, close_of=self._close_of, cap=3)
        assert len(rows) == 3

    def test_missing_closes_still_emits_the_row_with_null_move(self):
        """No price history is a null to print, not a row to hide.

        The AGE lives in the verdict (`fresh_bars`, counted on the daily grid inside
        signal_gate), not in this lane's closes — only `pct_since` needed the prices.
        So the row keeps its anchor and its age and discloses the missing move. This
        is NOT the B3 drop: that fires only when the age itself would be invented
        (see test_no_marker_and_no_fresh_bars_drops_the_row)."""
        rows = ubr.build_ran_rows({"A": _ran_verdict(4)}, close_of=lambda _t: None)
        assert rows[0]["pct_since"] is None
        assert rows[0]["sessions_since"] == 4
        assert rows[0]["anchor"] == "approx"
        assert rows[0]["ticks"] == 4

    def test_missing_closes_keeps_the_marker_date_when_there_is_one(self):
        rows = ubr.build_ran_rows(
            {"A": _ran_verdict(4, last={"type": "buy", "date": "2026-07-21"})},
            close_of=lambda _t: None)
        assert rows[0]["cross_date"] == "2026-07-21"
        assert rows[0]["anchor"] == "marker"
        assert rows[0]["sessions_since"] == 4 and rows[0]["pct_since"] is None

    def test_no_close_accessor_at_all(self):
        rows = ubr.build_ran_rows({"A": _ran_verdict(4)})
        assert [r["ticker"] for r in rows] == ["A"]
        assert rows[0]["pct_since"] is None

    def test_a_marker_date_alone_dates_the_cross_without_claiming_an_age(self):
        """One anchor source is enough to keep the row: the marker date IS the cross
        date. With no closes to count sessions across and no fresh_bars, the age is
        honestly null — printed, not guessed, and not a reason to hide the row."""
        rows = ubr.build_ran_rows(
            {"A": _ran_verdict(4, fresh_bars=None,
                               last={"type": "buy", "date": "2026-07-21"})},
            close_of=lambda _t: None)
        assert rows[0]["cross_date"] == "2026-07-21"
        assert rows[0]["anchor"] == "marker"
        assert rows[0]["sessions_since"] is None and rows[0]["pct_since"] is None

    def test_marker_date_is_preferred_over_the_tick_count(self):
        """ticks are counted on the signal's own higher-timeframe grid, so the §7
        marker date is the only exact anchor when it exists."""
        rows = ubr.build_ran_rows(
            {"A": _ran_verdict(4, last={"type": "buy", "date": "2026-07-21"})},
            close_of=self._close_of)
        assert rows[0]["cross_date"] == "2026-07-21"
        assert rows[0]["sessions_since"] == 8      # not 4
        assert rows[0]["anchor"] == "marker"

    def test_a_sell_marker_is_not_a_cross_anchor(self):
        """A sell/cut marker cannot date a BUY cross, so the row falls back to the
        session count — never to the marker."""
        rows = ubr.build_ran_rows(
            {"A": _ran_verdict(4, last={"type": "sell", "date": "2026-07-21"},
                               fresh_bars=6)},
            close_of=self._close_of)
        assert rows[0]["cross_date"] == "2026-07-23"   # 6 sessions back, not the 21st
        assert rows[0]["sessions_since"] == 6
        assert rows[0]["anchor"] == "approx"

    # -- B3: the anchor contract ------------------------------------------------

    def test_the_fallback_reads_fresh_bars_and_not_ticks(self):
        """B3, the whole defect. `sessions_back=ticks` made sessions_since == ticks —
        a ~3x understatement (measured AEE 29 sessions reported as 11) — and anchored
        pct_since on the wrong bar with it."""
        rows = ubr.build_ran_rows(
            {"A": _ran_verdict(3, fresh_bars=9)}, close_of=self._close_of)
        assert rows[0]["sessions_since"] == 9, "must read fresh_bars, not ticks"
        assert rows[0]["ticks"] == 3
        assert rows[0]["pct_since"] == pytest.approx(round((110 / 100 - 1) * 100, 1))
        assert rows[0]["anchor"] == "approx"

    def test_no_marker_and_no_fresh_bars_drops_the_row(self):
        """The real shape behind ~45% of ran admits on the local store: the last
        marker is a sell, so signal_gate leaves fresh_bars None and there is no buy
        date to anchor on. Fail closed — never render a wrong age."""
        rows = ubr.build_ran_rows(
            {"A": _ran_verdict(4, last={"type": "sell", "date": "2026-07-21"},
                               fresh_bars=None)},
            close_of=self._close_of)
        assert rows == []

    def test_the_drop_is_reported_as_a_line_start_annotation(self, capsys):
        ubr.build_ran_rows({"A": _ran_verdict(4, fresh_bars=None)},
                           close_of=self._close_of)
        out = capsys.readouterr().out
        assert any(line.startswith("::notice") for line in out.splitlines()), (
            "the annotation must START the line — a logger prefix makes GitHub drop it")

    def test_the_drop_removes_only_the_unanchored_rows(self):
        """Mutation guard: the fail-closed rule must not empty the lane."""
        rows = ubr.build_ran_rows(
            {"KEEP": _ran_verdict(4, fresh_bars=5),
             "DROP": _ran_verdict(4, fresh_bars=None),
             "MARK": _ran_verdict(9, fresh_bars=None,
                                  last={"type": "buy", "date": "2026-07-22"})},
            close_of=self._close_of)
        assert [r["ticker"] for r in rows] == ["KEEP", "MARK"]   # ticks 4 before 9
        assert {r["ticker"]: r["anchor"] for r in rows} == {
            "KEEP": "approx", "MARK": "marker"}

    def test_every_emitted_row_carries_a_usable_anchor_and_age(self):
        """The invariant is about the ANCHOR and the AGE only. `pct_since` may be
        null on an anchored row whose closes could not measure the move — that is a
        disclosed null, not a contract break."""
        verdicts = {f"T{i:02d}": _ran_verdict(3 + (i % 6), fresh_bars=(i % 8) or None)
                    for i in range(20)}
        rows = ubr.build_ran_rows(verdicts, close_of=self._close_of)
        assert rows, "fixture must keep some rows or this proves nothing"
        for r in rows:
            assert r["anchor"] in ("marker", "approx")
            assert isinstance(r["sessions_since"], int)

    def test_an_anchored_row_whose_anchor_predates_the_tail_keeps_its_age(self):
        """fresh_bars 40 against a 10-bar tail: the move is unmeasurable here, the age
        is not. Dropping this row would delete a name we can date precisely."""
        rows = ubr.build_ran_rows(
            {"A": _ran_verdict(14, fresh_bars=40)}, close_of=self._close_of)
        assert rows[0]["sessions_since"] == 40
        assert rows[0]["pct_since"] is None
        assert rows[0]["anchor"] == "approx"

    def test_json_serialisable(self):
        rows = ubr.build_ran_rows({"A": _ran_verdict(4)}, close_of=self._close_of,
                                  theme_by={"A": {"id": "x", "bull_days": 2}})
        json.dumps(rows, allow_nan=False)

    def test_empty_verdicts(self):
        assert ubr.build_ran_rows({}) == []
        assert ubr.build_ran_rows(None) == []


# ---------------------------------------------------------------------------
# 8b. artifact-ORDER consumers (m8) — the hidden priority-order dependency
# ---------------------------------------------------------------------------

class TestArtifactOrderConsumers:
    """Two consumers slice `us_standouts.json["buy"]` by POSITION, so this module's
    sort silently decides their population:

      * engine/stock_desk.py — `board["buy"][:n]` picks which names the accountable
        AI desk writes graded leans about (n = cfg max_picks, default 6, capped 12).
      * scripts/build_vector.py `_standout_tickers` — `[:3]` of the BUY-ZONE-labelled
        rows, falling back to `buy[:3]`, names the tickers on the vector card.

    Neither reads a rank field, so nothing in either file fails if the order changes
    underneath it — the dependency is invisible at both call sites. These tests make
    it visible and mutation-checked: permute the artifact, the output must follow.
    """

    _ROWS = [
        {"ticker": "AAA", "label": "BUY ZONE", "price": 10.0, "conviction": {}},
        {"ticker": "BBB", "label": "BUY ZONE", "price": 11.0, "conviction": {}},
        {"ticker": "CCC", "label": "BUY ZONE", "price": 12.0, "conviction": {}},
        {"ticker": "DDD", "label": "BUY ZONE", "price": 13.0, "conviction": {}},
        {"ticker": "EEE", "label": "UPTREND", "price": 14.0, "conviction": {}},
    ]

    def _write(self, root, rows):
        out = root / "site" / "factordata"
        out.mkdir(parents=True, exist_ok=True)
        (out / "us_standouts.json").write_text(
            json.dumps({"as_of": "2026-07-31", "rank_by": "us_prophet_v1",
                        "gate_go": True, "buy": rows}))

    # -- engine/stock_desk.gather_top_picks ---------------------------------

    def test_stock_desk_takes_the_board_top_n_in_artifact_order(self, tmp_path):
        from engine import stock_desk
        self._write(tmp_path, self._ROWS)
        picks = stock_desk.gather_top_picks(root=tmp_path, cfg={"max_picks": 3})
        assert [p["ticker"] for p in picks["picks"]] == ["AAA", "BBB", "CCC"]

    def test_stock_desk_population_follows_a_reordered_board(self, tmp_path):
        """Mutation check — the whole point of the pin. Reverse the artifact and the
        desk writes notes about a DIFFERENT set of names, with no code change."""
        from engine import stock_desk
        self._write(tmp_path, list(reversed(self._ROWS)))
        picks = stock_desk.gather_top_picks(root=tmp_path, cfg={"max_picks": 3})
        assert [p["ticker"] for p in picks["picks"]] == ["EEE", "DDD", "CCC"]

    # -- scripts/build_vector._standout_tickers -----------------------------

    def test_vector_card_takes_the_first_three_buy_zone_rows_in_order(self, monkeypatch,
                                                                      tmp_path):
        from lib import config
        from scripts import build_vector
        self._write(tmp_path, self._ROWS)
        monkeypatch.setattr(config, "ROOT", tmp_path)
        assert build_vector._standout_tickers("us") == ["AAA", "BBB", "CCC"]

    def test_vector_card_follows_a_reordered_board(self, monkeypatch, tmp_path):
        from lib import config
        from scripts import build_vector
        self._write(tmp_path, list(reversed(self._ROWS)))
        monkeypatch.setattr(config, "ROOT", tmp_path)
        assert build_vector._standout_tickers("us") == ["DDD", "CCC", "BBB"]

    def test_vector_fallback_slice_is_order_dependent_too(self, monkeypatch, tmp_path):
        """No BUY ZONE row anywhere → the fallback `buy[:3]` carries the dependency."""
        from lib import config
        from scripts import build_vector
        rows = [{**r, "label": "UPTREND"} for r in self._ROWS]
        self._write(tmp_path, rows)
        monkeypatch.setattr(config, "ROOT", tmp_path)
        assert build_vector._standout_tickers("us") == ["AAA", "BBB", "CCC"]
        self._write(tmp_path, list(reversed(rows)))
        assert build_vector._standout_tickers("us") == ["EEE", "DDD", "CCC"]

    def test_the_ranker_is_what_decides_that_order(self, monkeypatch, tmp_path):
        """End to end: score_rows' output order is what both consumers slice."""
        from lib import config
        from scripts import build_vector
        rows = ubr.score_rows(
            [{**_row("LOW", alpha=0.1), "label": "BUY ZONE"},
             {**_row("HIGH", alpha=9.0), "label": "BUY ZONE"},
             {**_row("MID", alpha=1.0), "label": "BUY ZONE"}],
            board_asof="2026-07-31")
        self._write(tmp_path, rows)
        monkeypatch.setattr(config, "ROOT", tmp_path)
        assert build_vector._standout_tickers("us")[0] == "HIGH"


# ---------------------------------------------------------------------------
# 8b. R2 (§6.9) — reversal cohort channel + the score-scope contract
# ---------------------------------------------------------------------------

def _cohort_fixture(tmp_path, *, states, members):
    """Write a minimal us_basket_turn artifact + curated membership pair."""
    site = tmp_path / "site"
    data = tmp_path / "data"
    (site / "basketdata").mkdir(parents=True)
    (data / "baskets").mkdir(parents=True)
    (site / "basketdata" / "us_basket_turn.json").write_text(json.dumps({
        "schema": "us_basket_turn.v1",
        "as_of": "2026-08-07",
        "baskets": {bid: {"state": st} for bid, st in states.items()},
    }))
    (data / "baskets" / "membership.json").write_text(json.dumps({
        "baskets": {
            bid: {"name": f"{bid} basket", "name_zh": "测试组合",
                  "members": [{"ticker": t} for t in tickers]}
            for bid, tickers in members.items()
        }
    }))
    return site, data


class TestReversalCohortChannel:
    """R2's binary membership channel — LIVE, disclosed, and carrying no score.

    The channel is sourced from the ``us_basket_turn`` organ, which declares
    ``may_rank: false`` in BOTH its artifact and its config/synapse.yml node.  These
    tests pin the two things that keeps honest: it earns no points, and a missing
    input is never smoothed into "nobody qualified".
    """

    def test_a_cohort_basket_makes_its_members_members(self, tmp_path):
        site, data = _cohort_fixture(
            tmp_path,
            states={"uranium": "TURNING", "megacap": "CONFIRMED"},
            members={"uranium": ["UEC", "CCJ"], "megacap": ["AAPL"]})
        cohort = ubr.load_reversal_cohort(site_root=site, data_dir=data)
        assert cohort["input"] == "present"
        assert set(cohort["members"]) == {"UEC", "CCJ"}
        assert cohort["members"]["UEC"]["state"] == "TURNING"
        assert cohort["baskets_in_cohort"] == 1
        assert cohort["baskets_read"] == 2

    @pytest.mark.parametrize("state", sorted(ubr.REVERSAL_COHORT_STATES))
    def test_every_cohort_state_admits(self, tmp_path, state):
        site, data = _cohort_fixture(tmp_path, states={"b": state},
                                     members={"b": ["AAA"]})
        assert ubr.load_reversal_cohort(site_root=site, data_dir=data)["members"]

    @pytest.mark.parametrize("state", ["CONFIRMED", "FALLING", "NONE", ""])
    def test_a_non_cohort_state_admits_nobody(self, tmp_path, state):
        site, data = _cohort_fixture(tmp_path, states={"b": state},
                                     members={"b": ["AAA"]})
        cohort = ubr.load_reversal_cohort(site_root=site, data_dir=data)
        assert cohort["input"] == "present"
        assert cohort["members"] == {}

    def test_the_state_vocabulary_matches_the_organ_that_emits_it(self):
        """The duplication fence.

        :data:`ubr.REVERSAL_COHORT_STATES` re-types three literals that
        ``engine.us_early_turn`` also holds, because importing that module here would
        drag pandas into a scoring path this one documents as pandas-free.  Copying is
        allowed; DRIFTING is not, and this is the line that catches it.
        """
        from engine import us_early_turn

        assert ubr.REVERSAL_COHORT_STATES == us_early_turn.WASHOUT_MATURE_STATES

    # -- scarcity honesty ---------------------------------------------------
    def test_a_missing_input_reads_absent_and_never_zero_members(self, tmp_path):
        """THE SCARCITY RULE, and the one this channel exists to get right.

        "No source tonight" and "the source ran and nobody qualified" are different
        facts.  Collapsing them is the 2026-08-06 extension blackout in miniature: an
        upstream gap rendered as a confident empty answer.
        """
        cohort = ubr.load_reversal_cohort(site_root=tmp_path / "nope",
                                          data_dir=tmp_path / "nope")
        assert cohort["input"] == "absent"
        assert cohort["members"] == {}
        read = ubr.reversal_cohort_of("AAA", cohort)
        assert read == {"member": False, "input": "absent",
                        "state": None, "basket_id": None}

    def test_present_but_empty_is_a_different_reading_from_absent(self, tmp_path):
        site, data = _cohort_fixture(tmp_path, states={"b": "FALLING"},
                                     members={"b": ["AAA"]})
        present = ubr.load_reversal_cohort(site_root=site, data_dir=data)
        absent = ubr.load_reversal_cohort(site_root=tmp_path / "nope",
                                          data_dir=tmp_path / "nope")
        assert present["members"] == absent["members"] == {}
        assert ubr.reversal_cohort_of("AAA", present)["input"] == "present"
        assert ubr.reversal_cohort_of("AAA", absent)["input"] == "absent"

    def test_a_thin_day_publishes_the_count_rather_than_hiding_it(self, tmp_path):
        site, data = _cohort_fixture(tmp_path, states={"b": "TURNING"},
                                     members={"b": ["AAA"]})
        cohort = ubr.load_reversal_cohort(site_root=site, data_dir=data)
        scored = ubr.score_rows(
            [_row("AAA", ext_z=0.0), _row("BBB", ext_z=0.0), _row("CCC", ext_z=0.0)],
            board_asof="2026-07-31", reversal_cohort=cohort)
        cov = ubr.reversal_cohort_coverage(scored)
        assert cov["members"] == 1 and cov["n"] == 3
        assert cov["share"] == pytest.approx(1 / 3, abs=1e-4)
        assert cov["input"] == "present"
        assert ubr.ranking_block(scored)["reversal_cohort_coverage"] == cov

    def test_an_empty_board_does_not_divide_by_zero(self):
        cov = ubr.reversal_cohort_coverage([])
        assert cov["members"] == 0 and cov["n"] == 0 and cov["share"] is None

    # -- stamping + zero authority -----------------------------------------
    def test_every_row_is_stamped_even_when_nobody_qualifies(self):
        """Same rule as `ext_unknown`: a field stamped only when true cannot be told
        apart from a build that never computed it."""
        scored = ubr.score_rows([_row("AAA", ext_z=0.0)], board_asof="2026-07-31")
        assert scored[0]["reversal_member"] is False
        assert scored[0]["reversal_cohort"]["input"] == "absent"

    def test_the_channel_is_declared_scoreless_in_the_published_artifact(self):
        assert "reversal_member" in ubr.ZERO_SCORE_AUTHORITY
        assert "reversal_member" not in ubr.SCORE_WEIGHTS
        block = ubr.ranking_block([])
        assert "reversal_member" in block["zero_score_authority"]

    def test_membership_changes_no_score_no_stage_and_no_featured_flag(self, tmp_path):
        """The zero-authority claim, tested as BEHAVIOUR rather than as a list entry.

        The same pool scored with and without the cohort must differ in exactly the two
        disclosure fields.  A leg that quietly read the channel would show up here.
        """
        site, data = _cohort_fixture(tmp_path, states={"b": "TURNING"},
                                     members={"b": ["AAA", "BBB"]})
        cohort = ubr.load_reversal_cohort(site_root=site, data_dir=data)

        def _pool():
            return [_row("AAA", ext_z=0.0, alpha=2.0),
                    _row("BBB", ext_z=0.5, alpha=1.0, status="bounce_wait"),
                    _row("CCC", ext_z=1.0, alpha=3.0)]

        without = ubr.score_rows(_pool(), board_asof="2026-07-31")
        with_ = ubr.score_rows(_pool(), board_asof="2026-07-31",
                               reversal_cohort=cohort)
        assert [r["ticker"] for r in without] == [r["ticker"] for r in with_]
        assert any(r["reversal_member"] for r in with_), "fixture must mark somebody"
        _disclosure = {"reversal_member", "reversal_cohort"}
        for lhs, rhs in zip(without, with_):
            assert {k: v for k, v in lhs.items() if k not in _disclosure} == {
                k: v for k, v in rhs.items() if k not in _disclosure}, lhs["ticker"]

    def test_the_era_stamp_travels_with_the_channel(self, tmp_path):
        """Era-stamp law: a published number that could shift carries the regime that
        produced it, so a forward-ledger row is readable against its own era."""
        assert ubr.reversal_cohort_coverage([])["selection_era"] == ubr.SELECTION_ERA
        cohort = ubr.load_reversal_cohort(site_root=tmp_path / "nope",
                                          data_dir=tmp_path / "nope")
        assert cohort["selection_era"] == ubr.SELECTION_ERA

    def test_a_ticker_in_two_cohort_baskets_keeps_one_deterministic_row(self, tmp_path):
        site, data = _cohort_fixture(
            tmp_path, states={"zz": "TURNING", "aa": "WASHED_OUT"},
            members={"zz": ["DUP"], "aa": ["DUP"]})
        first = ubr.load_reversal_cohort(site_root=site, data_dir=data)
        second = ubr.load_reversal_cohort(site_root=site, data_dir=data)
        assert first["members"]["DUP"] == second["members"]["DUP"]
        assert first["members"]["DUP"]["basket_id"] == "aa"


class TestScoreScopeContract:
    """R2 rider — the don't-chase-at-100 deviation #4976 recorded and deferred here."""

    def test_a_high_scoring_ran_row_still_sits_below_every_live_row(self):
        """The deviation reproduced, then shown to be harmless to the ORDER.

        A `ran` row really can outscore a `live` one — the flat entry leg pays every
        admissible status alike.  What must hold is that the sort never lets that
        number cross a bucket boundary.
        """
        rows = [_row("RAN", status="hold", alpha=9.0, tier="T2", ticks=0, ext_z=0.0),
                _row("LIVE", status="buy_now", alpha=-0.5, tier="T3", ticks=5)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        by = {r["ticker"]: r for r in scored}
        assert by["RAN"]["stage"] == "ran" and by["LIVE"]["stage"] == "live"
        assert by["RAN"]["prophet"]["score"] > by["LIVE"]["prophet"]["score"], (
            "fixture must reproduce the deviation or this proves nothing")
        assert [r["ticker"] for r in scored] == ["LIVE", "RAN"]

    def test_the_artifact_says_the_score_is_bucket_scoped(self):
        """The fix itself: the contradiction was a missing STATEMENT, not a wrong
        number, so the repair is a published contract and not a re-scored column."""
        note = ubr.ranking_block([])["score_scope_note"]
        assert "WITHIN a stage bucket" in note
        assert "never" in note.lower()

    def test_the_score_column_itself_is_not_deflated_by_its_bucket(self):
        """Deliberate non-repair: capping a don't-chase row's score would publish a
        different number for identical evidence.  The same legs pay the same points in
        every bucket, and that is checked rather than assumed."""
        live = ubr.score_rows([_row("A", status="buy_now", alpha=1.0, ext_z=0.0)],
                              board_asof="2026-07-31")[0]
        ran = ubr.score_rows([_row("A", status="hold", alpha=1.0, ext_z=0.0)],
                             board_asof="2026-07-31")[0]
        assert live["stage"] == "live" and ran["stage"] == "ran"
        for leg in ("signal", "edge", "runway", "quality"):
            assert live["prophet"]["points"][leg] == ran["prophet"]["points"][leg]
        assert live["prophet"]["points"]["entry"] == ran["prophet"]["points"]["entry"]


# ---------------------------------------------------------------------------
# 9. fixture integration — the committed artifacts, end to end
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def scored():
    """(board, scored_rows) from the COMMITTED artifacts — deterministic, in git."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    board = json.loads(
        (root / "site" / "factordata" / "us_standouts.json").read_text())
    gate = json.loads(
        (root / "site" / "factordata" / "signal_gate.json").read_text())
    rows = ubr.score_rows([dict(r) for r in board["buy"]],
                          verdict_by=gate.get("verdicts") or {},
                          board_asof=board["as_of"])
    return board, rows


@pytest.fixture(scope="module")
def scored_with_blocked_witness(scored):
    """The live board shape with one deterministic downtrend witness.

    A nightly board can legitimately contain no blocked/downtrend names, which
    makes the two ordering guards below fail on fixture composition instead of
    ranking behaviour.  Mutating one real row keeps the full production shape
    while ensuring those guards always exercise the blocked bucket.
    """
    from pathlib import Path
    board, _rows = scored
    root = Path(__file__).resolve().parents[1]
    gate = json.loads(
        (root / "site" / "factordata" / "signal_gate.json").read_text())
    raw = [dict(r) for r in board["buy"]]
    assert raw, "committed board must contain a row for the blocked witness"
    witness = raw[-1]
    witness["dir"] = "down"
    rows = ubr.score_rows(raw, verdict_by=gate.get("verdicts") or {},
                          board_asof=board["as_of"])
    return board, rows, witness["ticker"]


class TestCommittedArtifactIntegration:
    """Run the real module over the COMMITTED us_standouts + signal_gate + baskets.

    Deterministic (the inputs are in git), and the only place the score meets real
    board data: unit tests cannot tell you whether the ordering law survives 71 rows
    of production shape.
    """

    def test_every_row_scores_finite_and_in_range(self, scored):
        _board, rows = scored
        assert rows
        for r in rows:
            score = r["prophet"]["score"]
            assert isinstance(score, float)
            assert 0.0 <= score <= 100.0

    def test_no_blocked_row_ranks_above_any_live_row(self, scored_with_blocked_witness):
        _board, rows, _witness = scored_with_blocked_witness
        live = [i for i, r in enumerate(rows) if r["stage"] == "live"]
        blocked = [i for i, r in enumerate(rows) if r["stage"] == "blocked"]
        assert live and blocked, "fixture must contain both stages to mean anything"
        assert min(blocked) > max(live)

    def test_stage_sequence_never_goes_backwards(self, scored):
        _board, rows = scored
        ranks = [ubr.stage_rank(r["stage"]) for r in rows]
        assert ranks == sorted(ranks)

    def test_score_is_non_increasing_within_each_stage(self, scored):
        _board, rows = scored
        for stage in ubr.STAGE_ORDER:
            scores = [r["prophet"]["score"] for r in rows if r["stage"] == stage]
            assert scores == sorted(scores, reverse=True), stage

    def test_membership_is_byte_identical_to_the_committed_buy_lane(self, scored):
        """The ranking reorders and annotates. It must not add or drop one name."""
        board, rows = scored
        assert sorted(r["ticker"] for r in rows) == sorted(
            r["ticker"] for r in board["buy"])
        assert len(rows) == len(board["buy"])

    def test_the_basing_shelf_changes_nothing_but_the_shelf(self, scored):
        """G0.3 at board grain: the committed board through score_rows with and
        without the basing opt-in.

        The witness is injected rather than hoped for.  The 2026-07-31 artifact
        happens to carry no BOTTOM WATCH buy row, so reading this fixture as-is would
        pass on an engine that had never learned the state — the vacuous form of this
        guard.  The board's own ledger says the state IS routine (41 buy-lane rows
        over 13 of the 17 board days ending 07-31), so one real row is relabelled to
        the state the ledger shows and the assertions below refuse an empty split.

        The non-buy lanes are asserted as OBJECTS, not counts: score_rows is never
        handed watch/leaders/laggards/ran, and this is the test that says so.
        """
        board, _rows = scored
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        gate = json.loads(
            (root / "site" / "factordata" / "signal_gate.json").read_text())
        verdicts = gate.get("verdicts") or {}

        def _pool():
            raw = [json.loads(json.dumps(r)) for r in board["buy"]]
            assert len(raw) >= 2, "committed board must have room for a witness"
            # The witness must be a row the shelf CAN move, and that is not every row:
            # `stage_for` checks the entry status FIRST, and an explicit blocked/exit/
            # avoid verdict outranks the cycle read by design ("Blocked wins over
            # everything") — so relabelling such a row to BOTTOM WATCH leaves it
            # `blocked` in BOTH runs and the guard fails on fixture composition rather
            # than on behaviour. That is what happened when the nightly re-bake left ORA
            # (the board's only blocked-status buy row, 1 of 62) last: this test picked
            # `raw[-1]` and reddened main while the shelf worked correctly.
            # Pick the LAST row whose status cannot pre-empt the split, and refuse to
            # run rather than silently witness nothing.
            idx = next((i for i in range(len(raw) - 1, -1, -1)
                        if ubr._status_of(raw[i].get("entry_signal"))
                        not in ubr._BLOCKED_STATUSES), None)
            assert idx is not None, (
                "every buy row carries a blocked/exit/avoid entry status, so no row can "
                "witness the basing split — the fixture, not the shelf, is the problem")
            raw[idx].update({"state": "BOTTOM WATCH", "label": "NEARING A LOW",
                             "dir": "down"})
            raw[idx].pop("label_zh", None)
            return raw, raw[idx]["ticker"]

        lanes_before = json.dumps(
            {lane: board.get(lane) for lane in
             ("watch", "leaders", "laggards", "ran")}, sort_keys=True)

        raw_before, witness = _pool()
        raw_after, _ = _pool()
        before = ubr.score_rows(raw_before, verdict_by=verdicts,
                                board_asof=board["as_of"])
        after = ubr.score_rows(raw_after, verdict_by=verdicts,
                               board_asof=board["as_of"],
                               bottom_watch_stage=ubr.STAGE_BASING)

        by_before = {r["ticker"]: r for r in before}
        by_after = {r["ticker"]: r for r in after}
        assert by_before[witness]["stage"] == "blocked", (
            "witness must be blocked without the opt-in or this proves nothing")
        assert by_after[witness]["stage"] == "basing"

        moved = {t for t in by_before
                 if by_before[t]["stage"] != by_after[t]["stage"]}
        assert moved == {witness}
        assert all(by_before[t]["stage"] == "blocked" for t in moved)
        assert all(by_after[t]["stage"] == "basing" for t in moved)

        # Matched by ticker, every stamped field but `stage`, the two position stamps
        # and the stage token in `featured_blocked_by` is identical — the split
        # re-groups the board, it does not re-score it.  (R2 made the veto reason name
        # the refusing bucket, so it moves with the bucket; the flag still must not.)
        _positional = {"stage", "display_rank", "score_rank", "featured_blocked_by"}
        assert set(by_before) == set(by_after)
        for tk, lhs in by_before.items():
            rhs = by_after[tk]
            assert {k: v for k, v in lhs.items() if k not in _positional} == {
                k: v for k, v in rhs.items()
                if k not in _positional}, tk
            assert lhs["featured"] == rhs["featured"], tk
            assert ([r for r in (lhs.get("featured_blocked_by") or [])
                     if not r.startswith("stage_")]
                    == [r for r in (rhs.get("featured_blocked_by") or [])
                        if not r.startswith("stage_")]), tk
        assert [r["ticker"] for r in after] == [
            r["ticker"] for r in sorted(
                before,
                key=lambda r: (ubr.stage_rank(by_after[r["ticker"]]["stage"]),
                               -r["prophet"]["score"], r["ticker"]))]

        # The graded/context lanes are byte-identical across BOTH runs.  The US
        # builder shares one row object between lanes, so an engine that stamped a
        # lane row while staging the buy pool would show up right here.
        assert json.dumps(
            {lane: board.get(lane) for lane in
             ("watch", "leaders", "laggards", "ran")}, sort_keys=True) == lanes_before

    def test_featured_respects_both_caps(self, scored):
        """ERA-INDEPENDENT: the caps bind, and an EMPTY featured set is a legitimate
        answer, not a failure.

        This used to assert ``0 < len(featured)``, which pinned a property of ONE
        era's data rather than the contract.  From B3 (2026-08-06) a row with no
        ``ext_z`` reading cannot be featured, and the committed 07-31 artifact carries
        no ext_z on any of its 59 buy rows (a builder wiring defect the module
        docstring documents), so the honest featured count on that artifact is zero.
        The number the artifact must always keep true is the one below: never more
        than the caps allow, and whatever it is, the block says WHY it is that.
        """
        from collections import Counter
        board, rows = scored
        featured = [r for r in rows if r["featured"]]
        assert len(featured) <= ubr.FEATURED_CAP
        if featured:
            assert max(
                Counter(r["sector"] for r in featured).values()) <= ubr.SECTOR_CAP
        # Whatever the count, it must be EXPLAINED: every non-featured row carries a
        # reason, and the block's own disclosure must match the rows it describes.
        assert all(r.get("featured_blocked_by") for r in rows if not r["featured"])
        block = ubr.ranking_block(rows)
        assert block["featured_count"] == len(featured)
        assert block["featured_blocked_unknown_extension"] == sum(
            1 for r in rows
            if "ext_z_unknown" in (r.get("featured_blocked_by") or ()))

    def test_every_featured_row_is_forward_looking(self, scored):
        """R2 widened this from `live` only to {live, setting_up}.

        The invariant that matters is unchanged and is what this asserts: nothing on
        the featured shelf comes from a bucket that tells the reader to stand aside or
        not to chase.  `ran`, `basing` and `blocked` are all still refused — see
        :data:`engine.us_board_rank._FEATURED_STAGES` for why the relax stopped there
        instead of adopting CN's no-stage-gate-at-all.
        """
        _board, rows = scored
        for r in (r for r in rows if r["featured"]):
            assert r["stage"] in ubr._FEATURED_STAGES, r["ticker"]
            assert r["entry_signal"]["status"] in ubr._FEATURED_ENTRY_STATUSES
            assert float(r["alpha"]) >= 0
            assert r["signal"]["tier_cascade"] in ("T1", "T2", "T3")
            assert r["signal"]["ticks"] is not None and r["signal"]["ticks"] <= 2
        assert not any(r["featured"] for r in rows
                       if r["stage"] in (ubr.STAGE_RAN, ubr.STAGE_BASING,
                                         ubr.STAGE_BLOCKED))

    def test_a_same_day_cross_is_featurable_on_real_data(self, scored):
        """The ticks==0 trap, pinned against production rows: the 07-31 board carries
        same-day crosses, and truthiness testing would silently drop every one.

        Stated as a SHORTFALL test rather than a featured-count test so it survives
        the B3 era: on the committed artifact every row is blocked by
        ``ext_z_unknown``, so no row is featured at all and an ``any(featured)``
        assertion would go red for a reason that has nothing to do with ticks.  What
        must never come back is ``ticks_unknown``/``ticks_stale`` on a same-day cross.
        """
        _board, rows = scored
        zero_tick = [r for r in rows if (r.get("signal") or {}).get("ticks") == 0]
        assert zero_tick, "fixture must contain a same-day cross"
        for r in zero_tick:
            reasons = r.get("featured_blocked_by") or []
            assert "ticks_unknown" not in reasons, (
                f"{r['ticker']}: a same-day cross read as a MISSING tick count — "
                "check for `(ticks or 99) <= 2`")
            assert "ticks_stale" not in reasons, r["ticker"]

    def test_every_row_carries_the_display_contract(self, scored):
        _board, rows = scored
        for r in rows:
            for key in ("stage", "featured", "new", "score_rank", "display_rank",
                        "prophet", "days_since_signal", "days_since_signal_basis"):
                assert key in r, key
            # Read from the PRODUCER: `score_rows` stamps this from BOARD_DEFINITION, so a
            # hand-copied literal here turns an era-stamp test into a test of the copy —
            # and would have gone red on the us_prophet_v1 -> v2 bump (2026-08-10) for a
            # reason that had nothing to do with the display contract this test is about.
            assert r["prophet"]["version"] == ubr.BOARD_DEFINITION
            assert isinstance(r["featured"], bool) and isinstance(r["new"], bool)
            assert r["days_since_signal_basis"] in ("sessions", "calendar", None)
        assert [r["display_rank"] for r in rows] == list(range(1, len(rows) + 1))

    def test_runway_component_coverage_matches_the_committed_artifact(self, scored):
        """M1: the disclosure must DESCRIBE the rows it ships with, in every era.

        Coverage CONSISTENCY, checked against production rows: whatever the artifact
        discloses under `ranking.component_coverage.runway` must equal what the rows it
        shipped alongside actually score.  Dead (0/71) passes; alive (68/71) passes; a
        disclosure that drifted from its own rows fails, which is the real defect.
        Both branches of the contract are exercised today by
        `TestRunwayCoverageContract` — this test is the production-shape instance.
        """
        board, rows = scored
        assert_runway_coverage_consistent(board, rows)

    def test_the_attainable_score_cap_follows_the_measured_coverage(self, scored):
        """A dead leg deducts its full weight from EVERY row, so it caps the board's
        top score below 100.  That relationship holds in both eras — it is the part of
        the old deadness assertion worth keeping."""
        _board, rows = scored
        runway = ubr.component_coverage(rows)["runway"]
        cap = 100.0 if runway["nonzero"] else 100.0 - ubr.SCORE_WEIGHTS["runway"]
        assert max(r["prophet"]["score"] for r in rows) <= cap

    def test_the_scoring_legs_that_are_alive_are_alive(self, scored):
        """Mutation guard for the coverage counter itself: a counter that reported
        every leg dead would pass the runway assertion above and mean nothing."""
        _board, rows = scored
        cov = ubr.ranking_block(rows)["component_coverage"]
        assert cov["signal"]["nonzero"] > 0
        assert cov["entry"]["nonzero"] > 0
        assert cov["edge"]["nonzero"] > 0

    def test_the_session_basis_engages_on_real_verdicts(self, scored):
        """m4 against production shape, and a pin on which verdict feeds the age.

        The COMMITTED site/factordata/signal_gate.json carries the slim `buy_signal()`
        verdict (no `fresh_bars`), so the fixture above resolves every row on the
        disclosed `calendar` branch — that is the resolver degrading VISIBLY, which is
        what the basis field is for. The nightly builder passes the FULL in-memory
        verdicts instead, and the board rows themselves carry that shape under
        `signal` (signal_gate.compact keeps `fresh_bars`). Re-scoring off the rows'
        own verdicts proves the session branch engages on real data.

        WHICH session count, specifically: since #4933 `signal_age` prefers
        `fresh_bars_knowable` — counted from the session the marker's 3D bucket
        CLOSED on — and keeps `fresh_bars` (the bucket's OPEN label) only as the
        fallback for verdicts built before that field existed. This asserted
        `fresh_bars` until 2026-08-07 and went red on the committed board the day
        the preference flipped (GPCR: knowable 41 vs fresh_bars 43). Asserting the
        PREFERENCE rather than a field name is the point — the two differ by up to
        two sessions on every marker-anchored row, which is the whole reason
        `templates/stocktable.js`'s `FRESH_DAYS = 2` filter was dropping the
        freshest turns on the board.
        """
        board, _rows = scored
        assert {r["days_since_signal_basis"] for r in _rows} == {"calendar"}

        rich = {r["ticker"]: r["signal"] for r in board["buy"]
                if (r.get("signal") or {}).get("fresh_bars") is not None}
        assert rich, "fixture must carry at least one marker-anchored verdict"
        knowable = {t: v for t, v in rich.items()
                    if v.get("fresh_bars_knowable") is not None}
        assert knowable, (
            "fixture must carry at least one verdict with fresh_bars_knowable, else "
            "this pins the FALLBACK branch and #4933's preference goes untested")
        rows = ubr.score_rows([dict(r) for r in board["buy"]],
                              verdict_by=rich, board_asof=board["as_of"])
        by = {r["ticker"]: r for r in rows}
        for ticker, verdict in rich.items():
            expected = verdict.get("fresh_bars_knowable")
            if expected is None:
                expected = verdict["fresh_bars"]
            assert by[ticker]["days_since_signal"] == expected, ticker
            assert by[ticker]["days_since_signal_basis"] == "sessions"

        # The docstring's stated relationship between the two counts, asserted rather
        # than described: the OPEN label can never postdate its own bucket's close, and
        # a 3D bucket is three sessions wide. A drift outside that band means one of the
        # two anchors moved and the "up to two sessions" reasoning above is stale.
        for ticker, verdict in knowable.items():
            gap = verdict["fresh_bars"] - verdict["fresh_bars_knowable"]
            assert 0 <= gap <= 2, (ticker, verdict["fresh_bars"],
                                   verdict["fresh_bars_knowable"])

    def test_no_downtrend_row_escapes_the_blocked_bucket(self, scored_with_blocked_witness):
        """m1 on production shape with a deterministic DOWNTREND witness."""
        _board, rows, witness = scored_with_blocked_witness
        downtrend = [r for r in rows if ubr.is_downtrend(r)]
        assert witness in {r["ticker"] for r in downtrend}
        assert all(r["stage"] == "blocked" for r in downtrend)

    def test_the_board_is_json_safe(self, scored):
        board, rows = scored
        json.dumps({**board, "buy": rows,
                    "ranking": ubr.ranking_block(rows)}, allow_nan=False)

    def test_committed_baskets_produce_a_usable_theme_map(self):
        ctx = ubr.load_theme_context()
        assert ctx["themes"], "the committed baskets snapshot must yield in-favour themes"
        assert len(ctx["themes"]) <= ubr.THEME_TOP_N
        assert ctx["by_ticker"]
        for theme in ctx["themes"]:
            assert not theme["id"].startswith("us_sector_")
            assert theme["reco"] in ubr.THEME_IN_FAVOUR_RECOS
        ranks = [t["rank"] for t in ctx["themes"]]
        assert ranks == sorted(ranks)
