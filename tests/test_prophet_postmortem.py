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


def _labelled(name: str, visible: bool = False) -> dict:
    return {"label": name, "visible_at_entry": visible, "trigger": {}}


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

    def test_no_prior_episode_does_not_fire(self):
        labels, _ = pm.classify(outcome_pct=-10.0, excess_pct=-9.0, ctx=_ctx(),
                                path=_path(), prior=None)
        assert "re_admission" not in _names(labels)


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
