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
        assert ubr.BOARD_DEFINITION == "us_prophet_v1"

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
    def test_map_is_the_china_map_verbatim(self):
        from engine import china_board_rank as cn
        assert ubr._ENTRY_VALUE == cn._ENTRY_VALUE

    @pytest.mark.parametrize("status,expected", [
        ("buy_now", 1.0), ("partial", 0.9), ("buy_soon", 0.8), ("hold", 0.65),
        ("await_confluence", 0.45), ("watch", 0.4), ("bounce_wait", 0.35),
        ("extended", 0.0), ("topping", 0.0), ("blocked", 0.0), ("avoid", 0.0),
    ])
    def test_values(self, status, expected):
        assert ubr.entry_value({"status": status}) == pytest.approx(expected)

    def test_unknown_and_missing_score_zero(self):
        assert ubr.entry_value({"status": "banana"}) == 0.0
        assert ubr.entry_value({}) == 0.0
        assert ubr.entry_value(None) == 0.0

    def test_status_is_case_insensitive(self):
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

    def test_single_row_pool(self):
        assert ubr.alpha_percentiles([_row("A", alpha=0.1)])[0] == pytest.approx(1.0)

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

    def test_downtrend_with_an_entry_status_keeps_that_status_bucket(self):
        assert ubr.stage_for({"dir": "down"}, {"status": "bounce_wait"}) == "setting_up"

    def test_blocked_status_beats_everything(self):
        assert ubr.stage_for({"dir": "up"}, {"status": "avoid"}) == "blocked"

    def test_unknown_or_missing_status_is_setting_up_never_live(self):
        for entry in ({}, None, {"status": ""}, {"status": "banana"}):
            assert ubr.stage_for({}, entry) == "setting_up"

    def test_stage_rank_order(self):
        ranks = [ubr.stage_rank(s) for s in
                 ("live", "setting_up", "ran", "blocked")]
        assert ranks == sorted(ranks) == [0, 1, 2, 3]

    def test_unknown_stage_sorts_last(self):
        assert ubr.stage_rank("banana") > ubr.stage_rank("blocked")

    def test_reads_the_row_when_no_entry_is_passed(self):
        assert ubr.stage_for({"entry_signal": {"status": "buy_now"}}) == "live"


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


# ---------------------------------------------------------------------------
# 5. featured
# ---------------------------------------------------------------------------

class TestFeatured:
    def test_a_clean_live_row_qualifies(self):
        assert ubr.featured_shortfalls(_row("A")) == []

    def test_ticks_zero_qualifies(self):
        """REGRESSION: `(v.get("ticks") or 99) <= 2` treats a same-day cross — the
        freshest and best signal there is — as missing, and un-features exactly the
        rows the board most wants to feature."""
        assert ubr.featured_shortfalls(_row("A", ticks=0)) == []

    def test_ticks_none_does_not_qualify(self):
        assert "ticks_unknown" in ubr.featured_shortfalls(_row("A", ticks=None))

    def test_ticks_three_is_stale(self):
        assert "ticks_stale" in ubr.featured_shortfalls(_row("A", ticks=3))
        assert ubr.featured_shortfalls(_row("A", ticks=2)) == []

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
        assert ubr.featured_shortfalls(_row("A", alpha=0.0)) == []

    def test_unknown_alpha_is_out(self):
        assert "alpha_unknown" in ubr.featured_shortfalls(_row("A", alpha=None))

    def test_extension_and_antichase_block(self):
        assert "extended" in ubr.featured_shortfalls(_row("A", ext_z=2.5))
        assert ubr.featured_shortfalls(_row("A", ext_z=2.0)) == []   # not > 2
        assert "antichase_blocked" in ubr.featured_shortfalls(
            _row("A", antichase_shadow_blocked=True))

    def test_earnings_blackout_blocks_from_either_source(self):
        assert "earnings_blackout" in ubr.featured_shortfalls(
            _row("A", earnings_soon={"in_blackout": True}))
        assert "earnings_blackout" in ubr.featured_shortfalls(
            _row("A"), in_blackout=True)

    def test_board_cap(self):
        # every alpha non-negative, so the cap is the only thing that can bind
        rows = [_row(f"T{i:02d}", sector=f"S{i}", alpha=20.0 - i) for i in range(20)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        featured = [r for r in scored if r["featured"]]
        assert len(featured) == ubr.FEATURED_CAP
        assert ["featured_cap"] in [
            r.get("featured_blocked_by") for r in scored if not r["featured"]]

    def test_sector_cap(self):
        rows = [_row(f"T{i:02d}", sector="Utilities", alpha=8.0 - i) for i in range(8)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        featured = [r for r in scored if r["featured"]]
        assert len(featured) == ubr.SECTOR_CAP
        assert ["sector_cap"] in [
            r.get("featured_blocked_by") for r in scored if not r["featured"]]

    def test_featured_is_taken_by_score_desc(self):
        rows = [_row("LOW", alpha=0.1, sector="A"), _row("HIGH", alpha=5.0, sector="B")]
        scored = ubr.score_rows(rows, board_asof="2026-07-31",
                                featured_cap=1, sector_cap=4)
        featured = [r["ticker"] for r in scored if r["featured"]]
        assert featured == ["HIGH"]

    def test_featured_never_changes_membership(self):
        rows = [_row("A"), _row("B", status="avoid", alpha=-2.0)]
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        assert {r["ticker"] for r in scored} == {"A", "B"}

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

    def test_a_perfect_row_scores_100(self):
        scored = ubr.score_rows(
            [_row("A", status="buy_now", tier="T2", ticks=1, alpha=1.0,
                  ext_z=0.0, coiled={"star": True})],
            board_asof="2026-07-31")
        assert scored[0]["prophet"]["score"] == pytest.approx(100.0)

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
            "live": 1, "setting_up": 0, "ran": 0, "blocked": 0}

    def test_empty_pool_is_not_a_crash(self):
        assert ubr.score_rows([], board_asof="2026-07-31") == []


class TestRankingBlock:
    def test_block_discloses_the_formula_and_the_scoreless_inputs(self):
        scored = ubr.score_rows([_row("A")], board_asof="2026-07-31")
        block = ubr.ranking_block(scored)
        assert block["definition"] == "us_prophet_v1"
        assert block["score_kind"] == ubr.SCORE_KIND
        assert {p["component"] for p in block["formula_points"]} == set(
            ubr.SCORE_WEIGHTS)
        assert sum(p["points"] for p in block["formula_points"]) == 100.0
        assert block["zero_score_authority"] == list(ubr.ZERO_SCORE_AUTHORITY)
        assert block["featured_count"] == 1
        assert block["stage_order"] == ["live", "setting_up", "ran", "blocked"]

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

def _ran_verdict(ticks, *, eligible=False, above200=True, weekly_bull=True,
                 last=None, asof="2026-07-31"):
    v = {"eligible": eligible, "ticks": ticks, "above200": above200,
         "weekly_bull": weekly_bull, "asof": asof}
    if last is not None:
        v["last"] = last
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

    def test_cross_date_anchor_wins(self):
        read = ubr.cross_read(self._DATES, self._CLOSES,
                              cross_date="2026-07-22", sessions_back=1)
        assert read["cross_date"] == "2026-07-22"
        assert read["sessions_since"] == 7
        assert read["pct_since"] == pytest.approx(round((110 / 102 - 1) * 100, 1))

    def test_cross_date_between_sessions_anchors_to_the_last_one_at_or_before(self):
        read = ubr.cross_read(self._DATES, self._CLOSES, cross_date="2026-07-26")
        assert read["cross_date"] == "2026-07-24"

    def test_cross_date_before_the_series_falls_back_to_sessions_back(self):
        read = ubr.cross_read(self._DATES, self._CLOSES,
                              cross_date="2020-01-01", sessions_back=2)
        assert read["cross_date"] == "2026-07-29"

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
        assert row["days_since_signal"] == 0

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
        """No price history is a null to print, not a row to hide."""
        rows = ubr.build_ran_rows({"A": _ran_verdict(4)}, close_of=lambda _t: None)
        assert rows[0]["pct_since"] is None and rows[0]["sessions_since"] is None
        assert rows[0]["ticks"] == 4

    def test_no_close_accessor_at_all(self):
        rows = ubr.build_ran_rows({"A": _ran_verdict(4)})
        assert [r["ticker"] for r in rows] == ["A"]

    def test_marker_date_is_preferred_over_the_tick_count(self):
        """ticks are counted on the signal's own higher-timeframe grid, so the §7
        marker date is the only exact anchor when it exists."""
        rows = ubr.build_ran_rows(
            {"A": _ran_verdict(4, last={"type": "buy", "date": "2026-07-21"})},
            close_of=self._close_of)
        assert rows[0]["cross_date"] == "2026-07-21"
        assert rows[0]["sessions_since"] == 8      # not 4

    def test_a_sell_marker_is_not_a_cross_anchor(self):
        rows = ubr.build_ran_rows(
            {"A": _ran_verdict(4, last={"type": "sell", "date": "2026-07-21"})},
            close_of=self._close_of)
        assert rows[0]["cross_date"] == "2026-07-27"   # fell back to ticks

    def test_json_serialisable(self):
        rows = ubr.build_ran_rows({"A": _ran_verdict(4)}, close_of=self._close_of,
                                  theme_by={"A": {"id": "x", "bull_days": 2}})
        json.dumps(rows, allow_nan=False)

    def test_empty_verdicts(self):
        assert ubr.build_ran_rows({}) == []
        assert ubr.build_ran_rows(None) == []


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

    def test_no_blocked_row_ranks_above_any_live_row(self, scored):
        _board, rows = scored
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

    def test_featured_respects_both_caps(self, scored):
        from collections import Counter
        _board, rows = scored
        featured = [r for r in rows if r["featured"]]
        assert 0 < len(featured) <= ubr.FEATURED_CAP
        assert max(Counter(r["sector"] for r in featured).values()) <= ubr.SECTOR_CAP

    def test_every_featured_row_is_actionable_today(self, scored):
        _board, rows = scored
        for r in (r for r in rows if r["featured"]):
            assert r["stage"] == "live"
            assert r["entry_signal"]["status"] in ("buy_now", "partial")
            assert float(r["alpha"]) >= 0
            assert r["signal"]["tier_cascade"] in ("T1", "T2", "T3")
            assert r["signal"]["ticks"] is not None and r["signal"]["ticks"] <= 2

    def test_a_same_day_cross_is_featurable_on_real_data(self, scored):
        """The ticks==0 trap, pinned against production rows: the 07-31 board carries
        same-day crosses, and truthiness testing would silently drop every one."""
        _board, rows = scored
        zero_tick = [r for r in rows if (r.get("signal") or {}).get("ticks") == 0]
        assert zero_tick, "fixture must contain a same-day cross"
        assert any(r["featured"] for r in zero_tick), (
            "no ticks==0 row was featured — check for `(ticks or 99) <= 2`")

    def test_every_row_carries_the_display_contract(self, scored):
        _board, rows = scored
        for r in rows:
            for key in ("stage", "featured", "new", "score_rank", "display_rank",
                        "prophet", "days_since_signal"):
                assert key in r, key
            assert r["prophet"]["version"] == "us_prophet_v1"
            assert isinstance(r["featured"], bool) and isinstance(r["new"], bool)
        assert [r["display_rank"] for r in rows] == list(range(1, len(rows) + 1))

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
