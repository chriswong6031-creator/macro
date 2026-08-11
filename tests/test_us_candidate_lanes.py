"""Tests for engine/us_candidate_lanes.py — the US candidate-pool lane partition.

Five things are pinned here, in order of how badly a regression would hurt:

1. **NO AUTHORITY LEAK.**  This is a display-tier block over a scored board.  If any
   admission-path module ever learns to read it, the board's membership starts depending
   on a lower tier that was built precisely because it has no say.  ``TestNoAuthorityLeak``
   pins that three ways — a static token sweep over every module tree, an import-closure
   walk from the three authority modules, and a BEHAVIOURAL invariance check that
   ``prophet_bridge.select_candidates`` returns the same list with and without the block.
2. **buy[] IS UNTOUCHED.**  Membership, order and the row objects themselves.
   ``TestBuyLaneUntouched`` deep-compares against a pre-change snapshot; the mutation
   check for it is recorded in the PR body.
3. **THE PARTITION IS LOSSLESS** — ``sum(lane_counts) == len(rows) == eligible``, every
   eligible name exactly once, every off-board name with a non-empty reason.  This is the
   CN invariant (``china_board_rank._partition``) and the whole point of the block.
4. **THE STORE SCHEMA.**  ``pool_*`` columns land on the existing candidates store under
   its own rules — schema union, keep-first, null off the pool, no permanently-dead
   column.
5. **GRADUATION DERIVES FROM THE STORE**, not from anything the builder happens to hold
   in memory, and is absent rather than faked when there is no history.

Hermetic: every store test passes ``root=tmp_path`` with ``event_rows={}`` and
``with_context_dims=False``, so nothing reads the repo's real ``data/`` tree.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from engine import us_candidate_lanes as ucl
from engine import us_context_vector as ucv

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# fixtures — a synthetic board with every lane and every drop reason represented
# --------------------------------------------------------------------------- #

def _buy_row(ticker, *, featured=False, status="buy_now", band="high", tone="up",
             tier="T2", score=70.0, blocked=None, sector="Industrials"):
    row = {
        "ticker": ticker,
        "name": f"{ticker} Inc",
        "sector": sector,
        "dir": tone,
        "stage": "live",
        "align_tier": tier,
        "featured": featured,
        "entry_signal": {"status": status},
        "conviction": {"band": band},
        "signal": {"tier_cascade": tier},
        "prophet": {
            "version": "us_prophet_v2",
            "score": score,
            "components": {"signal": 1.0, "entry": 1.0, "edge": 0.5,
                           "runway": 1.0, "quality": 0.4},
            "points": {"signal": 30.0, "entry": 25.0, "edge": 12.5,
                       "runway": 10.0, "quality": 4.0},
            "alpha_percentile": 0.5,
            "zero_score_authority": ["blowoff_risk"],
        },
    }
    if blocked is not None:
        row["featured_blocked_by"] = list(blocked)
    return row


@pytest.fixture
def board():
    """8 buy rows spanning every lane + 4 off-board eligibles, one per drop reason."""
    buy = [
        # cleared admission, board-featured        -> featured
        _buy_row("AAA", featured=True),
        # cleared admission, blocked by the featured cap -> more_actionable
        _buy_row("BBB", blocked=["featured_cap"]),
        # cleared admission, no blocked-by field at all  -> more_actionable
        _buy_row("CCC"),
        # ran too far                              -> late_or_unfillable
        _buy_row("DDD", status="extended", blocked=["entry_status_extended"]),
        # standing aside                           -> late_or_unfillable
        _buy_row("EEE", status="avoid", blocked=["entry_status_avoid"]),
        # entry has not arrived                    -> forming
        _buy_row("FFF", status="buy_soon", blocked=["entry_status_buy_soon"]),
        # conviction band low                      -> forming
        _buy_row("GGG", band="low", blocked=["alpha_below_floor"]),
        # cascade graded it out                    -> forming
        _buy_row("HHH", tier="T4", blocked=["tier_T4"]),
    ]
    off = {
        "III": ["sector_cap_overflow"],
        "JJJ": ["dual_class_duplicate"],
        "KKK": ["buy_slice_cap"],
        "LLL": ["sector_label_unreadable"],
        # W1.5 earnings-blackout hygiene gate — the drop site that shipped
        # uninstrumented and put 6 real names in the fail-closed bucket
        "MMM": ["event_blackout"],
    }
    eligible_order = [r["ticker"] for r in buy] + list(off)
    meta = {t: {"name": f"{t} Inc", "sector": "Industrials"} for t in off}
    return {
        "buy": buy,
        "off_board_reasons": off,
        "eligible_order": eligible_order,
        "meta_rows": meta,
    }


def _build(board, **overrides):
    kwargs = {
        "as_of": "2026-08-07",
        "board_definition": "us_prophet_v2",
        "selection_era": "anticipation-v1-2026-08-08",
        "eligible_order": board["eligible_order"],
        "buy_rows": board["buy"],
        "off_board_reasons": board["off_board_reasons"],
        "meta_rows": board["meta_rows"],
    }
    kwargs.update(overrides)
    return ucl.build_candidate_pool(**kwargs)


# --------------------------------------------------------------------------- #
# 1. the lossless invariant (CN parity)
# --------------------------------------------------------------------------- #

class TestLosslessPartition:
    """sum(lane_counts) == len(rows) == eligible, and every name lands exactly once."""

    def test_counts_reconcile(self, board):
        block = _build(board)
        assert block["eligible"] == len(board["eligible_order"]) == 13
        assert len(block["rows"]) == block["eligible"]
        assert sum(block["lane_counts"].values()) == block["eligible"]

    def test_every_eligible_name_appears_exactly_once(self, board):
        block = _build(board)
        tickers = [r["ticker"] for r in block["rows"]]
        assert sorted(tickers) == sorted(board["eligible_order"])
        assert len(tickers) == len(set(tickers))

    def test_lane_counts_cover_exactly_the_declared_lanes(self, board):
        block = _build(board)
        assert set(block["lane_counts"]) == set(ucl.LANE_ORDER)
        assert block["lane_order"] == list(ucl.LANE_ORDER)

    def test_in_buy_lane_and_off_buy_lane_sum_to_eligible(self, board):
        block = _build(board)
        assert block["in_buy_lane"] == 8
        assert block["off_buy_lane"] == 5
        assert block["in_buy_lane"] + block["off_buy_lane"] == block["eligible"]

    def test_display_rank_is_dense_within_every_lane(self, board):
        block = _build(board)
        for lane in ucl.LANE_ORDER:
            ranks = sorted(r["display_rank"] for r in block["rows"] if r["lane"] == lane)
            assert ranks == list(range(1, len(ranks) + 1))

    def test_pool_rank_is_the_blend_order(self, board):
        block = _build(board)
        by_ticker = {r["ticker"]: r["pool_rank"] for r in block["rows"]}
        assert [by_ticker[t] for t in board["eligible_order"]] == list(range(1, 14))

    def test_a_buy_row_missing_from_the_eligible_order_is_still_published(self, board):
        """Fail-closed: the pool must never lose a published name."""
        block = _build(board, eligible_order=board["eligible_order"][1:])
        assert "AAA" in {r["ticker"] for r in block["rows"]}
        assert block["orphan_buy_rows"] == ["AAA"]
        assert sum(block["lane_counts"].values()) == len(block["rows"])


# --------------------------------------------------------------------------- #
# 2. buy[] membership + order are untouched
# --------------------------------------------------------------------------- #

class TestBuyLaneUntouched:
    """The partition is ADDITIVE.  It may not touch the board it describes.

    MUTATION CHECK (recorded, run locally before merge): turning the lane assignment in
    ``build_candidate_pool`` into a membership change — ``buy_rows`` filtered to the
    featured lane before the loop — reds ``test_membership_and_order_are_identical``
    and ``test_row_objects_are_not_aliased``.  Restored after.
    """

    def test_membership_and_order_are_identical(self, board):
        before = copy.deepcopy(board["buy"])
        _build(board)
        assert [r["ticker"] for r in board["buy"]] == [r["ticker"] for r in before]
        assert board["buy"] == before

    def test_no_new_keys_reach_the_board_rows(self, board):
        keys_before = [set(r) for r in board["buy"]]
        _build(board)
        assert [set(r) for r in board["buy"]] == keys_before

    def test_row_objects_are_not_aliased(self, board):
        block = _build(board)
        board_ids = {id(r) for r in board["buy"]}
        assert not any(id(r) in board_ids for r in block["rows"])
        # nested structures are copied too, so a later edit of the block cannot reach
        # the artifact's own prophet block
        pool_aaa = next(r for r in block["rows"] if r["ticker"] == "AAA")
        pool_aaa["prophet"]["components"]["signal"] = -99
        assert board["buy"][0]["prophet"]["components"]["signal"] == 1.0

    def test_a_second_build_is_byte_identical(self, board):
        first = json.dumps(_build(board), sort_keys=True, default=str)
        second = json.dumps(_build(board), sort_keys=True, default=str)
        assert first == second


# --------------------------------------------------------------------------- #
# 3. lane taxonomy + honest reasons
# --------------------------------------------------------------------------- #

class TestLaneTaxonomy:

    @pytest.mark.parametrize("ticker,lane", [
        ("AAA", ucl.LANE_FEATURED),
        ("BBB", ucl.LANE_MORE_ACTIONABLE),
        ("CCC", ucl.LANE_MORE_ACTIONABLE),
        ("DDD", ucl.LANE_LATE_OR_UNFILLABLE),
        ("EEE", ucl.LANE_LATE_OR_UNFILLABLE),
        ("FFF", ucl.LANE_FORMING),
        ("GGG", ucl.LANE_FORMING),
        ("HHH", ucl.LANE_FORMING),
        ("III", ucl.LANE_MORE_ACTIONABLE),
        ("JJJ", ucl.LANE_MORE_ACTIONABLE),
        ("KKK", ucl.LANE_MORE_ACTIONABLE),
        ("LLL", ucl.LANE_FORMING),
        ("MMM", ucl.LANE_LATE_OR_UNFILLABLE),
    ])
    def test_row_lands_in_its_lane(self, board, ticker, lane):
        block = _build(board)
        row = next(r for r in block["rows"] if r["ticker"] == ticker)
        assert row["lane"] == lane

    def test_every_row_carries_a_non_empty_reason(self, board):
        block = _build(board)
        for row in block["rows"]:
            assert row["lane_reasons"], row["ticker"]
            assert row["headline_reason"] == row["lane_reasons"][0]

    def test_off_board_eligibles_all_carry_reasons(self, board):
        block = _build(board)
        off = [r for r in block["rows"] if not r["in_buy_lane"]]
        assert len(off) == 5
        for row in off:
            assert row["lane_reasons"]
            assert row["headline_reason"] in ucl.OFF_BOARD_REASONS

    def test_reason_vocabulary_is_prophet_bridges_own(self, board):
        """No second vocabulary — refused rows use REFUSAL_ORDER codes verbatim."""
        from engine import prophet_bridge as pb

        block = _build(board)
        refused = {"DDD": "ran_too_far", "EEE": "stood_down",
                   "FFF": "not_ready", "GGG": "conviction_low", "HHH": "grade_low"}
        for ticker, code in refused.items():
            row = next(r for r in block["rows"] if r["ticker"] == ticker)
            assert code in row["lane_reasons"]
            assert code in pb.REFUSAL_ORDER

    def test_a_blackout_suppressed_eligible_is_blocked_not_forming(self, board):
        """M1a.  The W1.5 hygiene gate removes intact setups for a DATED event.

        Filing them under `forming` would say the setup had not developed, which is
        false — and `earnings_blackout_note` in the same artifact names them, so the two
        blocks would contradict each other.  Six real names on the 2026-08-07 board
        (UAMY, ASTS, LITE, SVM, CRC, ONON) sat in `off_board_reason_unknown` before this.
        """
        block = _build(board)
        row = next(r for r in block["rows"] if r["ticker"] == "MMM")
        assert row["lane"] == ucl.LANE_LATE_OR_UNFILLABLE
        assert row["headline_reason"] == "event_blackout"
        assert row["in_buy_lane"] is False
        assert ucl.OFF_BOARD_REASONS["event_blackout"] == ucl.LANE_LATE_OR_UNFILLABLE
        # and it never reaches the alarm bucket
        assert "MMM" not in block["unknown_reason_tickers"]

    def test_the_builder_stamps_event_blackout_at_the_drop_site(self):
        """The reason is only honest if the DROP SITE writes it.

        Pins the wiring in scripts/build_stock_library.py, not just the taxonomy — the
        defect was a missing `_pool_off_board` entry, and a taxonomy-only test would have
        passed straight through it.
        """
        source = (REPO / "scripts" / "build_stock_library.py").read_text()
        assert source.count('_pool_off_board[_t_eb] = ["event_blackout"]') == 2, (
            "both earnings-blackout drop sites (trend lane + Lane-R recovery) must "
            "stamp the pool reason")

    def test_a_pending_expired_row_is_blocked_however_the_gate_reads_it(self, board):
        """M4.  `_expire_pending_buys` demotes INSIDE buy[]; no admission gate sees it."""
        board["buy"][0]["pending_expired"] = True          # AAA: featured + expired
        block = _build(board)
        row = next(r for r in block["rows"] if r["ticker"] == "AAA")
        assert row["lane"] == ucl.LANE_LATE_OR_UNFILLABLE
        assert row["headline_reason"] == ucl.PENDING_EXPIRED
        assert block["lane_counts"][ucl.LANE_FEATURED] == 0

    def test_an_unaccounted_eligible_fails_closed_into_forming(self, board):
        block = _build(board, off_board_reasons={})
        row = next(r for r in block["rows"] if r["ticker"] == "III")
        assert row["lane"] == ucl.LANE_FORMING
        assert row["headline_reason"] == "off_board_reason_unknown"

    def test_an_open_plan_is_not_a_refusal(self, board):
        block = _build(board, open_tickers=["AAA", "CCC"])
        aaa = next(r for r in block["rows"] if r["ticker"] == "AAA")
        ccc = next(r for r in block["rows"] if r["ticker"] == "CCC")
        assert aaa["lane"] == ucl.LANE_FEATURED
        assert ccc["lane"] == ucl.LANE_MORE_ACTIONABLE
        assert "already_open" in aaa["lane_reasons"]
        assert "already_open" in ccc["lane_reasons"]

    def test_off_board_rows_carry_no_score_and_say_so(self, board):
        block = _build(board)
        for row in block["rows"]:
            if row["in_buy_lane"]:
                assert row["prophet"]["score"] == 70.0
                assert row["prophet_score_basis"] == "buy_lane_pool"
            else:
                assert row["prophet"] is None
                assert row["prophet_score_basis"] is None


# --------------------------------------------------------------------------- #
# 4. disclosure — display caps, declined basis, featured divergence
# --------------------------------------------------------------------------- #

class TestDisclosure:

    def test_display_caps_are_carried_through(self, board):
        caps = {"sector_cap": {"value": 10, "displaced": 55},
                "watch_slice": {"value": 48, "considered": 703, "displaced": 655}}
        block = _build(board, display_caps=caps)
        assert block["display_caps"]["sector_cap"]["displaced"] == 55
        assert block["display_caps"]["watch_slice"]["considered"] == 703

    def test_the_pool_block_itself_is_never_truncated(self, board):
        """Caps trim other lanes; the pool publishes every eligible row."""
        block = _build(board, display_caps={"watch_slice": {"value": 1}})
        assert len(block["rows"]) == block["eligible"]

    def test_declined_basis_names_build_prophet_as_canonical(self, board):
        block = _build(board)
        assert block["declined_basis"] == "build_site_gate_only"
        assert "build_prophet" in block["declined_basis_note"]

    def test_board_featured_divergence_is_disclosed_not_reconciled(self, board):
        """A board-featured row the intake refuses is named, never silently recounted."""
        board["buy"][0]["conviction"] = {"band": "low"}      # AAA: featured + refused
        block = _build(board)
        assert block["board_featured_count"] == 1
        assert block["lane_counts"][ucl.LANE_FEATURED] == 0
        assert block["featured_divergence"] == [
            {"ticker": "AAA", "pool_lane": ucl.LANE_FORMING}]

    def test_no_divergence_when_the_two_agree(self, board):
        block = _build(board)
        assert block["board_featured_count"] == 1
        assert block["featured_divergence"] == []

    def test_the_unknown_reason_bucket_is_reported_as_an_alarm(self, board):
        """M1b.  An uninstrumented drop site is a defect, and must not read as a lane."""
        healthy = _build(board)
        assert healthy["unknown_reason_count"] == 0
        assert healthy["unknown_reason_tickers"] == []
        broken = _build(board, off_board_reasons={})
        assert broken["unknown_reason_count"] == 5
        assert broken["unknown_reason_tickers"] == ["III", "JJJ", "KKK", "LLL", "MMM"]

    def test_the_builder_raises_a_line_start_annotation_for_unknown_reasons(self):
        """House law: a bare line-start print, never a logger.

        `build_stock_library`'s logger prefixes every record with its level, so
        `log.warning("::warning …")` emits "WARNING ::warning …" and GitHub drops it.
        Asserted on the SOURCE because the surrounding builder cannot be run here.
        """
        source = (REPO / "scripts" / "build_stock_library.py").read_text()
        for title in ("candidate-pool-unknown-reason",
                      "candidate-pool-undeclared-reason",
                      "candidate-pool-orphan-buy"):
            marker = f'::warning title={title}::'
            assert marker in source, title
            for line in source.splitlines():
                if marker in line:
                    assert line.lstrip().startswith(("print(", 'f"', '"')), line
                    assert "log." not in line, line
        # the dead guard it replaced must be gone
        assert "!= board eligible" not in source

    def test_pool_definition_and_era_are_stamped(self, board):
        block = _build(board)
        assert block["pool_definition"] == ucl.POOL_DEFINITION
        assert block["selection_era"] == "anticipation-v1-2026-08-08"
        assert all(r["selection_era"] == "anticipation-v1-2026-08-08"
                   for r in block["rows"])


# --------------------------------------------------------------------------- #
# 4b. the reason vocabulary — four declared sets, no undeclared word ships
# --------------------------------------------------------------------------- #

class TestReasonVocabulary:
    """M3.  `pool_headline_reason` ships to a PUBLIC parquet.

    Every value it can take must be declared somewhere a rename has to go past, or an
    upstream edit silently splits a cohort across two spellings of the same fact.  The
    fourth source — ``us_board_rank.featured_shortfalls`` plus the featured pass in
    ``score_rows`` — carried 41 of 144 headline reasons on the 2026-08-07 board while
    being in no declared set at all.
    """

    def test_every_reason_the_fixture_board_emits_is_declared(self, board):
        block = _build(board)
        undeclared = sorted({code for r in block["rows"] for code in r["lane_reasons"]
                             if not ucl.is_declared_reason(code)})
        assert undeclared == []
        assert block["undeclared_reasons"] == []

    def test_the_seven_codes_the_review_found_undeclared_are_now_declared(self):
        """The exact set the adversarial pass named."""
        for code in ("alpha_below_floor", "antichase_blocked", "extended",
                     "featured_cap", "stage_ran", "ticks_stale", "tier_unknown"):
            assert ucl.is_declared_reason(code), code

    def test_an_undeclared_word_is_reported_not_absorbed(self, board):
        board["buy"][1]["featured_blocked_by"] = ["freshly_renamed_upstream"]
        block = _build(board)
        assert block["undeclared_reasons"] == ["freshly_renamed_upstream"]

    def test_every_declared_literal_still_exists_upstream(self):
        """A rename in us_board_rank must RED here rather than drift silently."""
        import inspect

        from engine import us_board_rank as ubr

        source = inspect.getsource(ubr.featured_shortfalls) + inspect.getsource(
            ubr.score_rows)
        for code in ucl.FEATURED_SHORTFALL_CODES:
            assert f'"{code}"' in source, (
                f"{code} is declared here but no longer emitted by us_board_rank — "
                "drop it or follow the rename")

    def test_every_declared_prefix_still_exists_upstream(self):
        import inspect

        from engine import us_board_rank as ubr

        source = inspect.getsource(ubr.featured_shortfalls)
        for prefix in ucl.FEATURED_SHORTFALL_PREFIXES:
            assert f'f"{prefix}' in source, prefix

    def test_the_stage_family_is_bounded_by_the_boards_own_stage_enum(self):
        """A prefix match alone would wave a renamed stage through."""
        from engine import us_board_rank as ubr

        assert ucl.FEATURED_SHORTFALL_FAMILY_VALUES["stage"] == set(ubr.STAGE_ORDER)

    def test_the_entry_status_family_is_bounded_by_the_emitter_vocabularies(self):
        from engine import entry_signal
        from engine import us_board_rank as ubr

        expected = set(entry_signal._HEADLINE) | set(ubr._ENTRY_VALUE) | {"unknown"}
        assert ucl.FEATURED_SHORTFALL_FAMILY_VALUES["entry_status"] == expected

    def test_the_tier_family_is_bounded_by_the_cascade_enum(self):
        from engine import signal_gate

        assert ucl.FEATURED_SHORTFALL_FAMILY_VALUES["tier"] == (
            set(signal_gate._CASCADE_RANK) | {"unknown"}
        )

    @pytest.mark.parametrize(
        "code", ["stage_new_bucket", "tier_T5", "entry_status_renamed_upstream"],
    )
    def test_an_unknown_member_of_a_declared_family_is_still_undeclared(self, code):
        assert ucl.is_declared_reason(code) is False

    def test_the_refusal_family_is_exactly_prophet_bridges(self):
        from engine import prophet_bridge as pb

        assert set(pb.REFUSAL_ORDER) <= ucl.declared_reasons()

    def test_off_board_reasons_are_all_declared(self):
        assert set(ucl.OFF_BOARD_REASONS) <= ucl.declared_reasons()

    def test_earnings_blackout_and_event_blackout_are_different_facts(self):
        """Both are declared and must NOT be unified by a future tidy-up.

        ``earnings_blackout`` is a FEATURED veto stamped by us_board_rank on a row that
        is still on the board; ``event_blackout`` is the W1.5 gate REMOVING the name
        from buy[] entirely.  Same event, different consequence.
        """
        assert "earnings_blackout" in ucl.FEATURED_SHORTFALL_CODES
        assert "event_blackout" in ucl.OFF_BOARD_REASONS
        assert "earnings_blackout" not in ucl.OFF_BOARD_REASONS

    @pytest.mark.parametrize("code", ["", None, "  ", "totally_made_up"])
    def test_undeclared_input_is_rejected(self, code):
        assert ucl.is_declared_reason(code) is False


# --------------------------------------------------------------------------- #
# 5. the store — schema, projection, append-only semantics
# --------------------------------------------------------------------------- #

def _is_buyable(verdict):
    return bool(verdict.get("eligible")) and verdict.get("tier_cascade") in {
        "T1", "T2", "T3"}


@pytest.fixture
def store_kwargs(tmp_path):
    return {
        "board_definition": "us_prophet_v2",
        "is_buyable": _is_buyable,
        "root": tmp_path,
        "event_rows": {},
        "with_context_dims": False,
    }


@pytest.fixture
def verdicts():
    return {
        "AAA": {"eligible": True, "tier_cascade": "T2", "asof": "2026-08-07"},
        "III": {"eligible": True, "tier_cascade": "T3", "asof": "2026-08-07"},
        "ZZZ": {"eligible": False, "tier_cascade": None, "asof": "2026-08-07"},
    }


class TestStoreSchema:

    def test_producer_and_store_agree_on_the_column_list(self):
        """The store owns its schema; the producer may not widen it unilaterally."""
        assert tuple(ucl.STORE_COLUMNS) == tuple(ucv.POOL_COLUMNS)

    def test_originated_is_deliberately_absent(self):
        """Carried-columns law: never ship a column that can never be populated."""
        assert "originated" not in ucv.POOL_COLUMNS
        assert "pool_originated" not in ucv.POOL_COLUMNS
        assert "pool_open_plan" in ucv.POOL_COLUMNS

    def test_store_columns_projection(self, board):
        block = _build(board)
        cols = ucl.store_columns(block, open_tickers=["CCC"])
        assert set(cols) == set(board["eligible_order"])
        assert set(cols["AAA"]) == set(ucv.POOL_COLUMNS)
        assert cols["AAA"]["pool_lane"] == ucl.LANE_FEATURED
        assert cols["AAA"]["pool_in_buy_lane"] is True
        assert cols["AAA"]["pool_open_plan"] is False
        assert cols["CCC"]["pool_open_plan"] is True
        assert cols["III"]["pool_in_buy_lane"] is False
        assert cols["III"]["pool_headline_reason"] == "sector_cap_overflow"

    def test_reason_join_preserves_order(self):
        """Headline first — ``_ids`` sorts, which would silently re-headline a row."""
        assert ucl.join_reasons(["z_last", "a_first"]) == "z_last|a_first"
        assert ucl.join_reasons([]) is None

    def test_columns_land_on_the_store_and_are_null_off_the_pool(
        self, board, verdicts, store_kwargs, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        cols = ucl.store_columns(_build(board))
        assert ucv.append_candidates(verdicts, "2026-08-07",
                                     pool_columns=cols, **store_kwargs) == 3
        frame = ucv.load_candidates(tmp_path).set_index("ticker")
        for column in ucv.POOL_COLUMNS:
            assert column in frame.columns
        assert frame.loc["AAA", "pool_lane"] == ucl.LANE_FEATURED
        assert frame.loc["III", "pool_headline_reason"] == "sector_cap_overflow"
        # ZZZ is in the universe but not in the pool: NULL, and specifically never
        # "false"/0 — a name outside tonight's pool was not measured, not refused
        # (#4485).  `isna` rather than `is None` because the store's own coercion
        # normalises object nulls to NaN on the way to parquet.
        for column in ucv.POOL_COLUMNS:
            value = frame.loc["ZZZ", column]
            assert pd.isna(value), (column, value)
            assert value is not False and value != 0

    def test_pool_lane_never_overwrites_the_artifact_lane_column(
        self, board, verdicts, store_kwargs, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        ucv.append_candidates(verdicts, "2026-08-07",
                              pool_columns=ucl.store_columns(_build(board)),
                              lane_by_ticker={"AAA": "buy"}, **store_kwargs)
        frame = ucv.load_candidates(tmp_path).set_index("ticker")
        assert frame.loc["AAA", "lane"] == "buy"
        assert frame.loc["AAA", "pool_lane"] == ucl.LANE_FEATURED

    def test_an_unknown_column_from_a_caller_is_dropped(
        self, verdicts, store_kwargs, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        ucv.append_candidates(
            verdicts, "2026-08-07",
            pool_columns={"AAA": {"pool_lane": "featured", "pool_smuggled": 1}},
            **store_kwargs)
        frame = ucv.load_candidates(tmp_path)
        assert "pool_smuggled" not in frame.columns

    def test_append_is_keep_first_on_a_rerun(
        self, board, verdicts, store_kwargs, tmp_path, monkeypatch
    ):
        """A re-run cannot rewrite a night already stamped, pool columns included."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        ucv.append_candidates(verdicts, "2026-08-07",
                              pool_columns=ucl.store_columns(_build(board)),
                              **store_kwargs)
        rewritten = dict(ucl.store_columns(_build(board)))
        rewritten["AAA"] = {**rewritten["AAA"], "pool_lane": ucl.LANE_FORMING}
        ucv.append_candidates(verdicts, "2026-08-07",
                              pool_columns=rewritten, **store_kwargs)
        frame = ucv.load_candidates(tmp_path)
        assert len(frame) == 3
        assert frame.set_index("ticker").loc["AAA", "pool_lane"] == ucl.LANE_FEATURED

    def test_a_night_stamped_before_the_columns_existed_reads_null(
        self, board, verdicts, store_kwargs, tmp_path, monkeypatch
    ):
        """Forward-only self-healing: no retroactive backfill of an earlier night."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        ucv.append_candidates(verdicts, "2026-08-06", **store_kwargs)
        ucv.append_candidates(verdicts, "2026-08-07",
                              pool_columns=ucl.store_columns(_build(board)),
                              **store_kwargs)
        frame = ucv.load_candidates(tmp_path)
        old = frame[frame["stamp_date"] == "2026-08-06"].set_index("ticker")
        new = frame[frame["stamp_date"] == "2026-08-07"].set_index("ticker")
        assert pd.isna(old.loc["AAA", "pool_lane"])
        assert new.loc["AAA", "pool_lane"] == ucl.LANE_FEATURED


# --------------------------------------------------------------------------- #
# 6. graduation — derived from a real 3-night store, never from memory
# --------------------------------------------------------------------------- #

@pytest.fixture
def three_night_store(board, verdicts, store_kwargs, tmp_path, monkeypatch):
    """AAA graduates forming -> more_actionable -> featured while its score climbs."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    script = [
        ("2026-08-03", ucl.LANE_FORMING, 40.0),
        ("2026-08-04", ucl.LANE_FORMING, 48.0),
        ("2026-08-05", ucl.LANE_MORE_ACTIONABLE, 55.0),
        ("2026-08-06", ucl.LANE_MORE_ACTIONABLE, 62.0),
        ("2026-08-07", ucl.LANE_MORE_ACTIONABLE, 66.0),
    ]
    for stamp, lane, score in script:
        rows = [_buy_row("AAA", score=score)]
        block = ucl.build_candidate_pool(
            as_of=stamp, board_definition="us_prophet_v2", selection_era="era-1",
            eligible_order=["AAA", "III"], buy_rows=rows,
            off_board_reasons={"III": ["sector_cap_overflow"]},
        )
        pool = ucl.store_columns(block)
        pool["AAA"] = {**pool["AAA"], "pool_lane": lane}
        ucv.append_candidates(
            {"AAA": {"eligible": True, "tier_cascade": "T2", "asof": stamp},
             "III": {"eligible": True, "tier_cascade": "T3", "asof": stamp}},
            stamp,
            board_rows={"AAA": rows[0]},
            pool_columns=pool, **store_kwargs)
    return tmp_path


class TestGraduationFields:

    def test_history_loads_only_prior_nights(self, three_night_store):
        history, meta = ucl.load_pool_history("2026-08-08", root=three_night_store)
        assert meta["available"] is True
        assert meta["nights"] == 5
        assert [r["stamp_date"] for r in history["AAA"]] == [
            "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]

    def test_tonights_own_row_can_never_become_its_own_history(self, three_night_store):
        history, _ = ucl.load_pool_history("2026-08-07", root=three_night_store)
        assert [r["stamp_date"] for r in history["AAA"]] == [
            "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]

    def test_days_in_pool_counts_prior_nights_plus_tonight(self, three_night_store):
        history, _ = ucl.load_pool_history("2026-08-08", root=three_night_store)
        fields = ucl.graduation_fields(
            history, tonight_lane_by_ticker={"AAA": ucl.LANE_FEATURED})
        assert fields["AAA"]["days_in_pool"] == 6

    def test_lane_transitions_and_prev_lane(self, three_night_store):
        history, _ = ucl.load_pool_history("2026-08-08", root=three_night_store)
        fields = ucl.graduation_fields(
            history, tonight_lane_by_ticker={"AAA": ucl.LANE_FEATURED})
        # forming -> more_actionable -> featured
        assert fields["AAA"]["lane_transitions"] == 2
        assert fields["AAA"]["prev_lane"] == ucl.LANE_MORE_ACTIONABLE
        assert fields["AAA"]["first_seen"] == "2026-08-03"

    def test_score_delta_is_measured_against_the_fifth_prior_stamp(
        self, three_night_store
    ):
        history, _ = ucl.load_pool_history("2026-08-08", root=three_night_store)
        fields = ucl.graduation_fields(
            history,
            tonight_lane_by_ticker={"AAA": ucl.LANE_FEATURED},
            tonight_score_by_ticker={"AAA": 74.0})
        assert fields["AAA"]["score_delta_5d"] == pytest.approx(34.0)  # 74.0 - 40.0
        assert ucl.SCORE_DELTA_BASIS == "5_prior_stamps"

    def test_score_delta_is_null_without_five_prior_stamps(self, three_night_store):
        history, _ = ucl.load_pool_history("2026-08-06", root=three_night_store)
        fields = ucl.graduation_fields(
            history,
            tonight_lane_by_ticker={"AAA": ucl.LANE_MORE_ACTIONABLE},
            tonight_score_by_ticker={"AAA": 62.0})
        assert fields["AAA"]["score_delta_5d"] is None

    def test_an_off_board_name_has_lane_history_but_no_score_delta(
        self, three_night_store
    ):
        history, _ = ucl.load_pool_history("2026-08-08", root=three_night_store)
        fields = ucl.graduation_fields(
            history,
            tonight_lane_by_ticker={"III": ucl.LANE_MORE_ACTIONABLE},
            tonight_score_by_ticker={"III": None})
        assert fields["III"]["days_in_pool"] == 6
        assert fields["III"]["score_delta_5d"] is None

    def test_a_name_new_to_the_pool_reads_night_one(self, three_night_store):
        history, meta = ucl.load_pool_history("2026-08-08", root=three_night_store)
        fields = ucl.graduation_fields(
            history, tonight_lane_by_ticker={"NEW": ucl.LANE_FORMING},
            window_meta=meta)
        assert fields["NEW"]["days_in_pool"] == 1
        assert fields["NEW"]["score_delta_5d"] is None
        assert fields["NEW"]["lane_transitions"] == 0
        assert fields["NEW"]["prev_lane"] is None
        assert fields["NEW"]["first_seen"] is None
        # a name with no history cannot be window-truncated
        assert fields["NEW"]["window_truncated"] is False

    def test_days_in_pool_discloses_when_it_is_only_a_floor(self, three_night_store):
        """m6.  A name whose history starts AT the window edge may be much older.

        Without this, a four-month resident and a genuine 5-night arrival both read
        "5 nights" with the same confidence.
        """
        history, meta = ucl.load_pool_history("2026-08-08", root=three_night_store)
        fields = ucl.graduation_fields(
            history, tonight_lane_by_ticker={"AAA": ucl.LANE_FEATURED},
            window_meta=meta)
        assert meta["oldest_stamp"] == "2026-08-03"
        assert meta["months_back"] == 1
        assert fields["AAA"]["first_seen"] == "2026-08-03"
        assert fields["AAA"]["window_truncated"] is True
        assert fields["AAA"]["window_oldest"] == "2026-08-03"
        assert fields["AAA"]["window_months_back"] == 1

    def test_a_name_that_arrived_inside_the_window_is_not_truncated(
        self, three_night_store
    ):
        history, meta = ucl.load_pool_history("2026-08-08", root=three_night_store)
        history = {"AAA": [r for r in history["AAA"] if r["stamp_date"] > "2026-08-03"]}
        fields = ucl.graduation_fields(
            history, tonight_lane_by_ticker={"AAA": ucl.LANE_FEATURED},
            window_meta=meta)
        assert fields["AAA"]["window_truncated"] is False

    def test_an_empty_store_is_an_available_read_with_no_nights(self, tmp_path):
        """"No prior nights" is a successful read, not an unavailable one."""
        history, meta = ucl.load_pool_history("2026-08-08", root=tmp_path)
        assert history == {}
        assert meta == {"available": True, "nights": 0,
                        "months": ["2026-07", "2026-08"]}

    def test_an_undated_call_reads_nothing(self):
        history, meta = ucl.load_pool_history(None)
        assert history == {}
        assert meta["available"] is False

    def test_graduation_is_attached_only_when_history_exists(self, board):
        without = _build(board)
        assert all("graduation" not in r for r in without["rows"])
        assert without["history"]["available"] is False
        with_hist = _build(
            board,
            history={"AAA": {"days_in_pool": 4, "score_delta_5d": 3.0,
                             "lane_transitions": 1, "prev_lane": "forming",
                             "first_seen": "2026-08-03"}},
            history_meta={"available": True, "nights": 3, "months": ["2026-08"]})
        aaa = next(r for r in with_hist["rows"] if r["ticker"] == "AAA")
        assert aaa["graduation"]["days_in_pool"] == 4
        assert with_hist["history"]["available"] is True
        assert with_hist["history"]["score_delta_basis"] == ucl.SCORE_DELTA_BASIS

    def test_a_store_with_no_pool_columns_yields_no_history(
        self, verdicts, store_kwargs, tmp_path, monkeypatch
    ):
        """The NaN trap, pinned.

        ``load_candidates(columns=...)`` falls back to a full read reindexed onto the
        requested columns when a part predates one — which materialises the absent
        column as float NaN.  Before ``_text`` was NaN-aware, every ticker read back a
        lane of ``"nan"``: measured on the real committed store, 4,474 tickers with four
        nights of "history" on a store that has never carried a pool lane.
        """
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        ucv.append_candidates(verdicts, "2026-08-06", **store_kwargs)
        ucv.append_candidates(verdicts, "2026-08-07", **store_kwargs)
        history, meta = ucl.load_pool_history("2026-08-08", root=tmp_path)
        assert history == {}
        assert meta["available"] is True
        assert meta["nights"] == 0

    @pytest.mark.parametrize("value", [float("nan"), None, "", "  ", "nan", "NaN",
                                       "None", "NaT", "<NA>"])
    def test_text_reads_every_null_shape_as_none(self, value):
        assert ucl._text(value) is None

    def test_history_read_is_fail_soft(self, monkeypatch):
        def _boom(*a, **kw):
            raise RuntimeError("store unreadable")

        monkeypatch.setattr(ucv, "load_candidates", _boom)
        history, meta = ucl.load_pool_history("2026-08-08")
        assert history == {}
        assert meta["available"] is False


# --------------------------------------------------------------------------- #
# 7. NO AUTHORITY LEAK
# --------------------------------------------------------------------------- #

#: The ONLY modules allowed to name the candidate pool.  The producer, the builder that
#: calls it, the store that carries its columns, and the schema exporter that merely
#: registers the already-public disclosure.  Everything else — and in
#: particular anything that decides membership, order, size or a gate — must not.
POOL_ALLOWLIST = frozenset({
    "engine/us_candidate_lanes.py",
    "engine/us_context_vector.py",
    "scripts/build_stock_library.py",
    "scripts/export_signal_contracts.py",
})

#: Modules that DECIDE things.  If any of them ever learns the pool exists, the fence is
#: gone: a display tier built because it has no say would start having one.
AUTHORITY_MODULES = (
    "engine/prophet_bridge.py",
    "engine/us_board_rank.py",
    "engine/signal_gate.py",
    "engine/confluence_tiers.py",
    "engine/us_leader_pullback.py",
)

#: Every token that would mean a module is reading this feature.  This must stay a
#: SUPERSET of the store's column names — a reader that touches only
#: ``pool_admission_class`` or ``pool_open_plan`` is reading the pool just as surely as
#: one that names the module (review n16).  ``test_the_fence_covers_every_store_column``
#: pins that so a tenth column cannot land outside the fence.
POOL_TOKENS = frozenset({
    "us_candidate_lanes", "candidate_pool", "us_candidate_pool_v1", "POOL_COLUMNS",
    *ucv.POOL_COLUMNS,
})

#: PRE-EXISTING, UNRELATED uses of two of those words, each named with its reason.  A
#: guard that reds on somebody else's vocabulary is a guard that gets deleted, and
#: silently dropping the colliding tokens from the sweep would blind it everywhere.  The
#: exemption is per (module, token) and fails closed for anything new.
TOKEN_COLLISION_EXEMPT = {
    # LLM OAuth key pools — a `"pool_lane"` desk-config key, nothing to do with the
    # board.  (`engine/llm_auth.py` names it only in comments, so it needs no exemption.)
    "admin/marketing_floor.py": {"pool_lane"},
    # a per-desk shortlist size, and a top-anatomy DataFrame parameter
    "engine/press/desk_planner.py": {"candidate_pool"},
    "engine/top_anatomy.py": {"candidate_pool"},
}

MODULE_TREES = ("engine", "scripts", "app", "admin", "lib", "collectors")


def _code_tokens(path: Path) -> set[str]:
    """Identifiers, attribute names, imports and string literals — prose EXCLUDED.

    Comments and docstrings are stripped, because the fence is about what a module DOES,
    not what it says.  ``prophet_bridge.refusal_codes`` names this module in its
    docstring on purpose (that provenance is the point of the alias) and must not read as
    a dependency.  Everything else — including a real ``doc["candidate_pool"]`` key read,
    which is a plain string literal — is kept.
    """
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except SyntaxError:                                  # pragma: no cover
        return set()
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                tokens.add(node.value)
        elif isinstance(node, ast.Name):
            tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr)
        elif isinstance(node, ast.alias):
            tokens.update(node.name.split("."))
            if node.asname:
                tokens.add(node.asname)
        elif isinstance(node, ast.ImportFrom) and node.module:
            tokens.update(node.module.split("."))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            tokens.add(node.name)
        elif isinstance(node, ast.arg):
            tokens.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            tokens.add(node.arg)
    return tokens


class TestNoAuthorityLeak:

    def test_only_the_allowlisted_modules_name_the_pool(self):
        offenders: dict[str, list[str]] = {}
        for tree in MODULE_TREES:
            for path in sorted((REPO / tree).rglob("*.py")):
                rel = path.relative_to(REPO).as_posix()
                if rel in POOL_ALLOWLIST:
                    continue
                hits = sorted((_code_tokens(path) & POOL_TOKENS)
                              - TOKEN_COLLISION_EXEMPT.get(rel, frozenset()))
                if hits:
                    offenders[rel] = hits
        assert not offenders, (
            "candidate-pool tokens reached a non-allowlisted module — if this is a new "
            "READER, add it to POOL_ALLOWLIST only after confirming it decides nothing: "
            f"{offenders}")

    def test_the_fence_covers_every_store_column(self):
        """A new pool column must not land outside the sweep (review n16)."""
        assert set(ucv.POOL_COLUMNS) <= POOL_TOKENS
        assert set(ucl.STORE_COLUMNS) <= POOL_TOKENS

    def test_every_collision_exemption_is_still_real(self):
        """A stale exemption is a hole.  Each one must still be earned."""
        for rel, tokens in TOKEN_COLLISION_EXEMPT.items():
            present = _code_tokens(REPO / rel)
            assert tokens <= present, (
                f"{rel} no longer uses {sorted(tokens - present)} — drop the exemption")

    def test_the_sweep_can_actually_see_a_leak(self, tmp_path):
        """The guard's own witness: a planted reader must be detected.

        Without this, the sweep above passes just as happily when ``_code_tokens``
        silently returns nothing.
        """
        planted = tmp_path / "leaky.py"
        planted.write_text(
            '"""Docstring naming us_candidate_lanes must NOT count."""\n'
            "# a comment naming pool_lane must NOT count\n"
            "def f(doc):\n"
            "    return doc['candidate_pool']['rows'][0]['pool_lane']\n"
        )
        assert _code_tokens(planted) & POOL_TOKENS == {"pool_lane", "candidate_pool"}
        clean = tmp_path / "prose_only.py"
        clean.write_text('"""Mentions us_candidate_lanes and pool_lane in prose."""\n'
                         "# and in a comment: candidate_pool\n"
                         "X = 1\n")
        assert not _code_tokens(clean) & POOL_TOKENS

    @pytest.mark.parametrize("module", AUTHORITY_MODULES)
    def test_no_authority_module_reads_the_pool(self, module):
        hits = sorted(_code_tokens(REPO / module) & POOL_TOKENS)
        assert not hits, f"{module} reads the candidate pool: {hits}"

    @pytest.mark.parametrize("module", AUTHORITY_MODULES)
    def test_the_pool_is_not_in_any_authority_import_closure(self, module):
        """Walk imports transitively — a two-hop leak is still a leak."""
        seen: set[str] = set()
        stack = [module]
        while stack:
            rel = stack.pop()
            if rel in seen:
                continue
            seen.add(rel)
            path = REPO / rel
            if not path.exists():
                continue
            try:
                tree = ast.parse(path.read_text(errors="ignore"))
            except SyntaxError:                          # pragma: no cover
                continue
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module] + [f"{node.module}.{a.name}"
                                             for a in node.names]
                for name in names:
                    assert not name.endswith("us_candidate_lanes"), (
                        f"{rel} reaches engine.us_candidate_lanes")
                    candidate = REPO / (name.replace(".", "/") + ".py")
                    if candidate.exists() and name.split(".")[0] in MODULE_TREES:
                        stack.append(candidate.relative_to(REPO).as_posix())

    @pytest.mark.parametrize("func", ["select_candidates", "originate_plans",
                                      "refusal_receipts", "admission_class"])
    def test_admission_call_sites_carry_no_pool_reference(self, func):
        import inspect

        from engine import prophet_bridge as pb

        target = getattr(pb, func, None)
        if target is None:                               # pragma: no cover
            pytest.skip(f"prophet_bridge.{func} not present")
        source = inspect.getsource(target)
        assert not [t for t in POOL_TOKENS if t in source], func

    def test_score_rows_carries_no_pool_reference(self):
        import inspect

        from engine import us_board_rank as ubr

        assert not [t for t in POOL_TOKENS if t in inspect.getsource(ubr.score_rows)]

    def test_admission_is_byte_identical_with_and_without_the_block(self, board):
        """The behavioural half: the block may not change who gets picked, ever."""
        from engine import prophet_bridge as pb

        doc = {"buy": copy.deepcopy(board["buy"]), "gate_go": True}
        baseline = pb.select_candidates(copy.deepcopy(doc), n=None)
        doc_with_pool = copy.deepcopy(doc)
        doc_with_pool["candidate_pool"] = _build(board)
        after = pb.select_candidates(doc_with_pool, n=None)
        assert [r.get("ticker") for r in baseline] == [r.get("ticker") for r in after]
        assert json.dumps(baseline, sort_keys=True, default=str) == \
            json.dumps(after, sort_keys=True, default=str)

    def test_refusal_receipts_are_unchanged_by_the_block(self, board):
        from engine import prophet_bridge as pb

        doc = {"buy": copy.deepcopy(board["buy"])}
        baseline = pb.refusal_receipts(doc)
        doc_with_pool = {**doc, "candidate_pool": _build(board)}
        assert pb.refusal_receipts(doc_with_pool) == baseline

    def test_public_refusal_codes_is_the_private_helper(self, board):
        """One vocabulary: the pool must not fork the gate's reason list."""
        from engine import prophet_bridge as pb

        for row in board["buy"]:
            assert pb.refusal_codes(row) == pb._refusal_codes(row)
