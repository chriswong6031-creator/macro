"""Prophet Learning Loop §2 — postmortem taxonomy + aggregation (gates G1, G2).

Two halves, and they check different things:

  * TestLoserCohortFixture runs the real classifier over the COMMITTED ledgers and
    pins gate G1: every name on the operator's 2026-07-31 worst-rows list must come
    back with a classification, entry-time context and visible-at-entry flags, and the
    IPGP double-admission must be flagged. A fixture test is the only thing that can
    catch a rule that is individually correct and collectively finds nothing.
  * The rule tests build synthetic rows so each threshold is exercised on BOTH sides
    and, critically, so an absent input is proven to produce a NULL rather than a
    silent negative — the failure mode that would have made every rate in the artifact
    look better than the data supports.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import postmortem as pm  # noqa: E402
from scripts import prophet_postmortem as ppm  # noqa: E402


# ===========================================================================
# helpers — the smallest context/row that exercises one rule at a time
# ===========================================================================
def _ctx(**over) -> dict:
    """A neutral entry context: every leg present, none of them firing.

    Present-but-negative is the right baseline. A context of Nones would make every
    rule NULL and the tests would pass while proving nothing.
    """
    base = {
        "sector": "Industrials",
        "basket_asof": "2026-07-01",
        "themes": [{"id": "defense", "reco": "hold", "label": "neutral",
                    "score": 50.0, "bull_days": 10.0, "rank": 5.0}],
        "spotlight_theme_id": "defense",
        "sector_basket": {"id": "us_sector_industrials", "reco": "hold",
                          "label": "neutral", "score": 50.0, "bull_days": 10.0,
                          "rank": 5.0},
        "spotlight": {"dir": "neutral", "z": 0.1, "sector_stage": "improving",
                      "sector_extended": False, "sector_pctile_252d": 60.0},
        "extension": {"overextended": False, "entry_tier": "Prime entry",
                      "ext_risk": 0.0, "ext_z": -0.2, "price": 100.0,
                      "chase_above": 110.0, "above_chase": False,
                      "off_high_pct": -8.0},
        "conviction": {"band": "neutral", "score": 50.0, "composite_z": 0.0,
                       "alpha": 0.1, "tier": None, "tier_cascade": None,
                       "urgency": "now", "state": "FRESH BUY"},
        "entry_plan": {"status": "buy_soon", "stop": 90.0, "atr_pct": 2.0,
                       "invalidation": 92.0, "hold_state": "intact"},
        "days_since_signal": 1.0,
        "board_tenure_days": 0.0,
    }
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


def _blank_ctx() -> dict:
    """A context with NO entry state recorded — the pre-archive history's shape."""
    return {
        "sector": "Industrials", "basket_asof": None, "themes": [],
        "spotlight_theme_id": None, "sector_basket": None,
        "spotlight": {"dir": None, "z": None, "sector_stage": None,
                      "sector_extended": None, "sector_pctile_252d": None},
        "extension": {"overextended": None, "entry_tier": None, "ext_risk": None,
                      "ext_z": None, "price": None, "chase_above": None,
                      "above_chase": False, "off_high_pct": None},
        "conviction": {}, "entry_plan": {"status": None, "stop": None},
        "days_since_signal": None, "board_tenure_days": None,
    }


def _path(**over) -> dict:
    base = {"n_bars": 10, "worst_session_pct": -1.5, "worst_session_date": "2026-07-06",
            "stop_level": 90.0, "stop_cross_date": None, "stop_cross_px": None}
    base.update(over)
    return base


def _names(labels) -> set[str]:
    return {lb["label"] for lb in labels}


def _trigger(labels, name) -> dict:
    return next(lb for lb in labels if lb["label"] == name)["trigger"]


def _visible(labels, name) -> bool:
    return next(lb for lb in labels if lb["label"] == name)["visible_at_entry"]


def _null_reasons(nulls, name) -> list[str]:
    return sorted(n["reason"] for n in nulls if n["label"] == name)


def _row(**over) -> dict:
    base = {"ticker": "AAA", "entry_date": "2026-07-01", "maturity": "matured",
            "outcome_pct": -10.0, "excess_pct": -9.0, "cohort": "loser",
            "labels": [], "labels_null": []}
    base.update(over)
    if "cohort" not in over:
        base["cohort"] = pm.cohort_of(base["outcome_pct"], base["excess_pct"])
    return base


def _labelled(name: str, visible: bool = False, **trigger) -> dict:
    return {"label": name, "visible_at_entry": visible, "trigger": dict(trigger)}


# ===========================================================================
# 0. THRESHOLD PINS — literals, never the constants they guard
# ===========================================================================
class TestThresholdsArePinnedAsLiterals:
    """Every threshold written out by hand.

    The rest of this file reads `pm.GAP_PCT` and friends so each boundary test stays
    honest when a threshold legitimately moves. That is the right shape for a boundary
    test and the WRONG shape for the only record of what the numbers are: with nothing
    but symbolic references, editing `GAP_PCT = -8.0` to `-5.0` re-points every test at
    the new value and the whole suite goes green on a silently redefined taxonomy — the
    artifact, the report and the masterplan would then be describing a rule no test
    disagrees with. These literals are that disagreement. A threshold change must land
    HERE, in a diff a reviewer reads, alongside the doc and masterplan edits.
    """

    def test_gap_event_threshold(self):
        assert pm.GAP_PCT == -8.0

    def test_extension_risk_threshold(self):
        assert pm.EXT_RISK_MIN == 0.10

    def test_readmission_window_in_sessions(self):
        assert pm.READMIT_MAX_SESSIONS == 10

    def test_cohort_and_remaining_thresholds(self):
        assert pm.LOSER_ABS_PCT == -8.0
        assert pm.LOSER_EXCESS_PCT == -5.0
        assert pm.WINNER_ABS_PCT == 8.0
        assert pm.BETA_SHARE_MAX == 0.40
        assert pm.READMIT_LOSS_PCT == -8.0

    def test_the_thresholds_the_artifact_publishes_match_the_module(self):
        # The artifact prints its own thresholds block; a reader re-deriving a label by
        # hand uses THOSE numbers. They must not be able to drift from the ones the
        # classifier actually applied.
        th = pm.aggregate([])["thresholds"]
        assert th["gap_pct"] == -8.0
        assert th["ext_risk_min"] == 0.10
        assert th["readmit_max_sessions"] == 10
        assert th["loser_abs_pct"] == -8.0
        assert th["loser_excess_pct"] == -5.0
        assert th["winner_abs_pct"] == 8.0
        assert th["beta_share_max"] == 0.40
        assert th["readmit_loss_pct"] == -8.0


# ===========================================================================
# 1. cohort gates
# ===========================================================================
class TestCohortGates:
    def test_absolute_leg(self):
        assert pm.cohort_of(-8.0, 0.0) == "loser"
        assert pm.cohort_of(-7.99, -1.0) == "neutral"

    def test_excess_leg_alone_makes_a_loser(self):
        # -6% in a +2% tape is a loss to the desk even though the absolute leg misses.
        assert pm.cohort_of(-4.0, -5.0) == "loser"

    def test_winner_gate_mirrors_the_absolute_loser_gate(self):
        assert pm.cohort_of(8.0, 0.0) == "winner"
        assert pm.cohort_of(7.99, 0.0) == "neutral"
        assert pm.WINNER_ABS_PCT == abs(pm.LOSER_ABS_PCT)

    def test_no_numbers_is_unscored_not_neutral(self):
        assert pm.cohort_of(None, None) == "unscored"

    def test_a_profitable_pick_is_a_WINNER_however_fast_the_tape_ran(self):
        # PRECEDENCE PIN. +9% against a +14.5% tape is -5.5% excess, which trips the
        # loser gate's excess leg. Testing the loser legs first booked that pick as a
        # LOSS — and, worse, deleted it from the winners-forfeited column, so every veto
        # in `veto_cost` looked cheaper than it is. The masterplan's winner gate is
        # absolute (">= +8%"), so the absolute return decides first.
        assert pm.cohort_of(9.0, -5.5) == "winner"
        assert pm.cohort_of(8.0, -20.0) == "winner"
        # ...and the excess leg keeps its real job: a name that LOST while the tape rose.
        assert pm.cohort_of(-4.0, -5.5) == "loser"
        assert pm.cohort_of(7.99, -5.5) == "loser"

    def test_a_winner_by_absolute_return_never_lands_in_the_loser_cohort(self):
        # The two gates cannot both be satisfied by an absolute return, so the only
        # overlap is via the excess leg — pinned above. This walks the boundary.
        for excess in (-50.0, -5.0, -4.99, 0.0, 5.0):
            assert pm.cohort_of(8.0, excess) == "winner"


# ===========================================================================
# 2. sector_headwind
# ===========================================================================
class TestSectorHeadwind:
    @pytest.mark.parametrize("reco", ["avoid", "trim"])
    def test_theme_reco_fires_and_is_visible_at_entry(self, reco):
        ctx = _ctx(themes=[{"id": "defense", "reco": reco, "label": "fading"}])
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=ctx, path=_path())
        assert "sector_headwind" in _names(labels)
        assert _visible(labels, "sector_headwind") is True
        legs = _trigger(labels, "sector_headwind")["legs"]
        assert {"leg": "theme_reco", "theme_id": "defense", "reco": reco,
                "label": "fading"} in legs

    def test_sector_basket_reco_fires_when_the_name_is_in_no_theme(self):
        ctx = _ctx(themes=[], sector_basket={"id": "us_sector_tech", "reco": "avoid",
                                             "label": "deteriorating"})
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=ctx, path=_path())
        legs = _trigger(labels, "sector_headwind")["legs"]
        assert [lg["leg"] for lg in legs] == ["sector_basket_reco"]

    def test_lagging_stage_and_out_of_play_each_fire(self):
        ctx = _ctx(spotlight={"sector_stage": "lagging", "dir": "out_of_play"})
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=ctx, path=_path())
        legs = {lg["leg"] for lg in _trigger(labels, "sector_headwind")["legs"]}
        assert legs == {"sector_stage", "spotlight_dir"}

    def test_weakening_stage_does_not_fire(self):
        # The RRG leading-but-rolling quadrant. Folding it in would push the label's
        # base rate past half the board and make it uninformative — a documented choice.
        ctx = _ctx(spotlight={"sector_stage": "weakening"})
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=ctx, path=_path())
        assert "sector_headwind" not in _names(labels)
        assert "weakening" not in pm.HEADWIND_STAGES

    def test_hold_and_accumulate_do_not_fire(self):
        labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=-9.0,
                                    ctx=_ctx(), path=_path())
        assert "sector_headwind" not in _names(labels)
        assert _null_reasons(nulls, "sector_headwind") == []   # decided, not skipped

    def test_no_theme_state_at_all_is_NULL_not_a_clean_bill(self):
        labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=-9.0,
                                    ctx=_blank_ctx(), path=_path())
        assert "sector_headwind" not in _names(labels)
        assert _null_reasons(nulls, "sector_headwind") == [
            "no_theme_state_or_spotlight_at_entry"]


# ===========================================================================
# 3. bought_extended
# ===========================================================================
class TestBoughtExtended:
    def test_overextended_flag(self):
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0,
                                ctx=_ctx(extension={"overextended": True}), path=_path())
        assert _visible(labels, "bought_extended") is True
        assert {"leg": "alignment_overextended", "value": True} in \
            _trigger(labels, "bought_extended")["legs"]

    def test_entry_tier_prefix(self):
        ctx = _ctx(extension={"entry_tier": "Extended — wait"})
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=ctx, path=_path())
        assert "bought_extended" in _names(labels)

    def test_ext_risk_threshold_is_inclusive_at_the_boundary(self):
        below = _ctx(extension={"ext_risk": pm.EXT_RISK_MIN - 0.001})
        at = _ctx(extension={"ext_risk": pm.EXT_RISK_MIN})
        assert "bought_extended" not in _names(
            pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=below, path=_path())[0])
        assert "bought_extended" in _names(
            pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=at, path=_path())[0])

    def test_fill_above_the_chase_level(self):
        ctx = _ctx(extension={"price": 120.0, "chase_above": 110.0, "above_chase": True})
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=ctx, path=_path())
        trig = _trigger(labels, "bought_extended")["legs"]
        assert {"leg": "above_chase_level", "price": 120.0, "chase_above": 110.0} in trig

    def test_absent_extension_state_is_NULL_not_negative(self):
        # `above_chase` is False both when the fill was cheap AND when price is missing,
        # so it must never stand in as evidence on its own.
        labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=-9.0,
                                    ctx=_blank_ctx(), path=_path())
        assert "bought_extended" not in _names(labels)
        assert _null_reasons(nulls, "bought_extended") == ["no_entry_state_recorded"]


# ===========================================================================
# 4. thesis_break
# ===========================================================================
class TestThesisBreak:
    def test_hold_state_history_wins_over_the_stop_cross(self):
        labels, _ = pm.classify(
            outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
            path=_path(stop_cross_date="2026-07-09", stop_cross_px=88.0),
            hold_broken={"board_date": "2026-07-07", "date": "2026-07-07"})
        trig = _trigger(labels, "thesis_break")
        assert trig["source"] == "hold_state_history"
        assert trig["date"] == "2026-07-07"

    def test_stop_cross_fallback_records_the_level_it_crossed(self):
        labels, _ = pm.classify(
            outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
            path=_path(stop_cross_date="2026-07-09", stop_cross_px=88.0))
        trig = _trigger(labels, "thesis_break")
        assert (trig["source"], trig["stop_level"], trig["close"]) == \
            ("stop_cross", 90.0, 88.0)
        assert _visible(labels, "thesis_break") is False

    def test_no_price_path_is_NULL(self):
        _labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=-9.0,
                                     ctx=_ctx(), path=None)
        assert "no_price_path" in _null_reasons(nulls, "thesis_break")

    def test_no_stop_recorded_is_NULL(self):
        _labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                     path=_path(stop_level=None))
        assert _null_reasons(nulls, "thesis_break") == ["no_stop_level_recorded"]

    def test_stop_present_and_uncrossed_is_a_decided_negative(self):
        _labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=-9.0,
                                     ctx=_ctx(), path=_path())
        assert _null_reasons(nulls, "thesis_break") == []


# ===========================================================================
# 5. gap_event
# ===========================================================================
class TestGapEvent:
    def test_threshold_is_inclusive_and_records_the_date(self):
        labels, _ = pm.classify(
            outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
            path=_path(worst_session_pct=pm.GAP_PCT, worst_session_date="2026-07-08"))
        trig = _trigger(labels, "gap_event")
        assert (trig["pct"], trig["date"], trig["basis"]) == \
            (pm.GAP_PCT, "2026-07-08", "close_to_close")

    def test_just_inside_the_threshold_does_not_fire(self):
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                path=_path(worst_session_pct=pm.GAP_PCT + 0.01))
        assert "gap_event" not in _names(labels)

    def test_no_price_path_is_NULL(self):
        _labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=-9.0,
                                     ctx=_ctx(), path=None)
        assert _null_reasons(nulls, "gap_event") == ["no_price_path"]

    def test_the_caller_owns_the_missing_path_reason(self):
        # A too-young episode is not an unpriceable one. Collapsing the two once made
        # the artifact report 67 unpriceable episodes where 12 were unpriceable.
        _labels, nulls = pm.classify(outcome_pct=None, excess_pct=None, ctx=_ctx(),
                                     path=None,
                                     path_missing_reason="fill_not_yet_printed")
        assert _null_reasons(nulls, "gap_event") == ["fill_not_yet_printed"]
        assert _null_reasons(nulls, "thesis_break") == ["fill_not_yet_printed"]


# ===========================================================================
# 6. market_beta
# ===========================================================================
class TestMarketBeta:
    def test_fires_when_most_of_the_loss_was_the_tape(self):
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-2.0,
                                ctx=_ctx(), path=_path())
        trig = _trigger(labels, "market_beta")
        assert trig["excess_share_of_loss"] == 0.2

    def test_does_not_fire_when_the_pick_carried_the_loss(self):
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0,
                                ctx=_ctx(), path=_path())
        assert "market_beta" not in _names(labels)

    def test_boundary_is_strict(self):
        at = pm.classify(outcome_pct=-10.0, excess_pct=-(pm.BETA_SHARE_MAX * 10.0),
                         ctx=_ctx(), path=_path())[0]
        assert "market_beta" not in _names(at)

    def test_missing_benchmark_leg_is_NULL(self):
        _labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=None,
                                     ctx=_ctx(), path=_path())
        assert _null_reasons(nulls, "market_beta") == ["no_benchmark_excess"]

    def test_a_winner_is_never_asked(self):
        _labels, nulls = pm.classify(outcome_pct=9.0, excess_pct=None,
                                     ctx=_ctx(), path=_path())
        assert _null_reasons(nulls, "market_beta") == []


# ===========================================================================
# 7. re_admission
# ===========================================================================
class TestReAdmission:
    def test_open_drawdown_leg_is_visible_at_entry(self):
        prior = {"entry_date": "2026-07-01", "outcome_pct": -12.0,
                 "sessions_since_prior_exit": 2, "mark_at_readmit_pct": -9.0}
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                path=_path(), prior=prior)
        assert _visible(labels, "re_admission") is True
        assert _trigger(labels, "re_admission")["leg"] == "open_drawdown_at_readmit"

    def test_prior_episode_loss_leg_is_NOT_visible_at_entry(self):
        # The IPGP shape: the first position was still GREEN on the night the board
        # re-admitted the name, and only rolled over afterwards. Real pattern, but the
        # engine could not have known — and the row says so.
        prior = {"entry_date": "2026-07-10", "outcome_pct": -14.35,
                 "sessions_since_prior_exit": 1, "mark_at_readmit_pct": 3.04}
        labels, _ = pm.classify(outcome_pct=-17.9, excess_pct=-16.7, ctx=_ctx(),
                                path=_path(), prior=prior)
        assert "re_admission" in _names(labels)
        assert _visible(labels, "re_admission") is False
        trig = _trigger(labels, "re_admission")
        assert trig["leg"] == "prior_episode_loss"
        assert trig["mark_at_readmit_pct"] == 3.04

    def test_outside_the_session_window_does_not_fire(self):
        prior = {"entry_date": "2026-05-01", "outcome_pct": -20.0,
                 "sessions_since_prior_exit": pm.READMIT_MAX_SESSIONS + 1,
                 "mark_at_readmit_pct": -20.0}
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                path=_path(), prior=prior)
        assert "re_admission" not in _names(labels)

    def test_a_profitable_prior_episode_does_not_fire(self):
        prior = {"entry_date": "2026-07-01", "outcome_pct": 5.0,
                 "sessions_since_prior_exit": 1, "mark_at_readmit_pct": 4.0}
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                path=_path(), prior=prior)
        assert "re_admission" not in _names(labels)

    def test_a_BIG_profitable_prior_episode_does_not_fire(self):
        """SIGN GUARD. The two legs read `<= -8%`; both thresholds are signed.

        A prior that made +12% has |12| >= |−8|, so any rewrite that reaches for an
        absolute value — `abs(prior_out) >= abs(READMIT_LOSS_PCT)`, the natural typo
        when the constant is negative — turns "re-bought a name that had just LOST
        money" into "re-bought a name that had just MOVED", flags winners, and quietly
        fills the winners-forfeited column that
        `test_the_readmission_veto_forfeits_exactly_zero_winners` pins at zero. The
        +5% prior above cannot catch that (|5| < 8); this one can.
        """
        prior = {"entry_date": "2026-07-01", "outcome_pct": 12.0,
                 "sessions_since_prior_exit": 1, "mark_at_readmit_pct": 11.0,
                 "prior_matured": True}
        labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                    path=_path(), prior=prior)
        assert "re_admission" not in _names(labels)
        assert _null_reasons(nulls, "re_admission") == []   # decided, not skipped

    def test_no_prior_episode_does_not_fire_and_is_a_decided_negative(self):
        # `prior=None` means the caller's scan found no prior run in the window. That is
        # a decided negative and the row must stay in every denominator — nulling it
        # would shrink the universe by every name that has only ever been bought once.
        labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                    path=_path(), prior=None)
        assert "re_admission" not in _names(labels)
        assert _null_reasons(nulls, "re_admission") == []

    def test_the_window_boundary_is_inclusive_at_ten_sessions(self):
        # Literal 10/11, not pm.READMIT_MAX_SESSIONS: see TestThresholdsArePinned.
        def _fire(gap):
            prior = {"entry_date": "2026-07-01", "outcome_pct": -12.0,
                     "sessions_since_prior_exit": gap, "mark_at_readmit_pct": -9.0}
            return "re_admission" in _names(pm.classify(
                outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                path=_path(), prior=prior)[0])
        assert _fire(10) is True
        assert _fire(11) is False

    def test_an_unpriceable_prior_episode_is_NULL_on_the_label_and_BOTH_legs(self):
        # A previous run that cannot be priced is not evidence that the name came back
        # clean. It nulls the label AND both leg keys, because the leg keys are the
        # denominators `veto_cost` costs each variant over — leaving them in would let
        # the buildable row's "0 of N" count rows it never got to look at.
        _labels, nulls = pm.classify(
            outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(), path=_path(),
            prior={"undecidable": "prior_episode_not_scoreable",
                   "n_priors_in_window": 1, "n_priors_unscoreable": 1})
        assert _null_reasons(nulls, "re_admission") == ["prior_episode_not_scoreable"]
        assert _null_reasons(nulls, pm.READMIT_NULL_OPEN_DRAWDOWN) == \
            ["prior_episode_not_scoreable"]
        assert _null_reasons(nulls, pm.READMIT_NULL_PRIOR_LOSS) == \
            ["prior_episode_not_scoreable"]

    def test_a_missing_mark_nulls_ONLY_the_buildable_leg(self):
        # The prior resolved to a loss (hindsight leg decidable) but there is no mark at
        # the re-admission, so the buildable leg had no input at all. Nulling both would
        # throw away a real finding; nulling neither would let the buildable variant
        # report a zero it never measured.
        prior = {"entry_date": "2026-07-01", "outcome_pct": -12.0,
                 "sessions_since_prior_exit": 2, "mark_at_readmit_pct": None,
                 "prior_matured": True}
        labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                    path=_path(), prior=prior)
        assert _trigger(labels, "re_admission")["leg"] == pm.READMIT_LEG_PRIOR_LOSS
        assert _null_reasons(nulls, pm.READMIT_NULL_OPEN_DRAWDOWN) == \
            ["no_mark_at_readmit"]
        assert _null_reasons(nulls, pm.READMIT_NULL_PRIOR_LOSS) == []
        assert _null_reasons(nulls, "re_admission") == []

    def test_an_unmeasurable_gap_is_NULL_not_out_of_window(self):
        prior = {"entry_date": "2026-07-01", "outcome_pct": -12.0,
                 "sessions_since_prior_exit": None, "mark_at_readmit_pct": -9.0}
        labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                    path=_path(), prior=prior)
        assert "re_admission" not in _names(labels)
        assert _null_reasons(nulls, "re_admission") == ["prior_gap_not_measurable"]

    def test_the_trigger_says_whether_the_prior_had_MATURED(self):
        # An unmatured prior's `outcome_pct` is a MARK — outcome-conditioned, and not
        # the same evidence as a resolved loss. The row has to say which it was.
        prior = {"entry_date": "2026-07-10", "outcome_pct": -14.0, "prior_matured": False,
                 "sessions_since_prior_exit": 1, "mark_at_readmit_pct": 3.0,
                 "n_priors_in_window": 2, "selected_by": pm.READMIT_LEG_PRIOR_LOSS}
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                path=_path(), prior=prior)
        trig = _trigger(labels, "re_admission")
        assert trig["prior_matured"] is False
        assert trig["n_priors_in_window"] == 2
        assert trig["selected_by"] == pm.READMIT_LEG_PRIOR_LOSS

    def test_a_caller_that_says_nothing_about_maturity_gets_a_NULL_not_a_False(self):
        prior = {"entry_date": "2026-07-01", "outcome_pct": -12.0,
                 "sessions_since_prior_exit": 2, "mark_at_readmit_pct": -9.0}
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                path=_path(), prior=prior)
        assert _trigger(labels, "re_admission")["prior_matured"] is None


# ===========================================================================
# 7b. re_admission is HINDSIGHT wearing a visible-at-entry badge (M7)
# ===========================================================================
class TestReAdmissionIsNotAVisibleAtEntryLabel:
    def test_the_label_is_not_in_the_visible_at_entry_list(self):
        """The headline is carried by a leg that cannot be read at entry.

        `re_admission`'s +79.08pp counterfactual (2026-07-31 artifact) comes entirely
        from `prior_episode_loss`, which needs the PRIOR episode's resolved outcome — a
        number that does not exist on the night the board re-admits the name (the IPGP
        case was +3.04% green at re-admission). Listing the label as visible-at-entry
        published that hindsight figure under a buildable badge.
        """
        assert "re_admission" not in pm.VISIBLE_AT_ENTRY_LABELS
        assert pm.VISIBLE_AT_ENTRY_LABELS == ("sector_headwind", "bought_extended")

    def test_the_row_level_flag_stays_leg_specific(self):
        # The label-level list is the weaker claim. A row that fired on the open-drawdown
        # leg really WAS visible at entry, and must keep saying so.
        open_leg = {"entry_date": "2026-07-01", "outcome_pct": -12.0,
                    "sessions_since_prior_exit": 2, "mark_at_readmit_pct": -9.0}
        hindsight = {"entry_date": "2026-07-10", "outcome_pct": -14.35,
                     "sessions_since_prior_exit": 1, "mark_at_readmit_pct": 3.04}
        a, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                           path=_path(), prior=open_leg)
        b, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                           path=_path(), prior=hindsight)
        assert _visible(a, "re_admission") is True
        assert _visible(b, "re_admission") is False

    def test_the_aggregation_reports_the_label_as_not_visible_at_entry(self):
        rows = [_row(ticker="A", outcome_pct=-10.0,
                     labels=[_labelled("re_admission", False,
                                       leg=pm.READMIT_LEG_PRIOR_LOSS)])]
        agg = pm.aggregate(rows)
        freq = {f["label"]: f for f in agg["label_frequency"]}
        assert freq["re_admission"]["visible_at_entry"] is False
        assert freq["sector_headwind"]["visible_at_entry"] is True
        tax = {t["label"]: t for t in agg["taxonomy"]}
        assert tax["re_admission"]["visible_at_entry"] is False
        # ...and the reader is told WHY, not just "no": one leg is buildable.
        legs = {lg["leg"]: lg for lg in tax["re_admission"]["legs"]}
        assert legs[pm.READMIT_LEG_OPEN_DRAWDOWN]["visible_at_entry"] is True
        assert legs[pm.READMIT_LEG_PRIOR_LOSS]["visible_at_entry"] is False

    def test_veto_cost_splits_the_label_into_one_row_per_leg(self):
        rows = [
            _row(ticker="H", outcome_pct=-20.0,
                 labels=[_labelled("re_admission", False,
                                   leg=pm.READMIT_LEG_PRIOR_LOSS)]),
            _row(ticker="N", outcome_pct=1.0, labels=[]),
        ]
        veto = {v["key"]: v for v in pm.aggregate(rows)["veto_cost"]}
        assert set(veto) == {"sector_headwind", "bought_extended",
                             "re_admission:open_drawdown_at_readmit",
                             "re_admission:prior_episode_loss"}
        build = veto["re_admission:open_drawdown_at_readmit"]
        hind = veto["re_admission:prior_episode_loss"]
        assert (build["variant"], build["visible_at_entry"]) == ("buildable", True)
        assert (hind["variant"], hind["visible_at_entry"]) == \
            ("hindsight_upper_bound", False)
        # The whole counterfactual sits on the hindsight leg...
        assert (hind["n_flagged"], hind["loss_avoided_pct"]) == (1, 20.0)
        # ...and the buildable row is PRINTED with its zero, never dropped.
        assert (build["n_flagged"], build["loss_avoided_pct"]) == (0, 0.0)
        assert build["n_universe"] == 2

    def test_a_leg_null_shrinks_only_ITS_variants_universe(self):
        rows = [
            _row(ticker="H", outcome_pct=-20.0,
                 labels=[_labelled("re_admission", False,
                                   leg=pm.READMIT_LEG_PRIOR_LOSS)],
                 labels_null=[{"label": pm.READMIT_NULL_OPEN_DRAWDOWN,
                               "reason": "no_mark_at_readmit"}]),
            _row(ticker="N", outcome_pct=1.0, labels=[]),
        ]
        veto = {v["key"]: v for v in pm.aggregate(rows)["veto_cost"]}
        assert veto["re_admission:open_drawdown_at_readmit"]["n_universe"] == 1
        assert veto["re_admission:open_drawdown_at_readmit"]["n_null_disclosed"] == 1
        assert veto["re_admission:prior_episode_loss"]["n_universe"] == 2

    def test_a_row_with_no_recorded_leg_is_never_credited_to_one(self):
        # `_labelled` with no trigger is the shape a hand-written row takes. It must not
        # be guessed into either leg — a veto variant may only count triggers it can see.
        rows = [_row(ticker="H", outcome_pct=-20.0, labels=[_labelled("re_admission")])]
        veto = {v["key"]: v for v in pm.aggregate(rows)["veto_cost"]}
        assert veto["re_admission:open_drawdown_at_readmit"]["n_flagged"] == 0
        assert veto["re_admission:prior_episode_loss"]["n_flagged"] == 0


# ===========================================================================
# 8. multi-label + the residual
# ===========================================================================
class TestMultiLabelAndResidual:
    def test_one_episode_carries_every_label_that_fired(self):
        ctx = _ctx(themes=[{"id": "defense", "reco": "avoid", "label": "fading"}],
                   extension={"overextended": True})
        prior = {"entry_date": "2026-07-01", "outcome_pct": -12.0,
                 "sessions_since_prior_exit": 1, "mark_at_readmit_pct": -9.0}
        labels, _ = pm.classify(
            outcome_pct=-10.0, excess_pct=-2.0, ctx=ctx,
            path=_path(worst_session_pct=-9.0, worst_session_date="2026-07-08",
                       stop_cross_date="2026-07-09", stop_cross_px=88.0),
            prior=prior)
        assert _names(labels) == {"sector_headwind", "bought_extended", "thesis_break",
                                  "gap_event", "market_beta", "re_admission"}

    def test_labels_come_back_in_taxonomy_order(self):
        ctx = _ctx(themes=[{"id": "defense", "reco": "avoid"}],
                   extension={"overextended": True})
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-2.0, ctx=ctx,
                                path=_path(worst_session_pct=-9.0))
        order = [pm.TAXONOMY.index(lb["label"]) for lb in labels]
        assert order == sorted(order)

    def test_idiosyncratic_when_nothing_else_fired(self):
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0,
                                ctx=_ctx(), path=_path())
        assert _names(labels) == {"idiosyncratic"}
        assert _trigger(labels, "idiosyncratic")["fully_checked"] is True

    def test_idiosyncratic_still_fires_with_unchecked_legs_but_says_so(self):
        # An episode with no labels at all would read as a classifier bug; hiding the
        # residual would hide the rows the taxonomy fails to explain. It fires, and the
        # trigger names the legs that were never decidable.
        labels, nulls = pm.classify(outcome_pct=-10.0, excess_pct=None,
                                    ctx=_blank_ctx(), path=None)
        assert "idiosyncratic" in _names(labels)
        trig = _trigger(labels, "idiosyncratic")
        assert trig["fully_checked"] is False
        assert set(trig["unchecked"]) == {"sector_headwind", "bought_extended",
                                          "thesis_break", "gap_event", "market_beta"}
        assert trig["checked"] == ["re_admission"]
        assert len(nulls) >= 5

    def test_every_label_carries_bilingual_copy(self):
        for name in pm.TAXONOMY:
            assert pm.TAXONOMY_COPY[name]["en"]
            assert pm.TAXONOMY_COPY[name]["zh"]
            assert pm.TAXONOMY_COPY[name]["en"] != pm.TAXONOMY_COPY[name]["zh"]


# ===========================================================================
# 9. path_features
# ===========================================================================
class TestPathFeatures:
    @staticmethod
    def _series(vals):
        idx = pd.bdate_range("2026-07-01", periods=len(vals))
        return pd.Series(vals, index=idx, dtype=float)

    def test_worst_session_and_stop_cross(self):
        s = self._series([100, 99, 90, 92, 88])
        out = pm.path_features(s, s.index[0], 4, 91.0)
        assert out["worst_session_pct"] == pytest.approx(-9.0909, abs=1e-3)
        assert out["worst_session_date"] == str(s.index[2].date())
        assert out["stop_cross_date"] == str(s.index[2].date())

    def test_window_stops_at_n_bars(self):
        s = self._series([100, 101, 102, 103, 50])
        out = pm.path_features(s, s.index[0], 3, None)
        assert out["n_bars"] == 3
        assert out["worst_session_pct"] > 0      # the -51% bar is outside the window

    def test_fill_bar_itself_is_never_a_stop_cross(self):
        s = self._series([80, 100, 101])
        out = pm.path_features(s, s.index[0], 2, 90.0)
        assert out["stop_cross_date"] is None    # the 80 IS the fill, not a break

    def test_absent_series_returns_none_not_a_dict_of_nulls(self):
        assert pm.path_features(None, "2026-07-01", 10, 90.0) is None
        assert pm.path_features(pd.Series(dtype=float), "2026-07-01", 10, 90.0) is None

    def test_fill_after_the_series_ends_returns_none(self):
        s = self._series([100, 101])
        assert pm.path_features(s, "2027-01-01", 10, None) is None


# ===========================================================================
# 10. aggregation
# ===========================================================================
class TestAggregate:
    def test_in_flight_rows_enter_no_rate(self):
        rows = [
            _row(ticker="A", outcome_pct=-20.0, excess_pct=-19.0,
                 labels=[_labelled("gap_event")]),
            _row(ticker="B", maturity="in_flight", outcome_pct=-30.0, excess_pct=None,
                 labels=[_labelled("gap_event")]),
        ]
        agg = pm.aggregate(rows)
        assert agg["n_matured"] == 1 and agg["n_in_flight"] == 1
        assert agg["cohorts"]["n_losers"] == 1              # the in-flight row excluded
        gap = next(f for f in agg["label_frequency"] if f["label"] == "gap_event")
        assert gap["n_losers"] == 1
        assert agg["in_flight"]["n_losers_marked"] == 1     # still visible, separately

    def test_veto_cost_counts_winners_forfeited_as_a_first_class_column(self):
        rows = [
            _row(ticker="L", outcome_pct=-10.0, excess_pct=-10.0,
                 labels=[_labelled("sector_headwind", True)]),
            _row(ticker="W", outcome_pct=12.0, excess_pct=12.0,
                 labels=[_labelled("sector_headwind", True)]),
            _row(ticker="C", outcome_pct=1.0, excess_pct=1.0, labels=[]),
        ]
        v = next(x for x in pm.aggregate(rows)["veto_cost"]
                 if x["label"] == "sector_headwind")
        assert v["n_losers_avoided"] == 1 and v["loss_avoided_pct"] == 10.0
        assert v["n_winners_forfeited"] == 1 and v["winners_forfeited_pct"] == 12.0
        assert v["net_pct_if_vetoed"] == -2.0     # the veto LOSES money here

    def test_veto_universe_excludes_rows_the_label_could_not_decide(self):
        rows = [
            _row(ticker="L", outcome_pct=-10.0, labels=[_labelled("sector_headwind", True)]),
            _row(ticker="U", outcome_pct=1.0, labels=[],
                 labels_null=[{"label": "sector_headwind",
                               "reason": "no_theme_state_or_spotlight_at_entry"}]),
        ]
        agg = pm.aggregate(rows)
        v = next(x for x in agg["veto_cost"] if x["label"] == "sector_headwind")
        assert v["n_universe"] == 1 and v["n_matured_total"] == 2
        assert v["flagged_share_of_universe_pct"] == 100.0
        f = next(x for x in agg["label_frequency"] if x["label"] == "sector_headwind")
        assert f["n_null_disclosed"] == 1 and f["n_evaluated"] == 1

    def test_undecidable_rows_never_land_in_the_clean_split(self):
        rows = [
            _row(ticker="H", outcome_pct=-10.0, labels=[_labelled("sector_headwind", True)]),
            _row(ticker="N", outcome_pct=2.0, labels=[]),
            _row(ticker="U", outcome_pct=2.0, labels=[],
                 labels_null=[{"label": "sector_headwind", "reason": "x"}]),
        ]
        splits = pm.aggregate(rows)["cohort_splits"]
        assert splits["headwind_at_entry"]["n"] == 1
        assert splits["no_headwind_at_entry"]["n"] == 1     # NOT 2

    def test_systemic_read_counts_dates_not_rows(self):
        rows = [_row(ticker=f"T{i}", entry_date="2026-07-01", outcome_pct=-10.0,
                     labels=[_labelled("gap_event")]) for i in range(9)]
        rows += [_row(ticker="X", entry_date="2026-07-02", outcome_pct=-10.0, labels=[])]
        sysd = next(x for x in pm.aggregate(rows)["systemic_vs_anomalous"]
                    if x["label"] == "gap_event")
        assert sysd["n_dates"] == 1 and sysd["read"] == "anomalous"

    def test_repeat_offenders_are_sorted_by_total_loss(self):
        rows = [
            _row(ticker="A", entry_date="2026-07-01", outcome_pct=-9.0),
            _row(ticker="A", entry_date="2026-07-08", outcome_pct=-9.0),
            _row(ticker="B", entry_date="2026-07-01", outcome_pct=-20.0),
            _row(ticker="B", entry_date="2026-07-08", outcome_pct=-20.0),
        ]
        rep = pm.aggregate(rows)["repeat_offenders"]
        assert [r["ticker"] for r in rep] == ["B", "A"]

    def test_loss_contribution_uses_ONE_denominator_and_prints_its_coverage(self):
        """The loss-contribution column is comparable down the table, or it is noise.

        Numerator and denominator used to come from different populations' worth of
        thinking: the share column beside it is over the DECIDABLE losers while the
        contribution is over the whole loser book, so a label evaluable on a third of
        the book and one with full reach printed two different 100%s in one column. The
        contribution keeps the whole-book denominator — the only one that is the same on
        every row — and the per-label reach is disclosed separately as coverage.
        """
        rows = [
            # a big loser this label could NOT be decided on
            _row(ticker="U", outcome_pct=-30.0, labels=[],
                 labels_null=[{"label": "sector_headwind", "reason": "x"}]),
            _row(ticker="H", outcome_pct=-10.0,
                 labels=[_labelled("sector_headwind", True)]),
            _row(ticker="C", outcome_pct=-10.0, labels=[]),
        ]
        f = next(x for x in pm.aggregate(rows)["label_frequency"]
                 if x["label"] == "sector_headwind")
        assert f["loss_contribution_pct"] == 20.0            # 10pp of the 50pp book
        assert f["loss_contribution_denominator_pp"] == 50.0
        assert f["loss_contribution_basis"] == "all matured losers' summed absolute loss"
        # ...and the reach that number was earned on, so 20% is never read as full reach
        assert (f["n_losers_evaluated"], f["n_losers_total"]) == (2, 3)
        assert f["loser_coverage_pct"] == 66.7
        assert f["decidable_loss_share_pct"] == 40.0         # 20pp of the 50pp book

    def test_every_label_shares_the_same_contribution_denominator(self):
        rows = [
            _row(ticker="A", outcome_pct=-20.0, labels=[_labelled("gap_event")],
                 labels_null=[{"label": "sector_headwind", "reason": "x"}]),
            _row(ticker="B", outcome_pct=-10.0,
                 labels=[_labelled("sector_headwind", True)]),
        ]
        agg = pm.aggregate(rows)
        denoms = {f["loss_contribution_denominator_pp"] for f in agg["label_frequency"]}
        assert denoms == {30.0} == {agg["cohorts"]["total_loser_loss_pct"]}

    def test_market_beta_diagnostics_print_the_distribution_behind_a_zero(self):
        rows = [_row(ticker="A", outcome_pct=-10.0, excess_pct=-9.0),
                _row(ticker="B", outcome_pct=-20.0, excess_pct=-15.0)]
        d = pm.aggregate(rows)["diagnostics"]["market_beta_excess_share"]
        assert d["n"] == 2 and d["min"] == 0.75 and d["max"] == 0.9

    def test_aggregate_is_order_independent(self):
        rows = [
            _row(ticker="A", entry_date="2026-07-01", outcome_pct=-10.0,
                 labels=[_labelled("gap_event")]),
            _row(ticker="B", entry_date="2026-07-02", outcome_pct=11.0, labels=[]),
            _row(ticker="C", entry_date="2026-07-03", outcome_pct=-9.0,
                 labels=[_labelled("sector_headwind", True)]),
        ]
        assert pm.aggregate(rows) == pm.aggregate(list(reversed(copy.deepcopy(rows))))


# ===========================================================================
# 10b. the prior-episode scan (scripts/prophet_postmortem.prior_episodes)
# ===========================================================================
CAL = pd.bdate_range("2026-06-01", periods=60)


def _series(dips: dict[str, float] | None = None) -> pd.Series:
    s = pd.Series(100.0, index=CAL, dtype=float)
    for day, px in (dips or {}).items():
        s.loc[pd.Timestamp(day)] = px
    return s


def _item(ticker: str, entry: str, exit_: str | None, *, pnl: float | None = None,
          matured: bool = True, series: "pd.Series | None" = None) -> dict:
    sc = None if pnl is None else {"pnl": pnl, "mark": pnl, "matured": matured,
                                   "entry": 100.0}
    return {"ep": {"ticker": ticker, "entry_date": entry, "exit_date": exit_},
            "sc": sc, "series": _series() if series is None and pnl is not None
            else series}


class TestPriorEpisodeScan:
    def test_it_scans_EVERY_prior_in_the_window_not_just_the_last_one(self):
        """`items[i-1]` answered a different question than the label prints.

        A name re-admitted twice inside a fortnight was compared only against its most
        recent run, so a qualifying loss one run further back — still inside the same
        10-session window — was invisible to the label. Here the OLDER prior is the
        loser and the newer one is flat; the scan has to find the older one.
        """
        scored = [
            _item("AAA", "2026-06-15", "2026-06-17", pnl=-12.0),
            _item("AAA", "2026-06-18", "2026-06-19", pnl=1.0),
            _item("AAA", "2026-06-22", None, pnl=-5.0),
        ]
        prior = ppm.prior_episodes(scored, CAL)[("AAA", "2026-06-22")]
        assert prior["entry_date"] == "2026-06-15"
        assert prior["outcome_pct"] == -12.0
        assert prior["selected_by"] == pm.READMIT_LEG_PRIOR_LOSS
        assert prior["n_priors_in_window"] == 2
        assert prior["prior_matured"] is True

    def test_the_buildable_leg_outranks_the_hindsight_leg_in_selection(self):
        # One prior was already under water on the night of the re-admission; the other
        # only resolved into a loss later. Report the one somebody could have acted on.
        scored = [
            _item("AAA", "2026-06-15", "2026-06-17", pnl=-20.0),
            _item("AAA", "2026-06-18", "2026-06-19", pnl=-9.0,
                  series=_series({"2026-06-22": 88.0})),
            _item("AAA", "2026-06-22", None, pnl=-5.0),
        ]
        prior = ppm.prior_episodes(scored, CAL)[("AAA", "2026-06-22")]
        assert prior["selected_by"] == pm.READMIT_LEG_OPEN_DRAWDOWN
        assert prior["entry_date"] == "2026-06-18"
        assert prior["mark_at_readmit_pct"] == pytest.approx(-12.0)

    def test_an_unpriceable_prior_makes_the_row_UNDECIDABLE_not_clean(self):
        # The prior run has no series at all, so nobody can say what it did. Reporting
        # "no re-admission" here is a silent zero — the exact failure this scan owns.
        scored = [
            _item("AAA", "2026-06-15", "2026-06-17", pnl=None),
            _item("AAA", "2026-06-22", None, pnl=-5.0),
        ]
        prior = ppm.prior_episodes(scored, CAL)[("AAA", "2026-06-22")]
        assert prior["undecidable"] == "prior_episode_not_scoreable"
        assert prior["n_priors_unscoreable"] == 1

    def test_a_qualifying_scored_prior_outranks_an_unpriceable_sibling(self):
        # An unpriceable prior only makes the row undecidable when nothing else fired:
        # once a leg has fired, the verdict is the same whatever the sibling did.
        scored = [
            _item("AAA", "2026-06-15", "2026-06-16", pnl=None),
            _item("AAA", "2026-06-17", "2026-06-19", pnl=-12.0),
            _item("AAA", "2026-06-22", None, pnl=-5.0),
        ]
        prior = ppm.prior_episodes(scored, CAL)[("AAA", "2026-06-22")]
        assert "undecidable" not in prior
        assert prior["entry_date"] == "2026-06-17"
        assert prior["n_priors_unscoreable"] == 1

    def test_a_prior_outside_the_window_leaves_no_comparison_at_all(self):
        scored = [
            _item("AAA", "2026-06-01", "2026-06-02", pnl=-30.0),
            _item("AAA", "2026-06-29", None, pnl=-5.0),
        ]
        assert ("AAA", "2026-06-29") not in ppm.prior_episodes(scored, CAL)

    def test_a_non_qualifying_prior_is_still_reported_as_the_comparison_made(self):
        scored = [
            _item("AAA", "2026-06-15", "2026-06-17", pnl=-2.0),
            _item("AAA", "2026-06-22", None, pnl=-5.0),
        ]
        prior = ppm.prior_episodes(scored, CAL)[("AAA", "2026-06-22")]
        assert prior["selected_by"] == "nearest_prior_no_leg_fired"
        assert prior["outcome_pct"] == -2.0

    def test_an_unmatured_prior_is_carried_with_its_maturity_flag(self):
        scored = [
            _item("AAA", "2026-06-15", "2026-06-17", pnl=-12.0, matured=False),
            _item("AAA", "2026-06-22", None, pnl=-5.0),
        ]
        prior = ppm.prior_episodes(scored, CAL)[("AAA", "2026-06-22")]
        assert prior["prior_matured"] is False

    def test_tickers_never_borrow_each_others_history(self):
        scored = [
            _item("AAA", "2026-06-15", "2026-06-17", pnl=-30.0),
            _item("BBB", "2026-06-22", None, pnl=-5.0),
        ]
        assert ppm.prior_episodes(scored, CAL) == {}


# ===========================================================================
# 11. GATE G1 — the operator's loser cohort, over the COMMITTED ledgers
# ===========================================================================
#: The 2026-07-31 track-record worst rows (masterplan §0 G1). Dates are the BOARD log
#: dates; the episode's entry_date is matched with a one-session tolerance because a
#: name can be re-admitted on the adjacent night.
LOSER_COHORT = [
    ("OLN", "2026-07-21"), ("AMKR", "2026-07-17"), ("IPGP", "2026-07-15"),
    ("STAA", "2026-07-15"), ("PSKY", "2026-07-01"), ("FN", "2026-07-21"),
    ("CDNS", "2026-07-09"), ("IPGP", "2026-07-10"), ("UNIT", "2026-07-21"),
    ("HL", "2026-07-01"), ("BG", "2026-07-17"),
]


@pytest.fixture(scope="module")
def artifact():
    """One real run over the committed ledgers (~5s, git archaeology included)."""
    return ppm.build_rows(ROOT)


def _match(doc, ticker, board_date):
    """The episode for (ticker, board_date), tolerating one session of drift."""
    dates = sorted({r["entry_date"] for r in doc["episodes"]})
    if board_date in dates:
        window = {board_date}
    else:
        window = set()
    i = dates.index(board_date) if board_date in dates else None
    if i is not None:
        window |= {dates[j] for j in (i - 1, i + 1) if 0 <= j < len(dates)}
    hits = [r for r in doc["episodes"]
            if r["ticker"] == ticker and r["entry_date"] in window]
    return hits[0] if hits else None


class TestLoserCohortFixture:
    def test_the_run_produces_a_populated_artifact(self, artifact):
        assert artifact["schema"] == ppm.SCHEMA
        assert artifact["method"]["llm_used"] is False
        assert artifact["summary"]["n_matured"] > 100
        assert artifact["coverage"]["basket_revisions"] > 0, \
            "git archaeology returned no baskets revisions — theme context would be empty"

    def test_every_cohort_name_is_classified(self, artifact):
        missing, unlabelled = [], []
        for ticker, date in LOSER_COHORT:
            row = _match(artifact, ticker, date)
            if row is None:
                missing.append(f"{ticker}@{date}")
                continue
            if not row["labels"]:
                unlabelled.append(f"{ticker}@{date}")
        assert not missing, f"cohort names absent from the ledgers: {missing}"
        assert not unlabelled, f"cohort names with no classification: {unlabelled}"

    def test_every_cohort_name_is_in_the_loser_cohort(self, artifact):
        not_losers = [
            f"{t}@{d} -> {(_match(artifact, t, d) or {}).get('cohort')}"
            for t, d in LOSER_COHORT
            if (_match(artifact, t, d) or {}).get("cohort") != "loser"
        ]
        assert not not_losers, not_losers

    def test_every_cohort_name_carries_entry_time_context(self, artifact):
        for ticker, date in LOSER_COHORT:
            ctx = _match(artifact, ticker, date)["entry_context"]
            assert ctx["sector"], f"{ticker}@{date} has no sector at entry"
            # Both tails keep the FULL context, never the compact form.
            assert not ctx.get("compact"), f"{ticker}@{date} was trimmed"
            assert "spotlight" in ctx and "extension" in ctx and "entry_plan" in ctx

    def test_every_label_carries_a_visible_at_entry_flag_and_triggers(self, artifact):
        for ticker, date in LOSER_COHORT:
            for lb in _match(artifact, ticker, date)["labels"]:
                assert isinstance(lb["visible_at_entry"], bool)
                assert lb["label"] in pm.TAXONOMY
                assert lb["trigger"] != {} or lb["label"] == "idiosyncratic"

    def test_IPGP_double_admission_is_flagged(self, artifact):
        """G1's named pin: same ticker re-admitted <= 10 sessions after a >= 8% loss."""
        row = _match(artifact, "IPGP", "2026-07-15")
        labels = {lb["label"]: lb for lb in row["labels"]}
        assert "re_admission" in labels, \
            f"IPGP 07-15 not flagged as a re-admission (labels: {sorted(labels)})"
        trig = labels["re_admission"]["trigger"]
        assert trig["prior_entry_date"] == "2026-07-10"
        assert trig["prior_outcome_pct"] <= pm.READMIT_LOSS_PCT
        assert trig["sessions_since_prior_exit"] <= pm.READMIT_MAX_SESSIONS
        # The honest half: on the night it was re-admitted the first position was still
        # GREEN, so this pattern was NOT visible at entry — and the row says so.
        assert labels["re_admission"]["visible_at_entry"] is False
        assert trig["mark_at_readmit_pct"] > 0

    def test_the_aggregation_carries_the_symmetric_winners_cost(self, artifact):
        for v in artifact["summary"]["veto_cost"]:
            assert "n_winners_forfeited" in v and "winners_forfeited_pct" in v
            assert v["net_pct_if_vetoed"] == pytest.approx(
                v["loss_avoided_pct"] - v["winners_forfeited_pct"], abs=0.01)
        headwind = next(v for v in artifact["summary"]["veto_cost"]
                        if v["label"] == "sector_headwind")
        assert headwind["n_winners_forfeited"] > 0, \
            "a headwind veto that forfeits no winners would be a free lunch — check it"

    def test_the_readmission_veto_forfeits_exactly_zero_winners(self, artifact):
        """A LITERAL zero, on real data, on both legs.

        `re_admission` is the one veto row in the artifact whose winners-forfeited
        column is empty, and an empty symmetric column is the shape of a free lunch —
        so it is the one that has to be pinned rather than admired. The zero is only
        earned because both legs read a SIGNED threshold (`<= -8%`): swap either for an
        absolute value and the label starts flagging names re-bought after a big WIN,
        winners land in the flagged set, and this assertion goes red. Pinned as `== 0`,
        never `is not None`, so the mutation cannot pass by producing some other number.
        """
        readmit = [v for v in artifact["summary"]["veto_cost"]
                   if v["label"] == "re_admission"]
        assert len(readmit) == 2, "both legs must be costed, including an empty one"
        for v in readmit:
            assert v["n_winners_forfeited"] == 0, (
                f"{v['key']} forfeits winners — the label is firing on names that MADE "
                f"money, which means a threshold lost its sign")
            assert v["winners_forfeited_pct"] == 0.0
            assert v["net_pct_if_vetoed"] == v["loss_avoided_pct"]

    def test_the_buildable_readmission_trigger_fires_zero_times_and_prints_it(self, artifact):
        # The finding, not an omission: on this window the ONLY buildable version of the
        # re-admission rule — the earlier position already 8% under water on the night
        # the name came back — never fires. The row exists anyway, with its zero.
        veto = {v["key"]: v for v in artifact["summary"]["veto_cost"]}
        build = veto["re_admission:open_drawdown_at_readmit"]
        hind = veto["re_admission:prior_episode_loss"]
        assert build["variant"] == "buildable" and build["visible_at_entry"] is True
        assert build["n_flagged"] == 0
        assert build["loss_avoided_pct"] == 0.0
        assert build["n_universe"] > 0, "a zero over an empty universe is not a finding"
        # ...and every percentage point of the headline sits on the hindsight leg.
        assert hind["variant"] == "hindsight_upper_bound"
        assert hind["visible_at_entry"] is False
        assert hind["n_flagged"] > 0 and hind["loss_avoided_pct"] > 0

    def test_no_readmission_fire_claims_to_have_been_visible_at_entry(self, artifact):
        # Today every fire is the hindsight leg. If that ever changes the row-level flag
        # may legitimately go True — but a row flagged visible-at-entry must be carrying
        # the open-drawdown leg, never the resolved-loss one.
        seen = set()
        for r in artifact["episodes"]:
            for lb in r["labels"]:
                if lb["label"] != "re_admission":
                    continue
                leg = lb["trigger"]["leg"]
                seen.add(leg)
                assert lb["visible_at_entry"] is (leg == pm.READMIT_LEG_OPEN_DRAWDOWN)
                assert "prior_matured" in lb["trigger"]
        assert seen == {pm.READMIT_LEG_PRIOR_LOSS}, \
            f"the leg mix moved: {sorted(seen)} — re-read the veto table before shipping"

    def test_prior_episode_comparisons_are_written_onto_the_rows(self, artifact):
        # Every comparison the scan made, including the ones that produced no label —
        # those are the ones a reader cannot otherwise see.
        with_prior = [r for r in artifact["episodes"] if r["prior_episode"]]
        assert with_prior, "no prior-episode comparisons recorded at all"
        for r in with_prior:
            p = r["prior_episode"]
            assert p["n_priors_in_window"] >= 1
            if p.get("undecidable"):
                assert p["n_priors_unscoreable"] >= 1
                # an undecidable prior nulls the label AND both legs
                nulled = {n["label"] for n in r["labels_null"]}
                assert {"re_admission", pm.READMIT_NULL_OPEN_DRAWDOWN,
                        pm.READMIT_NULL_PRIOR_LOSS} <= nulled
            else:
                assert isinstance(p["prior_matured"], bool)
                assert p["selected_by"] in (
                    pm.READMIT_LEG_OPEN_DRAWDOWN, pm.READMIT_LEG_PRIOR_LOSS,
                    "nearest_prior_no_leg_fired")
        # ...and a row with no in-window prior says so with a null, not a missing key.
        assert all("prior_episode" in r for r in artifact["episodes"])

    def test_no_price_path_tickers_are_disclosed_not_dropped(self, artifact):
        cov = artifact["coverage"]
        assert cov["n_no_price_path"] == len(
            [r for r in artifact["episodes"]
             if any(n["reason"] == "no_price_path" for n in r["labels_null"])])

    def test_the_run_is_deterministic(self, artifact):
        again = ppm.build_rows(ROOT)
        assert again["summary"] == artifact["summary"]
        assert [r["ticker"] for r in again["episodes"]] == \
            [r["ticker"] for r in artifact["episodes"]]

    def test_the_report_renders_and_names_the_cohort(self, artifact):
        text = ppm.render_report(artifact)
        for ticker, _date in LOSER_COHORT:
            assert f"| {ticker} |" in text, f"{ticker} missing from the report tables"
        assert "Winners forfeited" in text
        assert "validated" not in text.lower()

    def test_the_report_splits_the_loser_book_by_maturity_and_the_counts_add_up(
            self, artifact):
        """Matured and marked-to-market rows never share a table.

        One pooled loser table sorted today's worst OPEN positions to the top of the
        page — which is the read the maturity gate exists to prevent, arriving through
        the layout instead of through a rate. Two labelled blocks, and section counts
        that reconcile to the stated total, so a reader can check nothing was dropped
        between them.
        """
        text = ppm.render_report(artifact)
        losers = [r for r in artifact["episodes"] if r["cohort"] == "loser"]
        n_matured = len([r for r in losers if r["maturity"] == "matured"])
        n_flight = len([r for r in losers if r["maturity"] == "in_flight"])
        n_other = len(losers) - n_matured - n_flight

        assert f"### Matured losers ({n_matured})" in text
        assert f"### In-flight losers ({n_flight})" in text
        assert f"= {len(losers)}." in text
        assert n_matured + n_flight + n_other == len(losers)
        # the matured block is exactly what every rate above was computed on
        assert n_matured == artifact["summary"]["cohorts"]["n_losers"]
        # each block's table carries its own rows, and only its own
        head, _, tail = text.partition(f"### In-flight losers ({n_flight})")
        matured_block = head.rpartition(f"### Matured losers ({n_matured})")[2]
        for r in losers:
            line = f"| {r['ticker']} | {r['entry_date']} |"
            assert (line in matured_block) is (r["maturity"] == "matured"), \
                f"{r['ticker']}@{r['entry_date']} is in the wrong maturity block"
        assert "In-flight rows (classified, counted in no rate)" in tail

    def test_the_in_flight_block_reconciles_to_its_own_total(self, artifact):
        text = ppm.render_report(artifact)
        f = artifact["summary"]["in_flight"]
        assert (f["n_losers_marked"] + f["n_winners_marked"] + f["n_neutral_marked"]
                + f["n_unscored_marked"]) == f["n"]
        assert (f"{f['n_losers_marked']} at loser levels · "
                f"{f['n_winners_marked']} at winner levels · "
                f"{f['n_neutral_marked']} neutral · "
                f"{f['n_unscored_marked']} unscored = {f['n']}") in text

    def test_the_report_marks_the_hindsight_row_as_hindsight(self, artifact):
        """The +79pp may not appear on the page without its epistemic status attached."""
        text = ppm.render_report(artifact)
        veto = {v["key"]: v for v in artifact["summary"]["veto_cost"]}
        hind = veto["re_admission:prior_episode_loss"]
        build = veto["re_admission:open_drawdown_at_readmit"]
        assert "| `re_admission:prior_episode_loss` | hindsight upper bound |" in text
        assert "| `re_admission:open_drawdown_at_readmit` | buildable |" in text
        assert f"{hind['loss_avoided_pct']:.2f}pp on this line is a CEILING" in text
        # the buildable row is printed WITH its zero rather than dropped
        assert build["n_flagged"] == 0
        assert "it fires **zero** times on this window" in text
        assert "Dates flagged" in text      # n_dates_flagged reaches the reader

    def test_the_taxonomy_table_prints_per_label_coverage(self, artifact):
        text = ppm.render_report(artifact)
        assert "loser coverage" in text
        for f in artifact["summary"]["label_frequency"]:
            assert f"| {f['n_losers_evaluated']} / {f['n_losers_total']} " in text
