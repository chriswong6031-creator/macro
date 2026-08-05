"""Tests for engine/us_context_vector.py — the US Context Vector PIT store.

Three things are pinned here, in order of how badly a regression would hurt:

1. NIGHTLY IS THE SOLE ADVANCER.  The store must not advance from an intraday
   or render lane.  ``TestNightlyLaneGate`` pops COLLECT_LANE/US_LANE (the
   repo-wide conftest arms COLLECT_LANE=nightly for every test, so a gate test
   MUST remove it explicitly) and asserts no file is created at all.
2. PIT discipline — keep-first on rerun, schema union on append, no
   retroactive backfill of an already-stamped night.
3. The schema contract — column names and dtypes, so a downstream join written
   against tonight's store still parses next month.

Hermetic by construction: every test passes ``root=tmp_path`` and
``event_rows={}``/``with_context_dims=False``, so no test reads the repo's real
``data/`` tree, hits the network, or writes outside tmp_path (MM_DATA_GUARD).
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine import us_context_vector as ucv


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _verdict(eligible=True, tier="T2", ticks=1, **extra):
    verdict = {
        "eligible": eligible,
        "tier_cascade": tier,
        "tier_sub": "just_crossed",
        "ticks": ticks,
        "bars_to_cross": None,
        "fresh_bars": 3,
        "weight": 0.8,
        "state": "crossed",
        "reason": "macd+stoch confluence",
        "provisional": False,
        "htf_s1": True,
        "htf_s2": False,
        "asof": "2026-07-31",
    }
    verdict.update(extra)
    return verdict


def _is_buyable(verdict):
    return bool(verdict.get("eligible")) and verdict.get("tier_cascade") in {
        "T1", "T2", "T3"}


@pytest.fixture
def verdicts():
    """Full universe: two board-eligible names and one ineligible name."""
    return {
        "AAA": _verdict(),
        "BBB": _verdict(eligible=False, tier=None, ticks=7,
                        near_miss_reason="not_topped_veto"),
        "CCC": _verdict(tier="T3", ticks=0),
    }


@pytest.fixture
def append_kwargs(tmp_path):
    """Hermetic kwargs: nothing reads the real repo, nothing calls context_api."""
    return {
        "board_definition": "us_prophet_v1",
        "is_buyable": _is_buyable,
        "root": tmp_path,
        "event_rows": {},
        "with_context_dims": False,
    }


# --------------------------------------------------------------------------- #
# 1. nightly-is-the-sole-advancer
# --------------------------------------------------------------------------- #

class TestNightlyLaneGate:
    """The store must be unable to advance outside the US nightly lane."""

    @pytest.mark.parametrize("lane", [None, "intraday", "render", "weekly", "asia"])
    def test_non_nightly_lane_writes_nothing(
        self, lane, verdicts, append_kwargs, tmp_path, monkeypatch
    ):
        # conftest arms COLLECT_LANE=nightly for every test — remove it, or this
        # test passes for the wrong reason.
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        if lane is not None:
            monkeypatch.setenv("COLLECT_LANE", lane)

        assert ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs) == 0
        assert not ucv._part_path("2026-07-31", tmp_path).exists()

    def test_nightly_lane_writes(self, verdicts, append_kwargs, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        assert ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs) == 3
        assert ucv._part_path("2026-07-31", tmp_path).exists()

    def test_legacy_us_lane_alias_writes(
        self, verdicts, append_kwargs, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.setenv("US_LANE", "nightly")
        assert ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs) == 3

    def test_gate_precedes_any_assembly(
        self, verdicts, append_kwargs, monkeypatch
    ):
        """A blocked lane must not pay the ~8-minute assembly cost.

        If the gate ever moves below the assembly, these fakes raise and the
        test reds — that is the whole point of asserting on the ORDER rather
        than only on the return value.
        """
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)

        def _boom(*a, **kw):
            raise AssertionError("assembly ran in a non-nightly lane")

        monkeypatch.setattr(ucv, "build_records", _boom)
        monkeypatch.setattr(ucv, "basket_membership", _boom)
        monkeypatch.setattr(ucv, "context_dimension_frame", _boom)
        assert ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs) == 0


# --------------------------------------------------------------------------- #
# 2. PIT discipline
# --------------------------------------------------------------------------- #

class TestPitDiscipline:

    def test_full_universe_includes_ineligible_names(
        self, verdicts, append_kwargs, tmp_path
    ):
        ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs)
        frame = ucv.load_candidates(tmp_path)
        assert set(frame["ticker"]) == {"AAA", "BBB", "CCC"}
        # the ineligible name is present, and is marked so
        row = frame.set_index("ticker").loc["BBB"]
        assert bool(row["eligible"]) is False
        assert bool(row["buyable"]) is False
        assert row["lane"] == "not_on_board"

    def test_rerun_keeps_first_and_does_not_rewrite(
        self, verdicts, append_kwargs, tmp_path
    ):
        ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs)
        # a rerun with a MUTATED verdict must not overwrite the stamped night
        mutated = dict(verdicts)
        mutated["AAA"] = _verdict(tier="T1", ticks=99)
        total = ucv.append_candidates(mutated, "2026-07-31", **append_kwargs)
        assert total == 3
        frame = ucv.load_candidates(tmp_path)
        assert frame.set_index("ticker").loc["AAA"]["ticks"] == 1
        assert frame.set_index("ticker").loc["AAA"]["tier_cascade"] == "T2"

    def test_second_night_appends_without_touching_the_first(
        self, verdicts, append_kwargs, tmp_path
    ):
        ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs)
        # the return is the MONTH PART's row count, and August is a new part
        assert ucv.append_candidates(verdicts, "2026-08-03", **append_kwargs) == 3
        frame = ucv.load_candidates(tmp_path)
        assert len(frame) == 6
        assert sorted(frame["stamp_date"].unique()) == ["2026-07-31", "2026-08-03"]
        assert len(frame[frame["stamp_date"] == "2026-07-31"]) == 3

    def test_same_month_nights_share_one_part(
        self, verdicts, append_kwargs, tmp_path
    ):
        ucv.append_candidates(verdicts, "2026-08-03", **append_kwargs)
        assert ucv.append_candidates(verdicts, "2026-08-04", **append_kwargs) == 6
        parts = sorted(p.name for p in ucv._store_dir(tmp_path).glob("*.parquet"))
        assert parts == ["2026-08.parquet"]

    def test_schema_union_preserves_a_retired_column(
        self, verdicts, append_kwargs, tmp_path
    ):
        """A column present on an older night survives a night that lacks it."""
        ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs)
        path = ucv._part_path("2026-07-31", tmp_path)
        prior = pd.read_parquet(path)
        prior["legacy_only_column"] = "kept"
        prior.to_parquet(path, index=False)

        ucv.append_candidates(verdicts, "2026-08-03", **append_kwargs)
        frame = pd.read_parquet(path)
        assert "legacy_only_column" in frame.columns
        old = frame[frame["stamp_date"] == "2026-07-31"]["legacy_only_column"]
        new = frame[frame["stamp_date"] == "2026-08-03"]["legacy_only_column"]
        assert set(old) == {"kept"}
        assert new.isna().all()          # self-heals forward, never backwards

    def test_board_definition_change_starts_a_fresh_series(
        self, verdicts, append_kwargs, tmp_path
    ):
        ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs)
        kwargs = {**append_kwargs, "board_definition": "us_prophet_v2"}
        total = ucv.append_candidates(verdicts, "2026-07-31", **kwargs)
        assert total == 6      # same night, both definitions, neither shadowed

    def test_empty_or_undated_input_writes_nothing(self, append_kwargs, tmp_path):
        assert ucv.append_candidates({}, "2026-07-31", **append_kwargs) == 0
        assert ucv.append_candidates({"AAA": _verdict()}, None, **append_kwargs) == 0
        assert not ucv._part_path("2026-07-31", tmp_path).exists()


# --------------------------------------------------------------------------- #
# 2b. monthly-partitioned layout
# --------------------------------------------------------------------------- #

class TestMonthlyPartitionedLayout:
    """The layout exists to stop the store rewriting its whole history nightly.

    That claim holds only if a stamp provably leaves earlier parts alone, and it
    is only safe if no consumer has to know parts exist.  Both are pinned here.
    """

    def test_a_stamp_leaves_every_earlier_part_byte_identical(
        self, verdicts, append_kwargs, tmp_path
    ):
        import hashlib

        for stamp in ("2026-06-30", "2026-07-31"):
            ucv.append_candidates(verdicts, stamp, **append_kwargs)

        def digests():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(ucv._store_dir(tmp_path).glob("*.parquet"))}

        before = digests()
        assert set(before) == {"2026-06.parquet", "2026-07.parquet"}

        # a night in a NEW month must not rewrite a single earlier byte
        ucv.append_candidates(verdicts, "2026-08-03", **append_kwargs)
        after = digests()
        assert set(after) == {"2026-06.parquet", "2026-07.parquet",
                              "2026-08.parquet"}
        for part in ("2026-06.parquet", "2026-07.parquet"):
            assert after[part] == before[part], (
                f"{part} was rewritten by a later month's stamp — the whole "
                "point of the partitioned layout is that it is not")

        # and a second night INSIDE the current month rewrites only that part
        before2 = digests()
        ucv.append_candidates(verdicts, "2026-08-04", **append_kwargs)
        after2 = digests()
        for part in ("2026-06.parquet", "2026-07.parquet"):
            assert after2[part] == before2[part]
        assert after2["2026-08.parquet"] != before2["2026-08.parquet"]

    def test_reader_equivalence_across_parts(
        self, verdicts, append_kwargs, tmp_path
    ):
        """load_candidates() must return what one accreting file would have.

        Built by concatenating the parts by hand in chronological order and
        comparing frames — if the reader ever reorders, drops, or duplicates a
        row, this reds.
        """
        for stamp in ("2026-07-30", "2026-07-31", "2026-08-03"):
            ucv.append_candidates(verdicts, stamp, **append_kwargs)

        parts = sorted(ucv._store_dir(tmp_path).glob("*.parquet"))
        assert [p.name for p in parts] == ["2026-07.parquet", "2026-08.parquet"]

        expected = pd.concat([pd.read_parquet(p) for p in parts],
                             ignore_index=True)
        actual = ucv.load_candidates(tmp_path)
        pd.testing.assert_frame_equal(actual, expected)
        assert len(actual) == 9
        assert list(actual["stamp_date"]) == (
            ["2026-07-30"] * 3 + ["2026-07-31"] * 3 + ["2026-08-03"] * 3)

    def test_months_filter_reads_only_what_was_asked_for(
        self, verdicts, append_kwargs, tmp_path
    ):
        for stamp in ("2026-07-31", "2026-08-03"):
            ucv.append_candidates(verdicts, stamp, **append_kwargs)
        only_aug = ucv.load_candidates(tmp_path, months=["2026-08"])
        assert set(only_aug["stamp_date"]) == {"2026-08-03"}
        assert len(only_aug) == 3

    def test_a_column_added_in_a_later_month_is_null_for_earlier_months(
        self, verdicts, append_kwargs, tmp_path
    ):
        """Schema union has to survive ACROSS parts, not just within one."""
        ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs)
        ucv.append_candidates(verdicts, "2026-08-03", **append_kwargs)

        aug = ucv._part_path("2026-08-03", tmp_path)
        frame = pd.read_parquet(aug)
        frame["new_axis_v2"] = 1.0
        frame.to_parquet(aug, index=False)

        merged = ucv.load_candidates(tmp_path)
        assert "new_axis_v2" in merged.columns
        assert merged[merged["stamp_date"] == "2026-08-03"]["new_axis_v2"].notna().all()
        assert merged[merged["stamp_date"] == "2026-07-31"]["new_axis_v2"].isna().all()

    def test_reader_is_empty_and_safe_before_the_first_stamp(self, tmp_path):
        assert ucv.load_candidates(tmp_path).empty

    def test_one_unreadable_part_does_not_blind_the_rest(
        self, verdicts, append_kwargs, tmp_path
    ):
        for stamp in ("2026-07-31", "2026-08-03"):
            ucv.append_candidates(verdicts, stamp, **append_kwargs)
        ucv._part_path("2026-07-31", tmp_path).write_bytes(b"not a parquet")
        surviving = ucv.load_candidates(tmp_path)
        assert set(surviving["stamp_date"]) == {"2026-08-03"}


# --------------------------------------------------------------------------- #
# 3. schema contract
# --------------------------------------------------------------------------- #

#: Columns every night must carry, with the pandas dtype kind they must parse
#: as.  "O" = object/string (nullable), "f" = float, "b"/"O" = bool-or-null.
CONTRACT: dict[str, str] = {
    "stamp_date": "O", "ticker": "O", "name": "O", "sector": "O",
    "board_definition": "O", "lane": "O",
    "eligible": "b", "buyable": "b",
    "tier_cascade": "O", "tier_sub": "O", "gate_state": "O", "gate_reason": "O",
    "near_miss_reason": "O", "signal_asof": "O", "stage": "O",
    "ticks": "f", "bars_to_cross": "f", "fresh_bars": "f", "gate_weight": "f",
    "alpha": "f", "alpha_percentile": "f", "prophet_score": "f",
    "score_rank": "f", "display_rank": "f",
    "theme_membership_count": "i", "theme_membership_ids": "O",
    "theme_primary_id": "O", "theme_primary_name": "O", "theme_label": "O",
    "theme_reco": "O", "theme_score": "f", "theme_bull_days": "f",
    "theme_heat_rank": "f", "foresight_stage": "O",
    "relay_count_3d": "f", "relay_position": "f", "relay_members_covered": "f",
    "days_to_report": "f", "post_earnings_move_pct": "f",
    "eightk_recent_days": "f",
    "turnover_pctile_20d": "f", "turnover_window_20d": "f",
    "turnover_pctile_60d": "f",
    "ext_z": "f",
    "regime_dispersion_state": "O", "regime_market_quad": "O",
    "regime_quad_name": "O", "regime_vol_regime": "O",
    "context_dims": "O",
}

#: Tri-state columns: a real bool or None, NEVER coerced to False (#4485).
NULLABLE_BOOL_COLUMNS = (
    "featured", "reports_within_7", "earnings_stale",
    "in_blackout", "antichase_shadow_blocked", "regime_gate_go",
    "theme_clean_entry",
)


class TestSchemaContract:

    def test_every_contract_column_is_present(
        self, verdicts, append_kwargs, tmp_path
    ):
        ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs)
        frame = ucv.load_candidates(tmp_path)
        missing = sorted(set(CONTRACT) - set(frame.columns))
        assert not missing, f"schema contract lost columns: {missing}"

    def test_contract_dtypes_parse(self, verdicts, append_kwargs, tmp_path):
        ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs)
        frame = ucv.load_candidates(tmp_path)
        wrong = {}
        for column, kind in CONTRACT.items():
            actual = frame[column].dtype
            if kind == "O":
                ok = actual == object or isinstance(actual, pd.StringDtype)
            elif kind == "f":
                ok = actual.kind in "fiu" or actual == object
            elif kind == "i":
                # nullable int: object is legitimate when the source was absent
                ok = actual.kind in "iuf" or actual == object
            else:  # bool
                ok = actual.kind == "b" or actual == object
            if not ok:
                wrong[column] = str(actual)
        assert not wrong, f"schema contract dtype drift: {wrong}"

    def test_itemized_score_legs_are_present_and_never_blended(
        self, verdicts, append_kwargs, tmp_path
    ):
        ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs)
        frame = ucv.load_candidates(tmp_path)
        for component in ucv.SCORE_COMPONENTS:
            assert f"prophet_{component}" in frame.columns
            assert f"prophet_{component}_points" in frame.columns

    def test_dedupe_key_is_the_documented_triple(self):
        assert ucv.DEDUPE_KEY == ("stamp_date", "ticker", "board_definition")

    def test_nullable_bools_stay_null_not_false(
        self, verdicts, append_kwargs, tmp_path
    ):
        """#4485: an unmeasured flag is None, never False."""
        ucv.append_candidates(verdicts, "2026-07-31", **append_kwargs)
        frame = ucv.load_candidates(tmp_path)
        for column in NULLABLE_BOOL_COLUMNS:
            values = frame[column]
            assert values.isna().all(), (
                f"{column} was fabricated as a value when nothing measured it; "
                "an unmeasured flag must stay null"
            )


# --------------------------------------------------------------------------- #
# 4. assembly units — frozen inputs, no I/O
# --------------------------------------------------------------------------- #

class TestBuildRecords:

    def test_spine_is_the_verdict_map(self, verdicts):
        records = ucv.build_records(
            verdicts, stamp_date="2026-07-31",
            board_definition="us_prophet_v1", is_buyable=_is_buyable)
        assert [r["ticker"] for r in records] == ["AAA", "BBB", "CCC"]
        assert all(r["stamp_date"] == "2026-07-31" for r in records)

    def test_legs_are_read_off_the_board_row_not_recomputed(self, verdicts):
        board = {"AAA": {"prophet": {
            "score": 86.9,
            "components": {"signal": 1.0, "entry": 0.9, "edge": 0.8,
                           "runway": 1.0, "quality": 0.4},
            "points": {"signal": 30.0, "entry": 22.5, "edge": 20.0,
                       "runway": 10.0, "quality": 4.0},
            "alpha_percentile": 0.93,
        }, "score_rank": 1, "featured": True}}
        records = ucv.build_records(
            verdicts, stamp_date="2026-07-31",
            board_definition="us_prophet_v1", is_buyable=_is_buyable,
            board_rows=board)
        by_ticker = {r["ticker"]: r for r in records}
        assert by_ticker["AAA"]["prophet_signal_points"] == 30.0
        assert by_ticker["AAA"]["prophet_quality"] == 0.4
        assert by_ticker["AAA"]["alpha_percentile"] == 0.93
        # a name off the board carries NULL legs, never a zero
        assert by_ticker["BBB"]["prophet_signal_points"] is None
        assert by_ticker["BBB"]["prophet_score"] is None

    def test_near_miss_reason_absent_key_becomes_null(self, verdicts):
        records = ucv.build_records(
            verdicts, stamp_date="2026-07-31",
            board_definition="us_prophet_v1", is_buyable=_is_buyable)
        by_ticker = {r["ticker"]: r for r in records}
        assert by_ticker["BBB"]["near_miss_reason"] == "not_topped_veto"
        assert by_ticker["AAA"]["near_miss_reason"] is None

    def test_us_sector_baskets_are_excluded_from_membership(self, verdicts):
        records = ucv.build_records(
            verdicts, stamp_date="2026-07-31",
            board_definition="us_prophet_v1", is_buyable=_is_buyable,
            theme_ids={"AAA": ["ai_semiconductors", "us_sector_tech", "ai_infra"]})
        row = {r["ticker"]: r for r in records}["AAA"]
        assert row["theme_membership_count"] == 2
        assert row["theme_membership_ids"] == "ai_infra|ai_semiconductors"

    def test_missing_membership_source_nulls_the_count_rather_than_zeroing_it(
        self, verdicts
    ):
        """A missing file must not render as evidence.

        With no membership source loaded, every name would otherwise be stamped
        "in 0 curated baskets" — a confident measurement manufactured out of an
        absent input. The count is null unless the source actually loaded.
        """
        blind = ucv.build_records(
            verdicts, stamp_date="2026-07-31",
            board_definition="us_prophet_v1", is_buyable=_is_buyable,
            theme_ids={})                      # source unavailable
        assert {r["theme_membership_count"] for r in blind} == {None}

        seeing = ucv.build_records(
            verdicts, stamp_date="2026-07-31",
            board_definition="us_prophet_v1", is_buyable=_is_buyable,
            theme_ids={"AAA": ["ai_infra"]})   # source loaded; BBB genuinely in none
        by_ticker = {r["ticker"]: r for r in seeing}
        assert by_ticker["AAA"]["theme_membership_count"] == 1
        assert by_ticker["BBB"]["theme_membership_count"] == 0

    def test_foresight_stage_joins_only_through_the_crosswalk(self, verdicts):
        """No fuzzy joins: an unmapped basket contributes no stage."""
        records = ucv.build_records(
            verdicts, stamp_date="2026-07-31",
            board_definition="us_prophet_v1", is_buyable=_is_buyable,
            theme_ids={"AAA": ["ai_semiconductors"], "BBB": ["mag7"]},
            foresight_by_basket={"ai_semiconductors": "ai_semiconductors"},
            foresight_stages={"ai_semiconductors": "BROADENING"})
        by_ticker = {r["ticker"]: r for r in records}
        assert by_ticker["AAA"]["foresight_stage"] == "BROADENING"
        assert by_ticker["BBB"]["foresight_stage"] is None

    def test_regime_block_is_identical_on_every_row(self, verdicts):
        records = ucv.build_records(
            verdicts, stamp_date="2026-07-31",
            board_definition="us_prophet_v1", is_buyable=_is_buyable,
            regime={"regime_dispersion_state": "lean_in", "regime_gate_go": False,
                    "regime_market_quad": "Q2", "regime_quad_name": "Reflation",
                    "regime_vol_regime": "normalizing"})
        assert {r["regime_market_quad"] for r in records} == {"Q2"}
        assert {r["regime_dispersion_state"] for r in records} == {"lean_in"}

    def test_turnover_60d_is_stamped_null_pending_deeper_caches(self, verdicts):
        records = ucv.build_records(
            verdicts, stamp_date="2026-07-31",
            board_definition="us_prophet_v1", is_buyable=_is_buyable,
            turnover={"AAA": {"turnover_pctile_20d": 0.85,
                              "turnover_window_20d": 20}})
        by_ticker = {r["ticker"]: r for r in records}
        assert by_ticker["AAA"]["turnover_pctile_20d"] == 0.85
        assert by_ticker["AAA"]["turnover_pctile_60d"] is None


class TestRelayFeatures:

    def _panel(self, n=90):
        idx = pd.bdate_range("2026-01-01", periods=n)
        # DDD ramps to a fresh high on the last bar; EEE broke out earlier;
        # FFF and GGG are flat and never break out.
        flat = pd.Series(100.0, index=idx)
        ddd = flat.copy(); ddd.iloc[-1] = 150.0
        eee = flat.copy(); eee.iloc[-6] = 150.0; eee.iloc[-5:] = 120.0
        return pd.DataFrame({"DDD": ddd, "EEE": eee,
                             "FFF": flat.copy(), "GGG": flat.copy()})

    def test_relay_counts_other_members_not_itself(self):
        out = ucv.relay_features(
            self._panel(), {"theme": ["DDD", "EEE", "FFF", "GGG"]},
            high_lookback=63, recent_sessions=3, position_window=21,
            min_members=4)
        assert out["DDD"]["relay_count_3d"] == 0     # EEE fired 6 sessions ago
        assert out["DDD"]["relay_position"] == round(1 / 4, 4)  # EEE went earlier
        assert out["DDD"]["relay_members_covered"] == 4

    def test_basket_below_min_members_yields_nothing(self):
        out = ucv.relay_features(
            self._panel(), {"theme": ["DDD", "EEE"]},
            high_lookback=63, recent_sessions=3, position_window=21,
            min_members=4)
        assert out == {}

    def test_empty_inputs_are_safe(self):
        assert ucv.relay_features(None, {"t": ["A"]}, high_lookback=63,
                                  recent_sessions=3, position_window=21,
                                  min_members=4) == {}
        assert ucv.relay_features(self._panel(), {}, high_lookback=63,
                                  recent_sessions=3, position_window=21,
                                  min_members=4) == {}


class TestTurnoverPercentiles:

    def test_own_history_percentile_is_time_series_not_cross_sectional(self):
        idx = pd.bdate_range("2026-01-01", periods=40)
        # HHH ends at its own maximum; III ends at its own minimum. Their
        # absolute levels are inverted, so a cross-sectional rank would flip.
        frame = pd.DataFrame(
            {"HHH": list(range(1, 41)), "III": list(range(4000, 0, -100))},
            index=idx)
        out = ucv.turnover_percentiles(frame, "2026-02-25")
        assert out["HHH"]["turnover_pctile_20d"] == 1.0
        assert out["III"]["turnover_pctile_20d"] == 0.05
        assert out["HHH"]["turnover_window_20d"] == 20

    def test_short_history_is_skipped_rather_than_guessed(self):
        idx = pd.bdate_range("2026-01-01", periods=10)
        frame = pd.DataFrame({"JJJ": range(10)}, index=idx)
        assert ucv.turnover_percentiles(frame, "2026-01-14") == {}

    def test_future_sessions_are_excluded_pit(self):
        idx = pd.bdate_range("2026-01-01", periods=40)
        frame = pd.DataFrame({"KKK": list(range(1, 41))}, index=idx)
        # asof mid-panel: the trailing window must end at asof, so the last
        # observation ranks top of ITS window, not of the whole frame.
        out = ucv.turnover_percentiles(frame, "2026-01-30")
        assert out["KKK"]["turnover_pctile_20d"] == 1.0
        assert out["KKK"]["turnover_window_20d"] == 20


class TestBasketMembership:

    def test_pit_membership_honors_added_and_removed(self, tmp_path):
        import json
        data = tmp_path / "data" / "baskets"
        data.mkdir(parents=True)
        (data / "membership.json").write_text(json.dumps({"baskets": {
            "ai_infra": {"members": [
                {"ticker": "OLD", "added": "2020-01-01", "removed": "2026-01-01"},
                {"ticker": "NOW", "added": "2020-01-01", "removed": None},
                {"ticker": "FUT", "added": "2026-12-01", "removed": None},
            ]},
            "us_sector_tech": {"members": [{"ticker": "XLK", "added": None,
                                            "removed": None}]},
        }}))
        out = ucv.basket_membership("2026-07-31", root=tmp_path)
        assert out == {"ai_infra": ["NOW"]}      # us_sector_* excluded entirely

    def test_absent_membership_file_is_safe(self, tmp_path):
        assert ucv.basket_membership("2026-07-31", root=tmp_path) == {}
