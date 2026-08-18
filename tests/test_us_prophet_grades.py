"""Tests for the full-population US candidate grader (PROPHET US §W7).

Pinned here, in order of how badly a regression would hurt:

1. **NIGHTLY IS THE SOLE ADVANCER** — and the gate test is MUTATION-CHECKED: it asserts
   both that an off-lane run writes nothing AND that the same call on-lane DOES write, so
   deleting the gate flips it red instead of leaving it green for the wrong reason. (The
   repo conftest arms ``COLLECT_LANE=nightly`` for every test, so a gate test that only
   pops the variable can pass against a gateless implementation that happened to fail for
   an unrelated reason.)
2. **Idempotence / one-grader law** — a second run on the same night appends nothing, and
   a graded key is never rewritten.
3. **Monthly-part isolation** — a later run leaves every earlier part BYTE-IDENTICAL.
4. **Anti-fork** — :func:`engine.us_prophet_grades.grade_row` and
   ``scripts.grade_prophet_doors.grade_flag`` are pinned to identical marks on identical
   input, so the two wrappers over ``engine.grading.forward_metrics`` cannot drift into two
   sets of numbers under one name.
5. **The ruler's semantics** — next-bar fill, positional (session) horizons, unmatured
   horizons ABSENT rather than zero, null-not-zero excess when the benchmark is missing.
6. **Scorecard null-disclosure shape** — the miss-audit block prints a named reason on
   every null and never asserts a statistic it did not compute.
7. **Zero authority** — nothing outside the CLI, the miss-audit and these tests imports it.

Hermetic: every test passes ``root=tmp_path`` and injects its own price panel/benchmark,
so nothing reads the repo's real ``data/`` tree (MM_DATA_GUARD).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from engine import prophet_miss_audit as pma
from engine import us_context_vector as ucv
from engine import us_prophet_grades as upg

REPO = Path(__file__).resolve().parents[1]

BOARD_DEF = "us_prophet_v1"
# long enough that the WHOLE ladder (H=63 + a next-bar fill) matures for the latest fixture
# stamp — otherwise the long-horizon assertions would silently test nothing.
SESSIONS = 160


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _calendar(n: int = SESSIONS) -> pd.DatetimeIndex:
    """A pure trading-day index — the store's own basis (parquets hold sessions only)."""
    return pd.bdate_range("2026-06-01", periods=n)


def _panel(index: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Three names with deterministic, monotone-distinct paths + the benchmark's own."""
    idx = index if index is not None else _calendar()
    n = len(idx)
    return pd.DataFrame(
        {
            # a clear winner, a clear loser, and one that tracks the benchmark
            "AAA": [100.0 * (1.0 + 0.004 * i) for i in range(n)],
            "BBB": [100.0 * (1.0 - 0.002 * i) for i in range(n)],
            "CCC": [100.0 * (1.0 + 0.001 * i) for i in range(n)],
        },
        index=idx,
    )


def _bench(index: pd.DatetimeIndex | None = None) -> pd.Series:
    idx = index if index is not None else _calendar()
    return pd.Series([100.0 * (1.0 + 0.001 * i) for i in range(len(idx))], index=idx)


def _write_candidates(root: Path, rows: list[dict]) -> None:
    """Write candidate rows into the real monthly-part layout, via the store's own path
    helper — the test must exercise the layout the grader reads, not a stand-in."""
    frame = pd.DataFrame(rows)
    for month, sub in frame.groupby(frame["stamp_date"].str.slice(0, 7)):
        path = ucv._part_path(f"{month}-01", root)
        path.parent.mkdir(parents=True, exist_ok=True)
        sub.reset_index(drop=True).to_parquet(path, index=False)


def _candidate_rows(dates: list[str], tickers=("AAA", "BBB", "CCC"),
                    scores: dict[str, float] | None = None,
                    cohorts: dict[str, str] | None = None,
                    labels: dict[str, str] | None = None,
                    cohort_column: str = "universe_tier",
                    label_column: str = "cycle_state") -> list[dict]:
    scores = scores or {"AAA": 88.0, "BBB": 41.0, "CCC": 65.0}
    rows = []
    for d in dates:
        for t in tickers:
            row = {
                "stamp_date": d, "ticker": t, "board_definition": BOARD_DEF,
                "lane": "buy", "sector": "Information Technology",
                "eligible": True, "prophet_score": scores.get(t),
                "prophet_signal": 0.8, "prophet_edge": 0.5,
            }
            if cohorts is not None:
                row[cohort_column] = cohorts.get(t)
            if labels is not None:
                row[label_column] = labels.get(t)
            rows.append(row)
    return rows


@pytest.fixture
def two_month_store(tmp_path):
    """A synthetic TWO-MONTH candidates store — the layout the grader must span.

    (The real store's first stamp lands with the nightly that follows #4540's merge, so the
    build is verified against this fixture and the schema-contract suite, per the PR body.)
    """
    idx = _calendar()
    june = [str(d.date()) for d in idx if d.month == 6][:4]
    july = [str(d.date()) for d in idx if d.month == 7][:3]
    _write_candidates(tmp_path, _candidate_rows(june + july))
    return {"root": tmp_path, "dates": june + july, "june": june, "july": july,
            "panel": _panel(idx), "bench": _bench(idx)}


WIDE_N = 30


@pytest.fixture
def wide_store(tmp_path):
    """A cross-section wide enough for the SCORECARD's own floors (rank-IC needs 5+
    distinct scores a date; P@k and the decile table need 20+ scored names a date).

    The score is constructed to rank the forward outcome PERFECTLY, so the scorecard's
    arithmetic is checked against a known answer: a positive rank-IC and a top decile above
    the bottom one are then evidence the join and the ordering are right, not luck.
    """
    idx = _calendar()
    tickers = [f"T{i:02d}" for i in range(WIDE_N)]
    # drift ascends with i, so higher i = better forward excess, by construction
    panel = pd.DataFrame(
        {t: [100.0 * (1.0 + (0.0005 * i) * s) for s in range(len(idx))]
         for i, t in enumerate(tickers)}, index=idx)
    dates = [str(d.date()) for d in idx[:3]]
    scores = {t: float(10 + 3 * i) for i, t in enumerate(tickers)}
    _write_candidates(tmp_path, _candidate_rows(dates, tuple(tickers), scores))
    return {"root": tmp_path, "dates": dates, "panel": panel, "bench": _bench(idx),
            "tickers": tickers, "scores": scores}


def _run(store, **kw):
    return upg.run(store["root"], panel=store["panel"], bench=store["bench"], **kw)


def _part_digests(root: Path) -> dict[str, str]:
    store = upg._store_dir(root)
    return {str(p.relative_to(store)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(store.glob("*/*.parquet"))}


# --------------------------------------------------------------------------- #
# 1. nightly-is-the-sole-advancer (MUTATION-CHECKED)
# --------------------------------------------------------------------------- #

class TestNightlyLaneGate:

    @pytest.mark.parametrize("lane", [None, "intraday", "render", "weekly", "asia"])
    def test_off_lane_writes_nothing(self, lane, two_month_store, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        if lane is not None:
            monkeypatch.setenv("COLLECT_LANE", lane)
        doc = _run(two_month_store)
        assert doc["new_grades"] > 0, (
            "the fixture must produce matured grades — otherwise this test would pass "
            "on an empty run and prove nothing about the gate")
        assert doc["appended"] == 0
        assert not upg._store_dir(two_month_store["root"]).exists()

    def test_on_lane_does_write(self, two_month_store, monkeypatch):
        """The other half of the mutation check: same call, lane armed, rows land.

        Without this, deleting the gate could still leave the test above green (it would
        be asserting on a run that failed for some unrelated reason)."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        doc = _run(two_month_store)
        assert doc["appended"] > 0
        assert upg.load_grades(two_month_store["root"]).shape[0] == doc["appended"]

    def test_legacy_us_lane_alias_is_honoured(self, two_month_store, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.setenv("US_LANE", "nightly")
        assert _run(two_month_store)["appended"] > 0


# --------------------------------------------------------------------------- #
# 2. idempotence / one-grader law
# --------------------------------------------------------------------------- #

class TestIdempotence:

    def test_second_run_same_night_appends_nothing(self, two_month_store):
        first = _run(two_month_store)
        assert first["new_grades"] > 0
        n_rows = len(upg.load_grades(two_month_store["root"]))

        second = _run(two_month_store)
        assert second["new_grades"] == 0, "a re-run must find every key already frozen"
        assert second["appended"] == 0
        assert second["already_graded"] == first["new_grades"]
        assert len(upg.load_grades(two_month_store["root"])) == n_rows

    def test_graded_key_is_never_rewritten(self, two_month_store):
        _run(two_month_store)
        before = upg.load_grades(two_month_store["root"]).sort_values(
            list(upg.GRADE_KEY)).reset_index(drop=True)

        # a hostile re-append of the SAME keys with different numbers must not land
        rows = [{**r, "fwd_ret": 9.99, "excess_spy": 9.99}
                for r in before.to_dict("records")]
        upg.append_grades(rows, before["graded_asof"].iloc[0], two_month_store["root"])

        after = upg.load_grades(two_month_store["root"]).sort_values(
            list(upg.GRADE_KEY)).reset_index(drop=True)
        assert len(after) == len(before)
        assert (after["fwd_ret"] != 9.99).all(), "keep-FIRST must survive a hostile append"

    def test_grade_key_is_the_documented_tuple(self):
        assert upg.GRADE_KEY == ("stamp_date", "ticker", "board_definition", "horizon")


# --------------------------------------------------------------------------- #
# 3. monthly-part isolation
# --------------------------------------------------------------------------- #

class TestMonthlyPartLayout:

    def test_part_is_keyed_by_the_grading_run_not_the_stamp(self, two_month_store):
        """Run-keying is what makes closed parts permanent: a June stamp graded in an
        October run belongs to October's part, so June's is never reopened."""
        doc = _run(two_month_store)
        store = upg._store_dir(two_month_store["root"])
        parts = sorted(str(p.relative_to(store)) for p in store.glob("*/*.parquet"))
        run_day = str(doc["graded_asof"])[:10]
        assert parts == [f"{run_day[:7]}/{run_day}.parquet"], (
            "one run writes exactly one day part, inside its month directory")
        stamped = upg.load_grades(two_month_store["root"])["stamp_date"]
        assert {str(s)[:7] for s in stamped} - {run_day[:7]}, (
            "the fixture must grade at least one stamp month other than the run month, "
            "or this test cannot see the difference between the two keyings")

    def test_earlier_parts_stay_byte_identical(self, two_month_store):
        """A later run must not rewrite a single byte of any earlier part.

        With a day-grained write this is absolute, not merely usual: a run never opens a
        file another run wrote.
        """
        root = two_month_store["root"]
        # first run on a SHORT panel: only the earliest stamps have matured
        short = two_month_store["panel"].iloc[: 4 + max(upg.HORIZONS) + 2]
        first = upg.run(root, panel=short,
                        bench=two_month_store["bench"].iloc[:len(short)])
        first_parts = _part_digests(root)
        assert first_parts and first["new_grades"] > 0, "the short run must have written"

        # second run on the FULL panel, from a later date — new rows, new part
        full = two_month_store["panel"]
        assert str(full.index[-1].date()) != str(short.index[-1].date()), (
            "the two runs must land on different dates or the isolation claim is untested")
        second = upg.run(root, panel=full, bench=two_month_store["bench"])
        assert second["new_grades"] > 0, "the later run must have graded something new"

        after = _part_digests(root)
        for name, digest in first_parts.items():
            assert after[name] == digest, f"part {name} was rewritten by a later run"
        assert len(after) > len(first_parts), "the later run must have opened its own part"

    def test_a_rerun_on_the_same_day_rewrites_only_that_day(self, two_month_store):
        """The one file a run may reopen is its OWN day — and even then keep-first holds."""
        root = two_month_store["root"]
        short = two_month_store["panel"].iloc[: 4 + max(upg.HORIZONS) + 2]
        upg.run(root, panel=short, bench=two_month_store["bench"].iloc[:len(short)])
        upg.run(root, panel=two_month_store["panel"], bench=two_month_store["bench"])
        before = _part_digests(root)
        upg.run(root, panel=two_month_store["panel"], bench=two_month_store["bench"])
        assert _part_digests(root) == before, (
            "an idempotent re-run must not change a single byte anywhere")

    def test_load_grades_spans_parts_in_chronological_order(self, two_month_store):
        root = two_month_store["root"]
        short = two_month_store["panel"].iloc[: 4 + max(upg.HORIZONS) + 2]
        upg.run(root, panel=short, bench=two_month_store["bench"].iloc[:len(short)])
        upg.run(root, panel=two_month_store["panel"], bench=two_month_store["bench"])
        graded = upg.load_grades(root)
        assert len(graded) == len(graded.drop_duplicates(subset=list(upg.GRADE_KEY)))
        asofs = [str(a) for a in graded["graded_asof"]]
        assert asofs == sorted(asofs), "parts must concatenate chronologically"


# --------------------------------------------------------------------------- #
# 4. anti-fork: the ruler is shared with the doors grader
# --------------------------------------------------------------------------- #

class TestAntiFork:

    def test_grade_row_matches_the_doors_grader_mark_for_mark(self):
        """Two wrappers, one ruler.  If either drifts, this fails instead of shipping two
        sets of numbers under the name 'excess vs SPY'.

        Pinned on the SHARED horizons — this grader's ladder is a superset (H=42/63 were
        added by the 2026-08-05 basing ruling), and a longer ladder is not a different
        ruler.
        """
        from scripts import grade_prophet_doors as gpd

        idx = _calendar()
        close, bench = _panel(idx)["AAA"], _bench(idx)
        stamp = str(idx[3].date())
        shared = tuple(h for h in upg.HORIZONS if h in gpd.HORIZONS)
        assert shared, "the two graders must share at least one horizon to be comparable"

        mine = upg.grade_row(close, bench, stamp, shared)
        theirs = gpd.grade_flag(close, bench, stamp, shared)

        assert set(mine) == set(theirs) and mine, "both must mature the same horizons"
        for horizon in mine:
            for field in ("entry_price", "fill_date", "mark_date", "fwd_ret",
                          "bench_ret", "excess_spy", "fwd_mfe", "fwd_mdd"):
                assert mine[horizon][field] == theirs[horizon][field], (
                    f"H={horizon} field {field} drifted from the doors grader")

    def test_the_ladder_is_a_superset_of_the_doors_grader(self):
        from scripts import grade_prophet_doors as gpd
        assert upg.BENCH == gpd.BENCH
        assert set(gpd.HORIZONS) <= set(upg.HORIZONS), (
            "the incumbent horizons must survive — the ladder ADDS maturities, it never "
            "replaces the reads the existing record is built on")
        assert upg.HORIZONS == (10, 21, 42, 63)
        assert tuple(sorted(upg.HORIZONS)) == upg.HORIZONS, "ladder must be ascending"


# --------------------------------------------------------------------------- #
# 5. ruler semantics
# --------------------------------------------------------------------------- #

class TestRulerSemantics:

    def test_fill_is_the_bar_strictly_after_the_stamp(self):
        idx = _calendar()
        close = _panel(idx)["AAA"]
        stamp = str(idx[5].date())
        mark = upg.grade_row(close, _bench(idx), stamp)[10]
        assert mark["fill_date"] == str(idx[6].date()), "no same-bar entry, ever"
        assert mark["entry_price"] == pytest.approx(float(close.iloc[6]))

    def test_horizon_is_sessions_not_calendar_days(self):
        idx = _calendar()
        stamp = str(idx[5].date())
        mark = upg.grade_row(_panel(idx)["AAA"], _bench(idx), stamp)[10]
        assert mark["mark_date"] == str(idx[16].date()), (
            "H=10 must be ten SESSIONS past the fill bar (index positions), not ten "
            "calendar days")

    def test_unmatured_horizon_is_absent_not_zero(self):
        idx = _calendar(14)          # long enough for H=10, short of H=21
        marks = upg.grade_row(_panel(idx)["AAA"], _bench(idx), str(idx[1].date()))
        assert 10 in marks and 21 not in marks, (
            "an unmatured horizon must be ABSENT so it grades later, never marked short")

    def test_excess_is_null_not_zero_without_a_benchmark(self):
        idx = _calendar()
        mark = upg.grade_row(_panel(idx)["AAA"], None, str(idx[3].date()))[10]
        assert mark["bench_ret"] is None and mark["excess_spy"] is None
        assert mark["fwd_ret"] is not None, "absolute marks still grade without SPY"

    def test_excess_is_the_difference_of_the_two_graded_legs(self):
        idx = _calendar()
        mark = upg.grade_row(_panel(idx)["AAA"], _bench(idx), str(idx[3].date()))[21]
        assert mark["excess_spy"] == pytest.approx(
            mark["fwd_ret"] - mark["bench_ret"], abs=1e-6)

    def test_matured_horizons_is_a_necessary_condition_only(self):
        idx = _calendar()
        stamp = str(idx[-12].date())
        assert upg.matured_horizons(idx, stamp) == (10,)
        assert upg.matured_horizons(idx, str(idx[-1].date())) == ()
        assert upg.matured_horizons(pd.DatetimeIndex([]), stamp) == ()

    def test_a_name_with_no_price_column_is_counted_not_dropped_silently(
            self, two_month_store):
        store = dict(two_month_store)
        store["panel"] = two_month_store["panel"].drop(columns=["BBB"])
        doc = _run(store)
        assert doc["skipped_no_price"] > 0
        assert "BBB" not in set(upg.load_grades(store["root"])["ticker"])


# --------------------------------------------------------------------------- #
# 6. store plumbing
# --------------------------------------------------------------------------- #

class TestStoreReaders:

    def test_load_candidates_column_projection_matches_a_full_read(self, two_month_store):
        root = two_month_store["root"]
        full = ucv.load_candidates(root)
        projected = ucv.load_candidates(root, columns=["ticker", "prophet_score"])
        assert list(projected.columns) == ["ticker", "prophet_score"]
        pd.testing.assert_frame_equal(
            projected.reset_index(drop=True),
            full[["ticker", "prophet_score"]].reset_index(drop=True))

    def test_projection_of_an_absent_column_reads_null_not_error(self, two_month_store):
        frame = ucv.load_candidates(two_month_store["root"],
                                    columns=["ticker", "column_that_does_not_exist"])
        assert frame["column_that_does_not_exist"].isna().all()

    def test_graded_frame_joins_the_stamped_score(self, two_month_store):
        _run(two_month_store)
        joined = upg.load_graded_frame(two_month_store["root"],
                                       score_columns=["lane", "sector"])
        assert {"prophet_score", "lane", "sector"} <= set(joined.columns)
        assert joined.loc[joined["ticker"] == "AAA", "prophet_score"].eq(88.0).all()

    def test_coverage_discloses_an_empty_store(self, tmp_path):
        block = upg.coverage(tmp_path)
        assert block["available"] is False
        assert block["n_rows"] == 0
        assert "null_reason" in block and block["null_reason"]

    def test_empty_candidate_store_is_a_named_note_not_a_crash(self, tmp_path):
        doc = upg.run(tmp_path, panel=_panel(), bench=_bench())
        assert doc["new_grades"] == 0 and doc["note"]


# --------------------------------------------------------------------------- #
# 7. priority-score scorecard (miss-audit block)
# --------------------------------------------------------------------------- #

class TestPriorityScoreScorecard:

    def test_empty_store_yields_a_named_null_never_a_statistic(self, tmp_path):
        block = pma.priority_score_scorecard(tmp_path)
        assert block["tier"] == "ops_telemetry"
        assert block["available"] is False
        assert block["null_reason"], "an absent measurement must say WHY it is absent"
        assert "by_cohort" not in block or not block["by_cohort"]

    def test_populated_store_reports_every_required_leg(self, two_month_store):
        _run(two_month_store)
        block = pma.priority_score_scorecard(two_month_store["root"])
        assert block["available"] is True
        assert block["authority"].startswith("none")
        legs = block["by_cohort"]["unsplit"]
        assert set(legs) == {f"{h}d" for h in upg.HORIZONS}, (
            "every horizon in the ladder must be reported, not just the incumbent two")
        for horizon in legs:
            leg = legs[horizon]
            assert set(leg) >= {"horizon_d", "n_graded", "n_scored", "rank_ic",
                                "precision_at_k", "deciles", "population",
                                "by_signal_class"}
            # every null carries a reason; no statistic is asserted from nothing
            if leg["rank_ic"] is None:
                assert leg.get("null_reason")

    def test_there_is_no_pooled_leg_for_a_reader_to_misquote(self, two_month_store):
        """'Never pooled' has to be structural: if no cross-cohort rank-IC exists, none can
        be quoted."""
        _run(two_month_store)
        block = pma.priority_score_scorecard(two_month_store["root"])
        assert "by_horizon" not in block, (
            "a top-level horizon leg would be a pooled read across cohorts")
        assert "rank_ic" not in block and "precision_at_k" not in block

    def test_score_coverage_is_disclosed_not_imputed(self, two_month_store):
        """The builder computes the priority legs on the BUY LANE only, so most rows have
        no score.  The block must print that coverage, never treat a null score as 0."""
        rows = _candidate_rows(two_month_store["dates"])
        for row in rows:                       # strip the score off two of three names
            if row["ticker"] != "AAA":
                row["prophet_score"] = None
        _write_candidates(two_month_store["root"], rows)
        _run(two_month_store)
        block = pma.priority_score_scorecard(two_month_store["root"])
        cov = block["score_coverage"]
        assert cov["n_rows"] > cov["n_scored"] > 0
        assert 0.0 < cov["coverage_pct"] < 100.0
        assert cov["note"], "coverage needs a plain-word note, not just a number"

    def test_a_cross_section_too_narrow_for_rank_ic_says_so(self, two_month_store):
        """Three names cannot carry 5 distinct scores, so rank-IC is NOT computable — the
        block must name that, not print a correlation over three points."""
        _run(two_month_store)
        leg = pma.priority_score_scorecard(two_month_store["root"])["by_cohort"]["unsplit"]["10d"]
        assert leg["rank_ic"] is None
        assert "5+ distinct" in leg["null_reason"]
        assert leg["thin"] is True

    def test_thin_cohorts_are_marked_thin(self, wide_store):
        _run(wide_store)
        leg = pma.priority_score_scorecard(wide_store["root"])["by_cohort"]["unsplit"]["10d"]
        assert leg["rank_ic"] is not None, "the wide fixture must reach the measured path"
        assert leg["thin"] is True, (
            "three stamp dates must read as a sample, not a measurement")
        assert leg.get("thin_reason") and "disclosure floor" in leg["thin_reason"]

    def test_a_perfect_score_recovers_a_positive_rank_ic_and_decile_lift(self, wide_store):
        """The arithmetic against a known answer: the fixture's score ranks the forward
        outcome exactly, so a scrambled join or an inverted decile cut fails here."""
        _run(wide_store)
        leg = pma.priority_score_scorecard(wide_store["root"])["by_cohort"]["unsplit"]["21d"]
        assert leg["rank_ic"] == pytest.approx(1.0, abs=1e-6)
        deciles = leg["deciles"]
        assert deciles["n_dates_eligible"] == 3 and deciles["n_dates_excluded_thin"] == 0
        assert deciles["by_decile"]["d10"]["mean_excess"] > \
            deciles["by_decile"]["d1"]["mean_excess"]
        assert deciles["top_minus_bottom_excess"] > 0
        assert deciles["by_decile"]["d10"]["loser_rate"] == 0.0, (
            "the top decile of a perfectly-ordered score must lose to SPY 0% of the time")
        assert deciles["by_decile"]["d1"]["loser_rate"] > \
            deciles["by_decile"]["d10"]["loser_rate"], (
            "the operator's question — the bottom of the ordering must lose more often "
            "than the top, or the score is not ordering anything")
        pk = leg["precision_at_k"]["by_k"]
        assert pk["p_at_1"]["value"] == 1.0 and pk["p_at_1"]["lift_vs_base"] > 0
        assert set(leg["precision_at_k"]["by_k"]) == {
            f"p_at_{k}" for k in pma.PRIORITY_PK_K}

    def test_hits_are_judged_against_the_whole_graded_universe(self, wide_store):
        """The capability full-population grading buys: the comparator is that night's
        entire universe, stated in the definition string, not the ranked cohort alone."""
        _run(wide_store)
        leg = pma.priority_score_scorecard(wide_store["root"])["by_cohort"]["unsplit"]["21d"]
        assert "FULL-population median" in leg["precision_at_k"]["definition"]
        assert "FULL graded population" in leg["deciles"]["definition"]

    def test_lane_breakdown_needs_its_own_floor(self, wide_store):
        _run(wide_store)
        pop = pma.priority_score_scorecard(
            wide_store["root"])["by_cohort"]["unsplit"]["21d"]["population"]
        assert pop["n"] == WIDE_N * 3
        assert pop["by_lane"]["buy"]["n"] == WIDE_N * 3
        assert pop["mean_excess"] is not None and pop["pos_rate"] is not None

    def test_population_leg_counts_the_whole_graded_universe(self, two_month_store):
        """The 'more data to train on' half: the population block must be sized by every
        graded row, not by the scored subset."""
        _run(two_month_store)
        block = pma.priority_score_scorecard(two_month_store["root"])
        leg = block["by_cohort"]["unsplit"]["21d"]
        graded = upg.load_grades(two_month_store["root"])
        n_21 = int((graded["horizon"] == 21).sum())
        assert leg["population"]["n"] == n_21 > 0

    def test_block_reaches_the_artifact_and_the_forward_log_row(
            self, two_month_store, monkeypatch):
        """A block no artifact carries is a block nobody reads.

        Drives the real ``build_audit`` with a synthetic universe (the heavy tier scan is
        the only thing stubbed), so the assertion is about the document the nightly writes,
        not about a constant listing what it is supposed to contain.
        """
        _run(two_month_store)
        idx = pd.bdate_range("2025-06-02", periods=260)
        wide = _panel(idx)
        monkeypatch.setattr(pma, "load_universe",
                            lambda root=None: (wide, {t: "IT" for t in wide.columns}, []))
        doc = pma.build_audit(two_month_store["root"], top63_n=3, top21_n=2,
                              with_gate=False, with_cascade_basis=False,
                              with_name_score=False)
        block = doc["priority_score_scorecard"]
        assert block["available"] is True
        assert "priority_score" in doc["bases"]

        row = pma.summary_row(doc)
        assert row["priority_score_available"] is True
        assert row["priority_score_n_rows"] == block["score_coverage"]["n_rows"]
        assert row["priority_cohort_split_available"] is False
        # the log's columns are FIXED per (cohort, horizon, class) — a column set that
        # depended on tonight's data would not be a series anyone could plot
        for cohort in ("curated", "scan", "unsplit"):
            for horizon in pma.PRIORITY_HORIZONS:
                assert f"priority_{cohort}_rank_ic_{horizon}d" in row
                assert f"priority_{cohort}_n_{horizon}d" in row
                assert f"priority_{cohort}_basing_mean_excess_{horizon}d" in row
        assert row["priority_unsplit_n_21d"] > 0
        assert row["priority_curated_n_21d"] is None, (
            "a cohort with no rows must be a NULL column, never 0")

    def test_row_fields_are_null_safe_on_a_document_with_no_block(self):
        row = pma.priority_score_row_fields({})
        assert row["priority_score_available"] is False
        assert row["priority_score_n_rows"] is None


# --------------------------------------------------------------------------- #
# 7b. cohort discriminator (scan tier) + signal class (basing vs momentum)
# --------------------------------------------------------------------------- #

class TestCohortDiscriminator:

    def test_absent_column_is_disclosed_and_never_called_curated(self, two_month_store):
        """The column has not landed yet. The run must SAY so — a store with no split is
        one 'unsplit' population, never a population labelled 'curated' by default."""
        doc = _run(two_month_store)
        disc = doc["discriminator"]
        assert disc["available"] is False and disc["column"] is None
        assert "universe_tier" in disc["reason"]
        assert set(doc["by_cohort"]) == {"unsplit"}
        block = pma.priority_score_scorecard(two_month_store["root"])
        assert block["cohort_split"]["available"] is False
        assert "curated" not in block["by_cohort"]

    def test_a_present_column_splits_the_record(self, two_month_store):
        rows = _candidate_rows(two_month_store["dates"],
                               cohorts={"AAA": "curated", "BBB": "scan", "CCC": "scan"})
        _write_candidates(two_month_store["root"], rows)
        doc = _run(two_month_store)
        assert doc["discriminator"]["column"] == "universe_tier"
        assert doc["by_cohort"]["curated"] * 2 == doc["by_cohort"]["scan"]
        graded = upg.load_grades(two_month_store["root"])
        assert set(graded.loc[graded["ticker"] == "BBB", "universe_tier"]) == {"scan"}

        block = pma.priority_score_scorecard(two_month_store["root"])
        assert block["cohort_split"]["available"] is True
        assert set(block["by_cohort"]) == {"curated", "scan"}
        for cohort in ("curated", "scan"):
            assert set(block["by_cohort"][cohort]) == {f"{h}d" for h in upg.HORIZONS}

    def test_a_name_match_with_wrong_values_is_REJECTED(self, two_month_store):
        """A column that merely shares the name must not mis-cohort the whole store."""
        rows = _candidate_rows(two_month_store["dates"],
                               cohorts={"AAA": "sector_a", "BBB": "sector_b",
                                        "CCC": "sector_c"})
        _write_candidates(two_month_store["root"], rows)
        doc = _run(two_month_store)
        assert doc["discriminator"]["available"] is False
        assert "REJECTED" in doc["discriminator"]["reason"]
        assert set(doc["by_cohort"]) == {"unsplit"}

    def test_unrecognised_values_are_nulled_and_counted_not_guessed(self, two_month_store):
        rows = _candidate_rows(two_month_store["dates"],
                               cohorts={"AAA": "curated", "BBB": "scan", "CCC": "mystery"})
        _write_candidates(two_month_store["root"], rows)
        doc = _run(two_month_store)
        assert doc["discriminator"]["available"] is True
        assert doc["discriminator"]["n_unrecognised"] > 0
        assert doc["by_cohort"]["unsplit"] > 0, "an unknown value is null, never 'curated'"
        assert all(isinstance(k, str) for k in doc["by_cohort"]), (
            "a NaN cohort key would mean the null never reached the 'unsplit' bucket "
            "(NaN is truthy, so `cohort or 'unsplit'` silently keeps it)")
        graded = upg.load_grades(two_month_store["root"])
        assert graded.loc[graded["ticker"] == "CCC", "universe_tier"].isna().all()

    def test_normalize_cohort_vocabulary(self):
        assert upg.normalize_cohort(" CURATED ") == "curated"
        assert upg.normalize_cohort("Scan") == "scan"
        assert upg.normalize_cohort("something_else") is None
        assert upg.normalize_cohort(None) is None


class TestSignalClass:

    def test_the_map_covers_the_whole_live_cycle_vocabulary(self):
        """A label the board can actually print must never fall through to 'other' by
        accident — the map is a prereg, so its coverage is pinned against the live source."""
        from engine.cycles import STATE_DISPLAY
        for state, display in STATE_DISPLAY.items():
            assert state.upper() in upg.SIGNAL_CLASS_BY_LABEL, f"state {state} unmapped"
            assert display["label"].upper() in upg.SIGNAL_CLASS_BY_LABEL, (
                f"display label {display['label']} unmapped")

    def test_basing_and_momentum_are_the_operators_split(self):
        assert upg.classify_signal("BOTTOMING")[0] == upg.CLASS_BASING
        assert upg.classify_signal("TURN SIGNALED")[0] == upg.CLASS_BASING
        assert upg.classify_signal("NEARING A LOW")[0] == upg.CLASS_BASING
        assert upg.classify_signal("UPTREND")[0] == upg.CLASS_MOMENTUM
        assert upg.classify_signal("FRESH BUY")[0] == upg.CLASS_MOMENTUM
        assert upg.classify_signal("DOWNTREND")[0] == upg.CLASS_OTHER

    def test_an_unmapped_label_keeps_its_label(self):
        """A vocabulary that grows must be VISIBLE in the store, not absorbed."""
        assert upg.classify_signal("SOME NEW STATE") == (upg.CLASS_OTHER, "SOME NEW STATE")
        assert upg.classify_signal(None) == (upg.CLASS_OTHER, None)
        assert upg.classify_signal("  bottoming  ")[0] == upg.CLASS_BASING

    def test_chartered_horizons_are_fixed_and_inside_the_ladder(self):
        """The prereg: basing is headlined at a LONG horizon, momentum at a short one, and
        both were fixed before any H=42/63 data existed to peek at."""
        assert upg.CHARTERED_HORIZON[upg.CLASS_BASING]["primary"] == 63
        assert upg.CHARTERED_HORIZON[upg.CLASS_MOMENTUM]["primary"] == 10
        for signal_class in upg.SIGNAL_CLASSES:
            charter = upg.CHARTERED_HORIZON[signal_class]
            assert charter["primary"] in upg.HORIZONS
            assert charter["supporting"] in upg.HORIZONS

    def test_absent_label_column_is_disclosed_not_a_measured_other(self, two_month_store):
        doc = _run(two_month_store)
        sig = doc["signal_labels"]
        assert sig["available"] is False and sig["column"] is None
        assert "cycle_state" in sig["reason"]
        assert doc["by_signal_class"] == {"other": doc["new_grades"]}
        graded = upg.load_grades(two_month_store["root"])
        assert graded["signal_label"].isna().all(), (
            "no label resolved means a NULL label, not a fabricated one")

    def test_a_present_label_column_classes_and_is_carried_through(self, two_month_store):
        rows = _candidate_rows(two_month_store["dates"],
                               labels={"AAA": "BOTTOMING", "BBB": "UPTREND",
                                       "CCC": "SOME NEW STATE"})
        _write_candidates(two_month_store["root"], rows)
        doc = _run(two_month_store)
        assert doc["signal_labels"]["column"] == "cycle_state"
        assert doc["signal_labels"]["n_unmapped_labels"] > 0
        graded = upg.load_grades(two_month_store["root"])
        by_ticker = graded.set_index("ticker")["signal_class"].to_dict()
        assert by_ticker["AAA"] == "basing" and by_ticker["BBB"] == "momentum"
        assert by_ticker["CCC"] == "other"
        assert set(graded.loc[graded["ticker"] == "CCC", "signal_label"]) == {
            "SOME NEW STATE"}, "the unmapped label must survive onto the row"

    def test_the_scorecard_reports_each_class_at_every_horizon(self, two_month_store):
        """The whole point of the ladder: basing at H=63 beside momentum at H=10, with ns."""
        rows = _candidate_rows(two_month_store["dates"],
                               labels={"AAA": "BOTTOMING", "BBB": "BOTTOMING",
                                       "CCC": "UPTREND"})
        _write_candidates(two_month_store["root"], rows)
        _run(two_month_store)
        legs = pma.priority_score_scorecard(two_month_store["root"])["by_cohort"]["unsplit"]
        for horizon in (f"{h}d" for h in upg.HORIZONS):
            classes = legs[horizon]["by_signal_class"]
            assert set(classes) == {"basing", "momentum"}
            assert classes["basing"]["n"] == 2 * classes["momentum"]["n"] > 0

    def test_a_thin_class_gets_a_reason_not_a_number(self, two_month_store):
        rows = _candidate_rows(two_month_store["dates"],
                               labels={"AAA": "BOTTOMING", "BBB": "UPTREND",
                                       "CCC": "UPTREND"})
        _write_candidates(two_month_store["root"], rows)
        _run(two_month_store)
        legs = pma.priority_score_scorecard(two_month_store["root"])["by_cohort"]["unsplit"]
        basing = legs["10d"]["by_signal_class"]["basing"]
        assert basing["n"] < pma.PRIORITY_MIN_LANE_N
        assert basing.get("null_reason") and "mean_excess" not in basing

    def test_a_degenerate_cross_section_is_a_null_not_a_nan(self, tmp_path):
        """Zero variance in the forward returns makes Spearman UNDEFINED.

        Averaging that NaN in would poison the horizon, and `json.dumps` emits a bare
        `NaN` for it — invalid JSON that a strict reader rejects, i.e. one degenerate
        night could take down the whole nightly artifact. An undefined correlation is a
        missing observation, never a 0.0 correlation.
        """
        idx = _calendar()
        tickers = [f"D{i:02d}" for i in range(WIDE_N)]
        # every name on an IDENTICAL path -> identical forward returns -> zero variance
        flat = pd.DataFrame(
            {t: [100.0 * (1.0 + 0.0005 * s) for s in range(len(idx))] for t in tickers},
            index=idx)
        dates = [str(d.date()) for d in idx[:3]]
        scores = {t: float(10 + 3 * i) for i, t in enumerate(tickers)}
        _write_candidates(tmp_path, _candidate_rows(dates, tuple(tickers), scores))
        upg.run(tmp_path, panel=flat, bench=_bench(idx))

        block = pma.priority_score_scorecard(tmp_path)
        leg = block["by_cohort"]["unsplit"]["21d"]
        assert leg["rank_ic"] is None, "an undefined correlation must be null, never NaN"
        assert leg["n_ic_dates"] == 0 and leg["n_ic_dates_degenerate"] > 0
        assert "zero variance" in leg["null_reason"]

        # the whole block must survive a STRICT json round-trip
        text = json.dumps(block, allow_nan=False, default=str)
        assert "NaN" not in text and "Infinity" not in text
        json.loads(text)

    def test_the_prereg_reaches_the_artifact(self, two_month_store):
        """The map has to be IN the nightly artifact — a prereg nobody can read later is
        not a prereg."""
        _run(two_month_store)
        block = pma.priority_score_scorecard(two_month_store["root"])
        assert block["chartered_horizon"] == upg.CHARTERED_HORIZON
        assert block["horizon_ladder"] == list(upg.HORIZONS)
        note = block["chartered_horizon_note"]
        assert "PRE-REGISTERED" in note and "flatters" in note


# --------------------------------------------------------------------------- #
# 8. zero-authority fence
# --------------------------------------------------------------------------- #

class TestZeroAuthorityFence:

    def test_only_the_cli_and_the_miss_audit_import_the_grader(self):
        allowed = {
            "scripts/grade_us_prophet_candidates.py",
            "engine/us_prophet_grades.py",
            "engine/prophet_miss_audit.py",
            "tests/test_us_prophet_grades.py",
            # PR-3C: W3 ledger joins the existing grade store as the ONE shared
            # outcome ruler. Zero rank/gate/featured/plan authority.
            "engine/us_prophet_w3.py",
            "scripts/accrue_us_prophet_w3.py",
            "scripts/report_us_prophet_w3.py",
            "tests/test_us_prophet_w3.py",
            # PR-1a (WS:PROPHET-CONDITIONAL-FUSION): the arena LABEL builder reads
            # grades as OUTCOMES, never as features — research-tier, zero authority,
            # no rank/gate/size/board/plan path.  The backing is mechanical, not
            # prose: research/prophet_fusion/families.yml carries a
            # `label_only_stores` declaration naming this store, and
            # tests/test_prophet_fusion_families.py::TestLabelOnlyStores reds if
            # the declaration disappears OR if any family member ever claims a
            # grades column as evidence.  The anti-fork law is WHY the builder
            # must import the reader rather than re-glob the parts; the fence's
            # meaning is unchanged: any NEW importer outside this read-only
            # outcome-consumer class still fails here by name.
            "scripts/prophet_fusion_labels.py",
        }
        offenders = []
        for folder in ("engine", "scripts", "app", "admin", "lib", "collectors"):
            base = REPO / folder
            if not base.exists():
                continue
            for path in base.rglob("*.py"):
                rel = path.relative_to(REPO).as_posix()
                if rel in allowed:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "us_prophet_grades" in text:
                    offenders.append(rel)
        assert not offenders, (
            "the grade store is ZERO AUTHORITY — no rank/gate/size/board/plan consumer. "
            f"Unexpected importers: {offenders}")

    def test_the_store_path_is_a_sibling_of_the_candidates_it_grades(self):
        assert upg.STORE_DIR == ucv.STORE_DIR
        assert upg.STORE_SUBDIR == "grades" and ucv.STORE_SUBDIR == "candidates"


# --------------------------------------------------------------------------- #
# 9. DAG conformance
# --------------------------------------------------------------------------- #

class TestDagWiring:

    def test_the_nightly_step_is_declared_and_ordered(self):
        """Declared in the OFF-ENGINE lane, after the stamp and before the miss-audit.

        Moved out of the engine job 2026-08-06 (that job is chronically at its 200m cap and
        a cancel skips its commit, discarding the night's accrual). The two ordering facts
        are unchanged, they are just enforced across jobs now: build_stock_library (called
        at runtime by build_site, per config/dag.yml's own note on scripts.build_site) still
        stamps tonight's candidate rows FIRST — the engine job COMMITS them and this job
        `needs` it — and the miss-audit, whose priority_score_scorecard reads this store,
        still runs after within the new lane.
        """
        import yaml
        dag = yaml.safe_load((REPO / "config" / "dag.yml").read_text())

        def _lane(job):
            return next(l for l in dag["lanes"]
                        if l["workflow"] == ".github/workflows/daily.yml"
                        and l["job"] == job)

        engine = [s.get("module") for s in _lane("engine")["steps"]]
        assert "scripts.grade_us_prophet_candidates" not in engine, (
            "the grader is off the engine job's critical path — a step re-added there "
            "rides the cancel that discards the night")
        assert "scripts.build_site" in engine, "the stamping builder must stay in engine"

        lane = _lane("us_prophet_ledgers")
        modules = [s.get("module") for s in lane["steps"]]
        assert "scripts.grade_us_prophet_candidates" in modules
        assert (modules.index("scripts.grade_us_prophet_candidates")
                < modules.index("scripts.run_prophet_miss_audit")), (
            "the miss-audit's scorecard reads this store, so the grader must run first")

        daily = yaml.safe_load((REPO / ".github/workflows/daily.yml").read_text())
        needs = daily["jobs"]["us_prophet_ledgers"]["needs"]
        assert "engine" in needs, (
            "the grader reads data/us_prophet_rank/candidates, which the engine job's "
            "'commit engine outputs' step is what lands on main")

    def test_the_workflow_invokes_it_with_the_nightly_flag(self):
        # Read through the extraction seam: this step's body is inline today, but a
        # later 512KB-cap diet that moves it to scripts/ci/ would otherwise red this
        # assertion for a reason that has nothing to do with the nightly flag.
        from scripts.workflow_run_source import resolved_workflow_text

        text = resolved_workflow_text(
            REPO / ".github" / "workflows" / "daily.yml", REPO
        )
        assert "python -m scripts.grade_us_prophet_candidates --nightly" in text
