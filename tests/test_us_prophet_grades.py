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
from pathlib import Path

import pandas as pd
import pytest

from engine import prophet_miss_audit as pma
from engine import us_context_vector as ucv
from engine import us_prophet_grades as upg

REPO = Path(__file__).resolve().parents[1]

BOARD_DEF = "us_prophet_v1"
SESSIONS = 90


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
                    scores: dict[str, float] | None = None) -> list[dict]:
    scores = scores or {"AAA": 88.0, "BBB": 41.0, "CCC": 65.0}
    return [
        {
            "stamp_date": d, "ticker": t, "board_definition": BOARD_DEF,
            "lane": "buy", "sector": "Information Technology",
            "eligible": True, "prophet_score": scores.get(t),
            "prophet_signal": 0.8, "prophet_edge": 0.5,
        }
        for d in dates for t in tickers
    ]


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
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(upg._store_dir(root).glob("*.parquet"))}


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

    def test_part_is_keyed_by_the_grading_run_month_not_the_stamp_month(
            self, two_month_store):
        """Run-month partitioning is what makes closed parts permanent: a June stamp graded
        in an August run belongs to August's part, so June's part is never reopened."""
        doc = _run(two_month_store)
        parts = sorted(p.name for p in
                       upg._store_dir(two_month_store["root"]).glob("*.parquet"))
        run_month = str(doc["graded_asof"])[:7]
        assert parts == [f"{run_month}.parquet"]
        stamped = upg.load_grades(two_month_store["root"])["stamp_date"]
        assert {str(s)[:7] for s in stamped} - {run_month}, (
            "the fixture must grade at least one stamp month other than the run month, "
            "or this test cannot see the difference between the two keyings")

    def test_earlier_parts_stay_byte_identical(self, two_month_store):
        """A later run must not rewrite a single byte of any earlier part."""
        idx = _calendar()
        root = two_month_store["root"]
        # first run on a SHORT panel: only the earliest stamps have matured
        short = two_month_store["panel"].iloc[: 4 + max(upg.HORIZONS) + 2]
        upg.run(root, panel=short, bench=two_month_store["bench"].iloc[:len(short)])
        first_parts = _part_digests(root)
        assert first_parts, "the short run must have written a part"

        # second run on the FULL panel, from a later month — new rows, new part
        full = two_month_store["panel"]
        assert str(full.index[-1].date())[:7] != str(short.index[-1].date())[:7], (
            "the two runs must land in different months or the isolation claim is untested")
        upg.run(root, panel=full, bench=two_month_store["bench"])

        after = _part_digests(root)
        for name, digest in first_parts.items():
            assert after[name] == digest, f"part {name} was rewritten by a later run"
        assert len(after) > len(first_parts), "the later run must have opened its own part"
        assert idx is not None

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
        sets of numbers under the name 'excess vs SPY'."""
        from scripts import grade_prophet_doors as gpd

        idx = _calendar()
        close, bench = _panel(idx)["AAA"], _bench(idx)
        stamp = str(idx[3].date())

        mine = upg.grade_row(close, bench, stamp, upg.HORIZONS)
        theirs = gpd.grade_flag(close, bench, stamp, upg.HORIZONS)

        assert set(mine) == set(theirs) and mine, "both must mature the same horizons"
        for horizon in mine:
            for field in ("entry_price", "fill_date", "mark_date", "fwd_ret",
                          "bench_ret", "excess_spy", "fwd_mfe", "fwd_mdd"):
                assert mine[horizon][field] == theirs[horizon][field], (
                    f"H={horizon} field {field} drifted from the doors grader")

    def test_benchmark_and_horizons_match_the_doors_grader(self):
        from scripts import grade_prophet_doors as gpd
        assert upg.BENCH == gpd.BENCH
        assert upg.HORIZONS == gpd.HORIZONS


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
        assert "by_horizon" not in block or not block["by_horizon"]

    def test_populated_store_reports_every_required_leg(self, two_month_store):
        _run(two_month_store)
        block = pma.priority_score_scorecard(two_month_store["root"])
        assert block["available"] is True
        assert block["authority"].startswith("none")
        for horizon in ("10d", "21d"):
            leg = block["by_horizon"][horizon]
            assert set(leg) >= {"horizon_d", "n_graded", "n_scored", "rank_ic",
                                "precision_at_k", "deciles", "population"}
            # every null carries a reason; no statistic is asserted from nothing
            if leg["rank_ic"] is None:
                assert leg.get("null_reason")

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
        leg = pma.priority_score_scorecard(two_month_store["root"])["by_horizon"]["10d"]
        assert leg["rank_ic"] is None
        assert "5+ distinct" in leg["null_reason"]
        assert leg["thin"] is True

    def test_thin_cohorts_are_marked_thin(self, wide_store):
        _run(wide_store)
        leg = pma.priority_score_scorecard(wide_store["root"])["by_horizon"]["10d"]
        assert leg["rank_ic"] is not None, "the wide fixture must reach the measured path"
        assert leg["thin"] is True, (
            "three stamp dates must read as a sample, not a measurement")
        assert leg.get("thin_reason") and "disclosure floor" in leg["thin_reason"]

    def test_a_perfect_score_recovers_a_positive_rank_ic_and_decile_lift(self, wide_store):
        """The arithmetic against a known answer: the fixture's score ranks the forward
        outcome exactly, so a scrambled join or an inverted decile cut fails here."""
        _run(wide_store)
        leg = pma.priority_score_scorecard(wide_store["root"])["by_horizon"]["21d"]
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
        leg = pma.priority_score_scorecard(wide_store["root"])["by_horizon"]["21d"]
        assert "FULL-population median" in leg["precision_at_k"]["definition"]
        assert "FULL graded population" in leg["deciles"]["definition"]

    def test_lane_breakdown_needs_its_own_floor(self, wide_store):
        _run(wide_store)
        pop = pma.priority_score_scorecard(
            wide_store["root"])["by_horizon"]["21d"]["population"]
        assert pop["n"] == WIDE_N * 3
        assert pop["by_lane"]["buy"]["n"] == WIDE_N * 3
        assert pop["mean_excess"] is not None and pop["pos_rate"] is not None

    def test_population_leg_counts_the_whole_graded_universe(self, two_month_store):
        """The 'more data to train on' half: the population block must be sized by every
        graded row, not by the scored subset."""
        _run(two_month_store)
        block = pma.priority_score_scorecard(two_month_store["root"])
        leg = block["by_horizon"]["21d"]
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
        for horizon in pma.PRIORITY_HORIZONS:
            assert f"priority_rank_ic_{horizon}d" in row
            assert f"priority_pop_n_{horizon}d" in row

    def test_row_fields_are_null_safe_on_a_document_with_no_block(self):
        row = pma.priority_score_row_fields({})
        assert row["priority_score_available"] is False
        assert row["priority_score_n_rows"] is None


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
        import yaml
        dag = yaml.safe_load((REPO / "config" / "dag.yml").read_text())
        lane = next(l for l in dag["lanes"]
                    if l["workflow"] == ".github/workflows/daily.yml"
                    and l["job"] == "engine")
        modules = [s.get("module") for s in lane["steps"]]
        assert "scripts.grade_us_prophet_candidates" in modules
        # build_stock_library — which stamps tonight's candidate rows — is called at runtime
        # by build_site rather than declared as its own step (config/dag.yml's own note on
        # scripts.build_site says so), so build_site is what the ordering must clear.
        assert (modules.index("scripts.grade_us_prophet_candidates")
                > modules.index("scripts.build_site")), (
            "the grader must run AFTER the builder that stamps tonight's candidate rows")
        assert (modules.index("scripts.grade_us_prophet_candidates")
                < modules.index("scripts.run_prophet_miss_audit")), (
            "the miss-audit's scorecard reads this store, so the grader must run first")

    def test_the_workflow_invokes_it_with_the_nightly_flag(self):
        text = (REPO / ".github" / "workflows" / "daily.yml").read_text()
        assert "python -m scripts.grade_us_prophet_candidates --nightly" in text
