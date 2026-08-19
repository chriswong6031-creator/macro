"""The C1 fusion ranker and the retired v2 shadow — the 2026-08-15 Chairman override.

The suite is organised around the four claims the override rests on, because each one
is a place a plausible-looking implementation could be quietly wrong:

  1. THE PORT IS AN EXTRACTION.  `engine.us_prophet_fusion.aggregate` reproduces
     `scripts.prophet_fusion_race.build_c1` on the frozen research frame.  Without this
     the "deterministic C1 already specified by the workstream" is just a new model
     wearing C1's name.
  2. THE INPUTS ARE THE SAME INPUTS.  `extract_members` reads each member off a live
     board row exactly as `grade_us_board._row_features` reads it into the graded frame.
     Exact arithmetic over drifted inputs is the subtler half of the same mistake.
  3. THE FREEZE HELD.  `legacy_v2_values` reproduces scores the board actually
     PUBLISHED, byte-exact, on the committed artifact.
  4. THE SHADOW HAS NO AUTHORITY, AND A DEGRADED NIGHT SAYS SO.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import us_board_rank as ubr
from engine import us_prophet_fusion as fus

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "site" / "factordata" / "us_standouts.json"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _row(ticker, *, alpha=1.0, off_high=-5.0, tier="T2", status="buy_now",
         sue_z=None, sue_fresh_days=None, smartmoney=False, insiders=0,
         gex="neutral", news=0, ext_z=0.5, **extra):
    row = {
        "ticker": ticker,
        "alpha": alpha,
        "off_high": off_high,
        "signal": {"tier_cascade": tier, "ticks": 1, "tier": tier},
        "entry_signal": {"status": status},
        "smartmoney_chip": smartmoney,
        "insider_buyers": insiders,
        "gex_confirm": {"verdict": gex},
        "news_burst": {"n_recent": news},
        "ext_z": ext_z,
        "label": "BUY ZONE",
    }
    if sue_z is not None:
        row["sue_z"] = sue_z
        row["sue_fresh_days"] = sue_fresh_days if sue_fresh_days is not None else 10
    row.update(extra)
    return row


@pytest.fixture(scope="module")
def committed_board():
    if not BOARD.exists():
        pytest.skip("committed board artifact not present")
    return json.loads(BOARD.read_text())


# --------------------------------------------------------------------------- #
# 1. the port is an extraction
# --------------------------------------------------------------------------- #

@pytest.mark.needs_full_checkout("data")
class TestByteParityWithTheRacedC1:
    """`aggregate` IS `build_c1`, proven on the frame the race was run on.

    THE WHOLE OVERRIDE RESTS HERE.  The commissioning says to port "the exact
    deterministic C1-as-raced family aggregation", and the only way to show a port is
    exact is to run both and compare, not to read both and agree.  The research module
    is imported by this TEST and by nothing in `engine/` — that boundary is the point of
    the extraction, and `TestProductionNeverImportsResearch` below pins it.

    The floors are evaluated over the WHOLE frame here, because that is what PR-1b's
    race did.  Production evaluates the same code over one night; see
    `TestAsOfNightFloors`.
    """

    @pytest.fixture(scope="class")
    def raced(self):
        pytest.importorskip("pandas")
        try:
            from scripts import prophet_fusion_race as race
        except Exception as exc:                          # pragma: no cover
            pytest.skip(f"race harness unavailable: {exc}")
        try:
            frame = race.build_race_frame()
        except Exception as exc:                          # pragma: no cover
            pytest.skip(f"graded board frame unavailable: {exc}")
        return race, frame, race.build_c1(frame, race.load_registry())

    @staticmethod
    def _rows(frame):
        import numpy as np

        cols = sorted(fus.REGISTERED_SIGNS)
        out = []
        for _, r in frame.features.iterrows():
            values = {}
            for c in cols:
                v = r[c] if c in frame.features.columns else None
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    v = None
                values[c] = v
            out.append((str(r["date"]), values))
        return out

    def test_the_same_members_survive_the_same_floor(self, raced):
        _race, frame, c1 = raced
        admitted = fus.admit_members(self._rows(frame), apply_variance_floor=False)
        assert set(admitted.admitted) == {
            m["column"] for m in c1.membership["members_raced"]}
        assert {d["column"] for d in admitted.dropped} == {
            d["column"] for d in c1.membership["members_dropped"]}

    def test_the_same_families_vote(self, raced):
        _race, frame, c1 = raced
        rows = self._rows(frame)
        admitted = fus.admit_members(rows, apply_variance_floor=False)
        one_date = [v for d, v in rows if d == rows[0][0]]
        plane = fus.aggregate(one_date, admitted.admitted)
        assert plane.families_present == c1.membership["families_present"]

    def test_every_family_score_and_every_c1_score_matches(self, raced):
        """Per ROW, not per aggregate — an aggregate can match while rows disagree."""
        import numpy as np

        _race, frame, c1 = raced
        rows = self._rows(frame)
        admitted = fus.admit_members(rows, apply_variance_floor=False)

        by_date: dict[str, list[tuple[int, dict]]] = {}
        for i, (date, values) in enumerate(rows):
            by_date.setdefault(date, []).append((i, values))

        scores: list[float | None] = [None] * len(rows)
        fams: list[dict] = [{}] * len(rows)
        for _date, items in by_date.items():
            plane = fus.aggregate([v for _i, v in items], admitted.admitted)
            for slot, (i, _v) in enumerate(items):
                scores[i] = plane.scores[slot]
                fams[i] = plane.family_scores[slot]

        raced_scores = c1.rung.scores.reset_index(drop=True)
        raced_fams = c1.family_scores.reset_index(drop=True)
        assert len(raced_scores) == len(rows)

        worst_score, worst_family = 0.0, 0.0
        for i in range(len(rows)):
            a = raced_scores.loc[i, "score"]
            a_null = a is None or (isinstance(a, float) and np.isnan(a))
            assert a_null == (scores[i] is None), f"null disagreement at row {i}"
            if not a_null:
                # x100 is the production SCALE, not a change to the construction.
                worst_score = max(worst_score, abs(float(a) * 100.0 - scores[i]))
            for family in c1.membership["families_present"]:
                b = raced_fams.loc[i, family]
                b_null = b is None or (isinstance(b, float) and np.isnan(b))
                assert b_null == (family not in fams[i]), (family, i)
                if not b_null:
                    worst_family = max(worst_family, abs(float(b) - fams[i][family]))

        # Float ASSOCIATIVITY only: pandas sums a column, this sums a list.  Anything
        # above ~1e-9 is a construction difference, not a rounding one.
        assert worst_family < 1e-12, worst_family
        assert worst_score < 1e-10, worst_score


class TestProductionNeverImportsResearch:
    def test_the_engine_module_imports_nothing_from_scripts_or_research(self):
        """The nightly may not depend on a research harness — the reason the port
        exists at all.  Read as TEXT rather than by import so a lazily-imported name
        inside a function body cannot slip past."""
        source = (ROOT / "engine" / "us_prophet_fusion.py").read_text()
        for banned in ("from scripts", "import scripts", "from research",
                       "import research", "prophet_fusion_race", "prophet_fusion_arena"):
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith(("#", '"', "'")) or "``" in line:
                    continue                       # prose citing the provenance is fine
                assert banned not in stripped, f"{banned!r} in: {line}"


# --------------------------------------------------------------------------- #
# 2. the inputs are the same inputs
# --------------------------------------------------------------------------- #

class TestExtractionMirrorsTheGradedFrame:
    """`extract_members` reads what `grade_us_board._row_features` reads.

    A drift here is invisible to every parity test above — the arithmetic would stay
    exact while the numbers going into it came from somewhere else.
    """

    @pytest.fixture(scope="class")
    def graded(self):
        pytest.importorskip("pandas")
        try:
            from scripts import grade_us_board
        except Exception as exc:                          # pragma: no cover
            pytest.skip(f"grader unavailable: {exc}")
        return grade_us_board

    @pytest.mark.parametrize("row", [
        _row("A", sue_z=1.5, sue_fresh_days=10, smartmoney=True, insiders=3,
             gex="confirm", news=5),
        _row("B", alpha=None, off_high=None, tier=None, sue_z=None,
             smartmoney=False, insiders=1, gex=None, news=2),
        _row("C", sue_z=1.5, sue_fresh_days=90, insiders=2, gex="caution", news=3),
        {"ticker": "D"},                                   # a bare row: every field absent
    ])
    def test_each_member_matches_the_graders_derivation(self, graded, row):
        mine = fus.extract_members(row, (row.get("signal") or {}))
        theirs = graded._row_features(dict(row)) if hasattr(
            graded, "_row_features") else None
        if theirs is None:                                 # pragma: no cover
            pytest.skip("_row_features is not exposed")
        for column in ("alpha", "off_high", "tier_cascade", "sue_fresh",
                       "smartmoney_add", "insider_cluster", "gex_confirm_verdict",
                       "news_burst"):
            assert mine[column] == theirs.get(column), column


class TestPercentileSemantics:
    def test_average_ties_and_pct_over_the_non_null_count(self):
        # 3 present values with a tie: ranks 1, 2.5, 2.5 over n=3.
        assert fus.percentile_rank([1.0, 2.0, 2.0]) == pytest.approx(
            [1 / 3, 2.5 / 3, 2.5 / 3])

    def test_nulls_stay_null_and_do_not_enter_the_denominator(self):
        """A missing member ABSTAINS.  Handing it the mid-pool 0.5 would make a
        no-vote indistinguishable from a neutral vote, which is the exact confusion
        the abstention law exists to prevent."""
        out = fus.percentile_rank([1.0, None, 2.0])
        assert out[1] is None
        assert out == pytest.approx([0.5, None, 1.0])      # n == 2, not 3

    def test_all_null_is_all_null_not_all_zero(self):
        assert fus.percentile_rank([None, None]) == [None, None]

    @pytest.mark.needs_full_checkout("data")
    def test_it_matches_pandas_rank_pct_average(self):
        pd = pytest.importorskip("pandas")
        import numpy as np

        values = [3.0, 1.0, None, 1.0, 7.5, None, 0.0]
        expect = pd.Series([np.nan if v is None else v for v in values]).rank(
            pct=True, method="average")
        got = fus.percentile_rank(values)
        for i, v in enumerate(got):
            if v is None:
                assert bool(np.isnan(expect[i]))
            else:
                assert v == pytest.approx(float(expect[i]))


class TestOrientation:
    def test_an_unmapped_token_is_unmeasured_not_a_zero(self):
        """`gex_confirm` has no 'infirm' value.  A vocabulary miss must abstain — a
        zero would be a NEUTRAL vote cast on the strength of a producer typo."""
        sign = fus.REGISTERED_SIGNS["gex_confirm_verdict"]
        assert fus.oriented_value("infirm", sign) is None
        assert fus.oriented_value("neutral", sign) == 0.0
        assert fus.oriented_value("caution", sign) == -1.0

    def test_a_bool_on_a_continuous_member_is_not_one_point_zero(self):
        assert fus.oriented_value(True, fus.REGISTERED_SIGNS["alpha"]) is None

    def test_tier_reads_the_gates_cascade_order(self):
        sign = fus.REGISTERED_SIGNS["tier_cascade"]
        order = [fus.oriented_value(t, sign) for t in ("T2", "T1", "T3", "T4")]
        assert order == sorted(order, reverse=True), "T2 > T1 > T3 > T4"


# --------------------------------------------------------------------------- #
# the floors, evaluated AS OF NIGHT
# --------------------------------------------------------------------------- #

class TestAsOfNightFloors:
    def test_a_constant_member_is_vote_inert_even_at_full_presence(self):
        """The whole point of the variance axis: presence 100%, information 0.

        This is the shape PR-1b measured and could not act on — a column present on
        every row whose within-date percentile is a constant.  A presence floor admits
        it; the variance floor stands it down and SAYS SO.
        """
        rows = [{"flag": True}, {"flag": True}, {"flag": True}]
        sign = fus.RegisteredSign(column="flag", family="F8_ATTENTION_CROWDING",
                                  sign=+1, kind="flag", source="test")
        out = fus.admit_members([("n", r) for r in rows], signs={"flag": sign})
        assert out.admitted == ()
        (drop,) = out.dropped
        assert drop["reason"] == "vote_inert"
        assert drop["coverage"] == 1.0

    def test_a_sparse_but_variable_member_passes(self):
        """The registered acceptance test: an event flag firing on a few percent of
        rows is sparse, not inert, and must keep its vote."""
        rows = [{"flag": i == 0} for i in range(40)]
        sign = fus.RegisteredSign(column="flag", family="F8_ATTENTION_CROWDING",
                                  sign=+1, kind="flag", source="test")
        out = fus.admit_members([("n", r) for r in rows], signs={"flag": sign})
        assert out.admitted == ("flag",)

    def test_a_single_row_pool_does_not_manufacture_inertness(self):
        """A pool of one cannot carry variation for ANY member.  Counting that as a
        failed date would refuse the whole plane and stamp a legitimately tiny board
        as a degraded one — an outage invented out of a small board."""
        sign = fus.RegisteredSign(column="flag", family="F8_ATTENTION_CROWDING",
                                  sign=+1, kind="flag", source="test")
        out = fus.admit_members([("n", {"flag": True})], signs={"flag": sign})
        assert out.admitted == ("flag",)

    def test_the_presence_floor_is_measured_on_tonight_not_on_history(self):
        """`tier_cascade` sat at 0.25 coverage over the frozen 24-date frame and drops
        there; on a live buy pool every row carries a cascade verdict and it votes.
        Same code, same threshold, different frame — which is the entire prospective
        fix (#5700 left this unimplemented and PR-3 inherited it)."""
        live = [{"tier_cascade": t} for t in ("T1", "T2", "T3")] * 5
        out = fus.admit_members([("tonight", r) for r in live])
        assert "tier_cascade" in out.admitted
        thin = live + [{"tier_cascade": None}] * 60
        out2 = fus.admit_members([("tonight", r) for r in thin])
        (drop,) = [d for d in out2.dropped if d["column"] == "tier_cascade"]
        assert drop["reason"] == "below_presence_floor"


class TestNullIsNotZero:
    def test_a_row_no_family_can_speak_to_scores_null(self):
        plane = fus.aggregate([{"alpha": 1.0}, {"alpha": 2.0}, {"alpha": None}],
                              ["alpha"])
        assert plane.scores[2] is None
        assert plane.family_scores[2] == {}

    def test_an_absent_family_is_listed_with_a_reason(self):
        plane = fus.aggregate([{"alpha": 1.0}, {"alpha": 2.0}], ["alpha"])
        absent = {f["family"]: f["reason"] for f in plane.families_absent}
        assert "F6_MACRO_REGIME" in absent
        assert "STRUCTURALLY EXCLUDED" in absent["F6_MACRO_REGIME"]
        assert "F4_CATALYST_EVENT" in absent and absent["F4_CATALYST_EVENT"]

    def test_zero_families_refuses_rather_than_returning_zeros(self):
        with pytest.raises(fus.FusionUnavailable):
            fus.aggregate([{"alpha": 1.0}], [])


class TestTheFence:
    @pytest.mark.parametrize("column", sorted(fus.FORBIDDEN_INPUTS))
    def test_a_composite_or_a_count_refuses_by_name(self, column):
        sign = fus.RegisteredSign(column=column, family="F2_MOMENTUM_EXTENSION",
                                  sign=+1, kind="continuous", source="test")
        with pytest.raises(fus.ForbiddenCompositeRefusal):
            fus.aggregate([{column: 1.0}], [column], signs={column: sign})

    def test_no_registered_member_is_a_forbidden_input(self):
        assert not (set(fus.REGISTERED_SIGNS) & fus.FORBIDDEN_INPUTS)

    def test_every_registered_member_homes_in_exactly_one_family(self):
        """One column, one home — a second membership is the anti-double-count budget
        defeated by registration."""
        homes: dict[str, set[str]] = {}
        for column, sign in fus.REGISTERED_SIGNS.items():
            homes.setdefault(column, set()).add(sign.family)
        assert all(len(v) == 1 for v in homes.values())
        assert set(s.family for s in fus.REGISTERED_SIGNS.values()) <= set(
            fus.FAMILY_KEYS)

    def test_duplicate_members_collapse_inside_a_family_instead_of_double_voting(self):
        """Agreement inside a family is ONE fact, not two."""
        a = fus.RegisteredSign(column="a", family="F2_MOMENTUM_EXTENSION", sign=+1,
                               kind="continuous", source="test")
        b = fus.RegisteredSign(column="b", family="F2_MOMENTUM_EXTENSION", sign=+1,
                               kind="continuous", source="test")
        rows = [{"a": 1.0, "b": 10.0}, {"a": 2.0, "b": 20.0}]
        plane = fus.aggregate(rows, ["a", "b"], signs={"a": a, "b": b})
        assert [c["column"] for c in plane.members_collapsed] == ["b"]
        assert plane.members_collapsed[0]["duplicate_of"] == "a"
        # b contributed nothing: the family score is a's percentile alone.
        assert plane.family_scores[1]["F2_MOMENTUM_EXTENSION"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# 3. the freeze held
# --------------------------------------------------------------------------- #

@pytest.mark.needs_full_checkout("site")
class TestLegacyV2ByteParity:
    def test_the_frozen_scorer_reproduces_every_published_score(self, committed_board):
        """Published prophet_shadow scores on the committed v3 board, replayed.

        The board ranks by us_prophet_v3; the retired scorer lives on
        prophet_shadow as us_prophet_v2_shadow. Comparing published prophet.score
        (C1) against the frozen v2 replay is the v2-board contract and fails
        the moment the artifact flips — DAR's published prophet 63.9 vs
        replayed shadow 80.5. If the shadow drifts, the "old" column of every
        before/after comparison is a comparison against nothing — the same
        failure the race harness's own replay gate refuses to emit results
        behind.
        """
        buy = committed_board.get("buy") or []
        assert buy, "fixture must carry a buy lane"
        gate = json.loads(
            (ROOT / "site" / "factordata" / "signal_gate.json").read_text())
        verdicts = gate.get("verdicts") or {}

        rows = [dict(r) for r in buy]
        published = {str(r["ticker"]): float((r.get("prophet_shadow") or {})["score"])
                     for r in buy}
        for r in rows:
            for key in ("prophet", "prophet_shadow", "score_rank", "display_rank",
                        "featured", "featured_blocked_by", "stage"):
                r.pop(key, None)

        scored = ubr.score_rows(rows, verdict_by=verdicts,
                                board_asof=committed_board.get("as_of"),
                                bottom_watch_stage=ubr.STAGE_BASING)
        for row in scored:
            replayed = row["prophet_shadow"]["score"]
            assert replayed == pytest.approx(published[str(row["ticker"])], abs=1e-9), (
                row["ticker"])

    def test_the_comparison_script_runs_and_refuses_on_drift(self, committed_board):
        from scripts import us_prophet_fusion_compare as cmp_mod

        report = cmp_mod.compare(top=30)
        assert report["old_definition"] == ubr.SHADOW_DEFINITION == "us_prophet_v2_shadow"
        assert report["new_definition"] == ubr.BOARD_DEFINITION
        assert len(report["new_top"]) == 30
        assert report["fusion_receipt"]["families_active"]
        # Every row carries the receipt the acceptance surface promises.
        for row in report["new_top"]:
            assert row["why"]
            assert row["v2_rank"] and row["new_rank"]
            assert row["n_families"] == len(row["family_contribution"])

    def test_the_comparison_survives_the_board_it_is_run_on_becoming_v3(
            self, committed_board, tmp_path, monkeypatch):
        """The acceptance surface must still work once the board IS the new ranker.

        THE TRAP THIS PINS.  A pre-override `us_prophet_v2` board publishes the
        retired scorer as `prophet.score` and `display_rank` IS that order.  On the
        shipped fusion board neither holds: the published score is C1 and the
        retired scorer has moved to `prophet_shadow`.  Read the wrong block and the
        script fails twice — the freeze check compares a C1 score against a v2 score
        and refuses the buy lane, and `old_rank` becomes the FUSION rank, which would
        compare the new order against itself and report every delta as zero.  The
        tests above now pin the shipped v3 / shadow contract; this one still proves
        the SAME pool produces the SAME comparison when the artifact is re-derived
        as a v3 board.

        The invariant asserted here is the strong one — the SAME pool must produce the
        SAME comparison whichever generation of board it is read from.
        """
        from scripts import us_prophet_fusion_compare as cmp_mod

        gate = json.loads((BOARD.parent / "signal_gate.json").read_text())
        from_v2 = cmp_mod.compare(top=30)

        # Build the artifact the first fusion nightly actually publishes.
        rows = [dict(r) for r in committed_board["buy"]]
        for r in rows:
            for key in ("prophet", "prophet_shadow", "score_rank", "display_rank",
                        "featured", "featured_blocked_by", "stage"):
                r.pop(key, None)
        floors: dict = {}
        scored = ubr.score_rows(rows, verdict_by=gate.get("verdicts") or {},
                                board_asof=committed_board.get("as_of"),
                                bottom_watch_stage=ubr.STAGE_BASING,
                                fusion_floors=floors)
        board_v3 = dict(committed_board)
        board_v3["buy"] = scored
        board_v3["rank_by"] = board_v3["board_definition"] = ubr.published_definition(scored)
        v3_path = tmp_path / "us_standouts.json"
        v3_path.write_text(json.dumps(board_v3))
        monkeypatch.setattr(cmp_mod, "BOARD", v3_path)
        monkeypatch.setattr(cmp_mod, "_REPO", tmp_path)

        from_v3 = cmp_mod.compare(top=30)

        assert from_v3["old_definition"] == ubr.SHADOW_DEFINITION
        assert from_v3["old_rank_basis"] == "prophet_shadow.score_rank"
        assert from_v3["new_definition"] == ubr.BOARD_DEFINITION
        # Not merely "it ran": the deltas must be the real ones, not a wall of zeros.
        assert any(r["rank_change"] for r in from_v3["new_top"])
        assert ({r["ticker"]: r["rank_change"] for r in from_v3["new_top"]}
                == {r["ticker"]: r["rank_change"] for r in from_v2["new_top"]})
        assert from_v3["promoted_into_top"] == from_v2["promoted_into_top"]
        assert from_v3["demoted_out_of_top"] == from_v2["demoted_out_of_top"]
        # The shadow ranks but never features, so there is no retired featured set to
        # differ from — an empty list, never every featured name listed as a change.
        assert from_v3["featured_changed"] == []


# --------------------------------------------------------------------------- #
# 4. the shadow has no authority; a degraded night says so
# --------------------------------------------------------------------------- #

class TestTheBoardRanksByFusion:
    @staticmethod
    def _pool():
        return [
            # BROAD: every family speaks for it, but its alpha is the pool's worst.
            _row("BROAD", alpha=0.1, off_high=-3.0, tier="T2", sue_z=2.0,
                 smartmoney=True, insiders=3, gex="confirm", news=5),
            # NARROW: the retired scorer's favourite — best alpha, nothing else.
            _row("NARROW", alpha=9.0, off_high=-1.0, tier="T2", gex="neutral"),
            _row("MID", alpha=4.0, off_high=-8.0, tier="T1", sue_z=1.0,
                 smartmoney=True, insiders=0, gex="neutral", news=0),
        ]

    def test_the_canonical_score_is_the_fusion_score(self):
        scored = ubr.score_rows(self._pool(), board_asof="2026-08-15")
        for row in scored:
            block = row["prophet"]
            assert block["version"] == ubr.BOARD_DEFINITION == "us_prophet_v3"
            assert block["score_authority"].startswith("C1 evidence-family fusion")
            assert block["fusion"]["families_active"]
            assert block["score"] == pytest.approx(
                sum(block["fusion"]["family_contribution"].values())
                / len(block["fusion"]["family_contribution"]), abs=0.06)

    def test_breadth_of_evidence_can_outrank_the_retired_favourite(self):
        """The behaviour change the override is FOR, shown rather than asserted."""
        scored = ubr.score_rows(self._pool(), board_asof="2026-08-15")
        order = [r["ticker"] for r in scored]
        shadow = sorted(scored, key=lambda r: -r["prophet_shadow"]["score"])
        assert order[0] == "BROAD"
        assert shadow[0]["ticker"] == "NARROW"

    def test_the_sort_key_is_stage_then_fusion_then_ticker(self):
        scored = ubr.score_rows(self._pool(), board_asof="2026-08-15")
        keys = [(ubr.stage_rank(r["stage"]), -(r["prophet"]["score"] or 0.0),
                 r["ticker"]) for r in scored]
        assert keys == sorted(keys)

    def test_an_unscored_row_sorts_after_scored_rows_in_its_bucket(self):
        """Null-last by SAYING so, not by coercing the null to 0.0."""
        pool = self._pool()
        blind = _row("BLIND", alpha=None, off_high=None, tier=None, gex=None)
        blind.pop("news_burst"); blind.pop("smartmoney_chip"); blind.pop("insider_buyers")
        scored = ubr.score_rows(pool + [blind], board_asof="2026-08-15")
        by_stage: dict[str, list] = {}
        for row in scored:
            by_stage.setdefault(row["stage"], []).append(row)
        for bucket in by_stage.values():
            seen_null = False
            for row in bucket:
                if row["prophet"]["score"] is None:
                    seen_null = True
                else:
                    assert not seen_null, "a scored row sorted after an unscored one"

    def test_the_receipt_names_the_abstaining_families(self):
        scored = ubr.score_rows(self._pool(), board_asof="2026-08-15")
        fusion = scored[0]["prophet"]["fusion"]
        assert set(fusion["families_abstaining"]) >= {
            "F3_THEME_STRUCTURE", "F6_MACRO_REGIME", "F7_QUALITY_FUNDAMENTAL"}
        assert not set(fusion["families_abstaining"]) & set(fusion["families_active"])

    def test_the_ranking_block_publishes_the_floors_when_asked(self):
        floors: dict = {}
        scored = ubr.score_rows(self._pool(), board_asof="2026-08-15",
                                fusion_floors=floors)
        block = ubr.ranking_block(scored, fusion_floors=floors)
        assert block["fusion"]["floors"]["captured"] is True
        assert block["fusion"]["shadow_note"]
        assert block["score_kind"] == ubr.FUSION_SCORE_KIND
        json.dumps(block, allow_nan=False)

    def test_the_block_is_honest_when_the_floors_were_not_captured(self):
        scored = ubr.score_rows(self._pool(), board_asof="2026-08-15")
        block = ubr.ranking_block(scored)
        assert block["fusion"]["floors"]["captured"] is False


class TestTheShadowHasNoAuthority:
    @staticmethod
    def _pool():
        return TestTheBoardRanksByFusion._pool()

    def test_it_is_stamped_on_every_row_with_the_shadow_definition(self):
        scored = ubr.score_rows(self._pool(), board_asof="2026-08-15")
        for row in scored:
            assert row["prophet_shadow"]["version"] == ubr.SHADOW_DEFINITION
            assert row["prophet_shadow"]["version"] == "us_prophet_v2_shadow"
            assert "none" in row["prophet_shadow"]["authority"]

    def test_it_carries_its_own_rank_and_that_rank_is_not_the_board_order(self):
        scored = ubr.score_rows(self._pool(), board_asof="2026-08-15")
        board = [r["ticker"] for r in scored]
        shadow = [r["ticker"] for r in
                  sorted(scored, key=lambda r: r["prophet_shadow"]["score_rank"])]
        assert sorted(board) == sorted(shadow)
        assert board != shadow, "fixture must actually disagree or this proves nothing"

    def test_deleting_the_shadow_changes_no_order_no_score_and_no_featured_flag(self):
        """The operational meaning of ZERO AUTHORITY, tested the only way that binds:
        remove it and show nothing downstream moves."""
        with_shadow = ubr.score_rows(self._pool(), board_asof="2026-08-15")
        snapshot = [{k: v for k, v in r.items() if k != "prophet_shadow"}
                    for r in with_shadow]
        again = ubr.score_rows(self._pool(), board_asof="2026-08-15")
        for row in again:
            row.pop("prophet_shadow")
        assert again == snapshot

    def test_the_shadow_never_sets_display_rank(self):
        scored = ubr.score_rows(self._pool(), board_asof="2026-08-15")
        for row in scored:
            assert "display_rank" not in row["prophet_shadow"]


class TestDegradationIsStampedNotHidden:
    def test_a_refused_plane_publishes_the_fallback_definition_and_the_cause(self,
                                                                            monkeypatch):
        def _refuse(*_a, **_k):
            raise fus.FusionUnavailable("no family survived (synthetic)")

        monkeypatch.setattr(fus, "fuse_board", _refuse)
        scored = ubr.score_rows([_row("A"), _row("B", alpha=2.0)],
                                board_asof="2026-08-15")
        for row in scored:
            block = row["prophet"]
            assert block["version"] == ubr.FALLBACK_DEFINITION
            assert block["version"] != ubr.BOARD_DEFINITION
            assert "no family survived" in block["degradation"]["reason"]
            assert block["degradation"]["expected_definition"] == ubr.BOARD_DEFINITION
            assert "fusion" not in block
            assert "prophet_shadow" not in row

    def test_the_artifact_definition_follows_the_rows_not_the_constant(self,
                                                                      monkeypatch):
        """The trap this closes: a builder copying BOARD_DEFINITION into `rank_by`
        would publish an artifact claiming to be a fusion board over rows that say
        otherwise, and every forward ledger keyed on the artifact would pool a
        degraded night with the canonical ones."""
        def _refuse(*_a, **_k):
            raise fus.FusionUnavailable("synthetic")

        monkeypatch.setattr(fus, "fuse_board", _refuse)
        scored = ubr.score_rows([_row("A"), _row("B", alpha=2.0)],
                                board_asof="2026-08-15")
        assert ubr.published_definition(scored) == ubr.FALLBACK_DEFINITION
        assert ubr.ranking_block(scored)["definition"] == ubr.FALLBACK_DEFINITION

    def test_a_mixed_pool_refuses_rather_than_picking_one(self):
        rows = [{"prophet": {"version": "us_prophet_v3"}},
                {"prophet": {"version": "us_prophet_v2_fallback"}}]
        with pytest.raises(ValueError, match="different board definitions"):
            ubr.published_definition(rows)

    def test_the_degradation_stamp_is_still_this_market(self):
        """It must keep the US extension-outage alarm and the US entry provenance —
        a fallback night is this board having a bad night, not a sibling market."""
        assert ubr.is_us_definition(ubr.FALLBACK_DEFINITION)
        assert ubr.FALLBACK_DEFINITION in ubr.EXTENSION_PANEL_MARKETS
        assert not ubr.is_us_definition("hk_prophet_v1")


class TestSiblingBoardsAreUntouched:
    def test_a_non_us_definition_gets_the_retired_scorer_and_no_fusion_block(self):
        """`hk_prophet_v1` delegates this whole pass.  It has no registered members
        wired and must publish exactly what it published before the override."""
        rows = [_row("A", alpha=1.0), _row("B", alpha=2.0)]
        scored = ubr.score_rows(rows, board_asof="2026-08-15",
                                definition="hk_prophet_v1")
        for row in scored:
            assert row["prophet"]["version"] == "hk_prophet_v1"
            assert "fusion" not in row["prophet"]
            assert "prophet_shadow" not in row
            assert set(row["prophet"]["components"]) == set(ubr.SCORE_WEIGHTS)

    def test_the_sibling_score_equals_the_frozen_v2_arithmetic(self):
        rows = [_row("A", alpha=1.0), _row("B", alpha=2.0)]
        scored = ubr.score_rows([dict(r) for r in rows], board_asof="2026-08-15",
                                definition="hk_prophet_v1")
        us = ubr.score_rows([dict(r) for r in rows], board_asof="2026-08-15")
        # MATCHED BY TICKER: the two boards sort on different keys, so a positional
        # zip compares two different names and passes or fails by accident.
        own_by = {r["ticker"]: r for r in us}
        for sib in scored:
            assert (sib["prophet"]["score"]
                    == own_by[sib["ticker"]]["prophet_shadow"]["score"]), sib["ticker"]

    def test_a_sibling_ranking_block_keeps_its_own_definition_and_score_kind(self):
        scored = ubr.score_rows([_row("A")], board_asof="2026-08-15",
                                definition="hk_prophet_v1")
        block = ubr.ranking_block(scored, definition="hk_prophet_v1")
        assert block["definition"] == "hk_prophet_v1"
        assert block["score_kind"] == ubr.SCORE_KIND
        assert block["fusion"] is None


class TestTheEraFence:
    def test_the_displaced_stamp_was_appended_in_the_same_change(self):
        assert "us_prophet_v2" in ubr.SUPERSEDED_ERA_STAMPS
        assert ubr.BOARD_DEFINITION not in ubr.SUPERSEDED_ERA_STAMPS

    def test_the_selection_era_did_not_move(self):
        """A RANK change is not an ADMISSION change.  Bumping the era here would
        restart the H=63 episode clock and re-create the unsatisfiable-gate trap the
        era's own ruling exists to prevent."""
        assert ubr.SELECTION_ERA == "anticipation-v1-2026-08-08"

    def test_no_forecast_or_validation_language_in_the_fusion_copy(self):
        scored = ubr.score_rows(TestTheBoardRanksByFusion._pool(),
                                board_asof="2026-08-15")
        text = json.dumps(ubr.ranking_block(scored)).lower()
        text += json.dumps(scored[0]["prophet"]).lower()
        for banned in ("validated", "win rate", "win-rate", "forecast return",
                       "expected return", "backtested", "proven alpha"):
            assert banned not in text, banned

    def test_the_published_score_kind_refuses_the_alpha_claim(self):
        assert "not a calibrated return forecast" in ubr.FUSION_SCORE_KIND
        assert "not a promoted alpha model" in ubr.FUSION_SCORE_KIND
