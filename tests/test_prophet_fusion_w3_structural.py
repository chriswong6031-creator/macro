"""PR-3B: outcome-blind LOFO + member census. Zero authority.

These tests pin the structural diagnostic path against the ten required
mutations. They never load grades, never compute IC/alpha/returns, and never
touch ``data/us_prophet_rank/w3``.
"""

from __future__ import annotations

import copy
import json

import pytest

from engine import us_board_rank as ubr
from engine import us_prophet_fusion as fus


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


def _live_pool():
    return [
        _row("BROAD", alpha=0.1, off_high=-3.0, tier="T2", sue_z=2.0,
             smartmoney=True, insiders=3, gex="confirm", news=5),
        _row("NARROW", alpha=9.0, off_high=-1.0, tier="T2", gex="neutral"),
        _row("MID", alpha=4.0, off_high=-8.0, tier="T1", sue_z=1.0,
             smartmoney=True, insiders=0, gex="neutral", news=0),
    ]


def _plane(family_scores, *, voting=None, dropped=None, collapsed=None,
           extracted=None, admission=None, families_present=None):
    scores = []
    for families in family_scores:
        present = [value for value in families.values()]
        scores.append(None if not present else (sum(present) / len(present)) * 100.0)
    present_names = families_present if families_present is not None else sorted({
        family for row in family_scores for family in row
    })
    return fus.FusionPlane(
        scores=scores,
        family_scores=family_scores,
        member_percentiles=[{} for _ in family_scores],
        families_present=list(present_names),
        families_absent=[],
        members_voting=list(voting or []),
        members_dropped=list(dropped or []),
        members_collapsed=list(collapsed or []),
        admission=admission,
        extracted_members=tuple(extracted or ()),
    )


def _keys(tickers, stages, ranks=None):
    out = []
    for i, ticker in enumerate(tickers):
        item = {"ticker": ticker, "stage": stages[i]}
        if ranks is not None:
            item["score_rank"] = ranks[i]
        out.append(item)
    return out


# --------------------------------------------------------------------------- #
# 1. high tie-share still shows planted LOFO movement
# --------------------------------------------------------------------------- #

class TestHighTieShareIsNotAUsefulnessProxy:
    def test_a_high_tie_share_family_still_shows_large_planted_lofo_movement(self):
        """38/40 rows share one F1 value (tie-share 0.95); two stars sit at 1.0.

        After ablation every remaining family is flat, so the stars fall from
        rank 1-2 to ticker-last. Tie-share cannot be allowed to hide that.
        """
        pack = [f"A{i:02d}" for i in range(38)]
        stars = ["YYY", "ZZZ"]
        tickers = stars + pack
        stages = ["live"] * 40
        family_scores = []
        for ticker in tickers:
            f1 = 1.0 if ticker in stars else 0.5
            family_scores.append({
                "F1_TECHNICAL_CONFLUENCE": f1,
                "F2_MOMENTUM_EXTENSION": 0.5,
            })
        plane = _plane(family_scores)
        diag = fus.diagnose_structure(_keys(tickers, stages), plane)
        row = {item["family"]: item for item in diag["lofo"]}["F1_TECHNICAL_CONFLUENCE"]
        assert row["tie_share"] == pytest.approx(0.95)
        assert row["tie_share_is_descriptive_only"] is True
        assert row["max_abs_rank_displacement"] >= 30
        assert row["rows_moved"] >= 2


# --------------------------------------------------------------------------- #
# 2. variance-floor eligibility != LOFO usefulness
# --------------------------------------------------------------------------- #

class TestVarianceFloorIsNotLofoUsefulness:
    def test_a_near_constant_event_family_can_pass_the_floor_and_barely_move_ranks(self):
        tickers = [f"T{i:02d}" for i in range(40)]
        stages = ["live"] * 40
        family_scores = []
        extracted = []
        for i, ticker in enumerate(tickers):
            # F2 is the real ranker. F4 fires on one row — two distinct values,
            # so the variance floor would admit it — but removing it barely
            # moves the board.
            family_scores.append({
                "F2_MOMENTUM_EXTENSION": (i + 1) / 40.0,
                "F4_CATALYST_EVENT": 0.5001 if i == 0 else 0.5,
            })
            extracted.append({"alpha": float(i), "sue_fresh": i == 0})
        admission = fus.Admission(
            admitted=("alpha", "sue_fresh"), dropped=(), frame_dates=1, frame_rows=40)
        plane = _plane(
            family_scores,
            voting=[{"column": "alpha"}, {"column": "sue_fresh"}],
            extracted=extracted,
            admission=admission,
        )
        diag = fus.diagnose_structure(_keys(tickers, stages), plane)
        by_family = {item["family"]: item for item in diag["lofo"]}
        by_member = {item["member"]: item for item in diag["census"]}
        assert by_member["sue_fresh"]["status"] == "voting"
        assert by_member["sue_fresh"]["distinct_values"] == 2
        assert by_family["F4_CATALYST_EVENT"]["distinct_values"] == 2
        assert by_family["F4_CATALYST_EVENT"]["mean_abs_rank_displacement"] < 1.0
        assert by_family["F2_MOMENTUM_EXTENSION"]["mean_abs_rank_displacement"] > 5.0


# --------------------------------------------------------------------------- #
# 3. floor recomputation during ablation reds
# --------------------------------------------------------------------------- #

class TestAblationDoesNotRecomputeFloors:
    def test_admit_aggregate_and_percentile_are_not_called_during_lofo(self, monkeypatch):
        tickers = ["A", "B", "C"]
        stages = ["live"] * 3
        plane = _plane([
            {"F1_TECHNICAL_CONFLUENCE": 0.2, "F2_MOMENTUM_EXTENSION": 0.9},
            {"F1_TECHNICAL_CONFLUENCE": 0.5, "F2_MOMENTUM_EXTENSION": 0.4},
            {"F1_TECHNICAL_CONFLUENCE": 0.8, "F2_MOMENTUM_EXTENSION": 0.1},
        ])

        def boom(*_a, **_k):
            raise AssertionError("floors recomputed during ablation")

        monkeypatch.setattr(fus, "admit_members", boom)
        monkeypatch.setattr(fus, "percentile_rank", boom)
        monkeypatch.setattr(fus, "aggregate", boom)
        monkeypatch.setattr(fus, "fuse_board", boom)
        diag = fus.diagnose_structure(_keys(tickers, stages), plane)
        assert diag["canonical_observation"] is True
        assert diag["admitted_frozen"] == []


# --------------------------------------------------------------------------- #
# 4. ignoring stage buckets reds
# --------------------------------------------------------------------------- #

class TestStageBucketsAreLoadBearing:
    def test_ignoring_stage_buckets_reds(self):
        tickers = ["LOWLIVE", "HIGHBLOCK"]
        stages = [ubr.STAGE_LIVE, ubr.STAGE_BLOCKED]
        plane = _plane([
            {"F2_MOMENTUM_EXTENSION": 0.1},
            {"F2_MOMENTUM_EXTENSION": 0.9},
        ])
        diag = fus.diagnose_structure(_keys(tickers, stages), plane)
        # Reconstruct diagnostic order from the same key the function uses.
        scores = [10.0, 90.0]
        keys = [fus.diagnostic_sort_key(stages[i], scores[i], tickers[i])
                for i in range(2)]
        order = [tickers[i] for i in sorted(range(2), key=lambda i: keys[i])]
        score_only = [tickers[i] for i in sorted(
            range(2), key=lambda i: (-scores[i], tickers[i]))]
        assert order[0] == "LOWLIVE"
        assert score_only[0] == "HIGHBLOCK"
        assert diag["full_model_rank_matches_published"] is True


# --------------------------------------------------------------------------- #
# 5. null-as-zero reds
# --------------------------------------------------------------------------- #

class TestNullIsNotZeroInLofo:
    def test_null_as_zero_reds(self):
        tickers = ["AAA", "ZZZ"]
        stages = ["live", "live"]
        plane = _plane([
            {},
            {"F2_MOMENTUM_EXTENSION": 0.0},
        ], families_present=["F2_MOMENTUM_EXTENSION"])
        diag = fus.diagnose_structure(_keys(tickers, stages), plane)
        canonical = [fus.diagnostic_sort_key(stages[i], plane.scores[i], tickers[i])
                     for i in range(2)]
        canonical_order = [tickers[i] for i in sorted(range(2), key=lambda i: canonical[i])]
        coerced = [(-float(plane.scores[i] or 0.0), tickers[i]) for i in range(2)]
        coerced_order = [tickers[i] for i in sorted(range(2), key=lambda i: coerced[i])]
        assert canonical_order == ["ZZZ", "AAA"]
        assert coerced_order == ["AAA", "ZZZ"]
        assert diag["rows_unscored"] == 1
        assert diag["rows_scored"] == 1


# --------------------------------------------------------------------------- #
# 6. degraded / fallback board emits no canonical W3 observation
# --------------------------------------------------------------------------- #

class TestDegradedBoardEmitsNoCanonicalW3:
    def test_a_degraded_board_has_no_fusion_receipt_and_no_w3_block(self, monkeypatch):
        def _refuse(*_a, **_k):
            raise fus.FusionUnavailable("no family survived (synthetic)")

        monkeypatch.setattr(fus, "fuse_board", _refuse)
        floors: dict = {}
        scored = ubr.score_rows([_row("A"), _row("B", alpha=2.0)],
                                board_asof="2026-08-15", fusion_floors=floors)
        block = ubr.ranking_block(scored, fusion_floors=floors)
        assert block["definition"] == ubr.FALLBACK_DEFINITION
        assert block["fusion"] is None
        assert "w3_structural" not in (block.get("fusion") or {})
        assert floors.get("degraded") is True
        assert "w3_structural" not in floors


# --------------------------------------------------------------------------- #
# 7. injected outcome columns cannot affect diagnostics
# --------------------------------------------------------------------------- #

class TestOutcomesCannotAffectDiagnostics:
    def test_injected_outcome_columns_cannot_affect_diagnostics(self):
        tickers = ["A", "B", "C"]
        stages = ["live"] * 3
        plane = _plane([
            {"F2_MOMENTUM_EXTENSION": 0.1},
            {"F2_MOMENTUM_EXTENSION": 0.5},
            {"F2_MOMENTUM_EXTENSION": 0.9},
        ])
        clean = _keys(tickers, stages)
        dirty = []
        for i, item in enumerate(clean):
            dirty.append({
                **item,
                "excess_spy": 99.0 if i == 0 else -99.0,
                "fwd_ret": 12.0,
                "grade": "win",
                "ic": 0.8,
                "leader": "A",
                "alpha_fwd": 3.14,
            })
        a = fus.diagnose_structure(clean, plane)
        b = fus.diagnose_structure(dirty, plane)
        assert a == b


# --------------------------------------------------------------------------- #
# 8. input-row permutation cannot affect diagnostics
# --------------------------------------------------------------------------- #

class TestPermutationInvariance:
    def test_input_row_permutation_cannot_affect_diagnostics(self):
        pool = _live_pool()
        floors_a: dict = {}
        a = ubr.score_rows(copy.deepcopy(pool), board_asof="2026-08-15",
                           fusion_floors=floors_a)
        floors_b: dict = {}
        b = ubr.score_rows(list(reversed(copy.deepcopy(pool))),
                           board_asof="2026-08-15", fusion_floors=floors_b)
        diag_a = floors_a["w3_structural"]
        diag_b = floors_b["w3_structural"]
        assert diag_a["lofo"] == diag_b["lofo"]
        assert diag_a["census"] == diag_b["census"]
        assert [r["ticker"] for r in a] == [r["ticker"] for r in b]


# --------------------------------------------------------------------------- #
# 9. reconstructed full-model order equals published canonical rank
# --------------------------------------------------------------------------- #

class TestFullModelReconstruction:
    def test_reconstructed_full_model_order_equals_published_canonical_rank(self):
        floors: dict = {}
        scored = ubr.score_rows(_live_pool(), board_asof="2026-08-15",
                                fusion_floors=floors)
        diag = floors["w3_structural"]
        assert diag["schema"] == fus.W3_DIAGNOSTICS_SCHEMA
        assert diag["canonical_observation"] is True
        assert diag["full_model_rank_matches_published"] is True
        published = [r["ticker"] for r in scored]
        plane = fus.fuse_board(_live_pool())
        keys = [{
            "ticker": row["ticker"],
            "stage": next(s["stage"] for s in scored if s["ticker"] == row["ticker"]),
            "score_rank": next(s["score_rank"] for s in scored
                               if s["ticker"] == row["ticker"]),
        } for row in _live_pool()]
        recon = fus.diagnose_structure(keys, plane)
        assert recon["full_model_rank_matches_published"] is True
        order = [ticker for ticker, _key in sorted(
            ((keys[i]["ticker"], fus.diagnostic_sort_key(
                keys[i]["stage"], plane.scores[i], keys[i]["ticker"]))
             for i in range(len(keys))),
            key=lambda pair: pair[1])]
        assert order == published


# --------------------------------------------------------------------------- #
# 10. diagnostics cannot mutate canonical score/rank/display/featured/population
# --------------------------------------------------------------------------- #

class TestDiagnosticsHaveZeroAuthority:
    def test_diagnostics_cannot_mutate_canonical_fields(self, monkeypatch):
        with_diag = ubr.score_rows(copy.deepcopy(_live_pool()),
                                   board_asof="2026-08-15")

        def _noop(*_a, **_k):
            return {"schema": "noop", "canonical_observation": True}

        monkeypatch.setattr(fus, "diagnose_structure", _noop)
        without = ubr.score_rows(copy.deepcopy(_live_pool()),
                                 board_asof="2026-08-15")

        def _canon(rows):
            return [{
                "ticker": r["ticker"],
                "score": r["prophet"]["score"],
                "score_rank": r["score_rank"],
                "display_rank": r["display_rank"],
                "featured": r["featured"],
                "version": r["prophet"]["version"],
            } for r in rows]

        assert _canon(with_diag) == _canon(without)
        assert {r["ticker"] for r in with_diag} == {r["ticker"] for r in without}

    def test_diagnose_structure_does_not_write_back_into_the_plane(self):
        family_scores = [
            {"F2_MOMENTUM_EXTENSION": 0.1},
            {"F2_MOMENTUM_EXTENSION": 0.9},
        ]
        plane = _plane(copy.deepcopy(family_scores))
        snapshot_scores = copy.deepcopy(plane.scores)
        snapshot_families = copy.deepcopy(plane.family_scores)
        fus.diagnose_structure(
            _keys(["A", "B"], ["live", "live"]), plane)
        assert plane.scores == snapshot_scores
        assert plane.family_scores == snapshot_families


class TestCensusCoversEveryRegisteredMember:
    def test_every_registered_member_has_a_nightly_structural_row(self):
        floors: dict = {}
        ubr.score_rows(_live_pool(), board_asof="2026-08-15", fusion_floors=floors)
        census = floors["w3_structural"]["census"]
        members = {row["member"] for row in census}
        assert members == set(fus.REGISTERED_SIGNS)
        statuses = {row["status"] for row in census}
        assert statuses <= set(fus.MEMBER_CENSUS_STATUSES)
        required = {"member", "family", "status", "coverage", "distinct_values",
                    "variation_share", "thresholds", "reason", "source",
                    "staleness_basis"}
        for row in census:
            assert required <= set(row)
            assert row["status"] in fus.MEMBER_CENSUS_STATUSES

    def test_statuses_distinguish_voting_inert_presence_collapse_and_absent(self):
        # voting + vote_inert: flags that are all-False are present and constant.
        inert_pool = [
            _row("A", alpha=1.0, off_high=-1.0, tier="T2", gex="confirm"),
            _row("B", alpha=2.0, off_high=-2.0, tier="T1", gex="neutral"),
            _row("C", alpha=3.0, off_high=-3.0, tier="T3", gex="caution"),
        ]
        floors: dict = {}
        ubr.score_rows(inert_pool, board_asof="2026-08-15", fusion_floors=floors)
        by_member = {row["member"]: row for row in floors["w3_structural"]["census"]}
        assert by_member["alpha"]["status"] == "voting"
        assert by_member["insider_cluster"]["status"] == "vote_inert"
        assert by_member["news_burst"]["status"] == "vote_inert"

        # below_presence: a continuous member that is almost entirely null.
        signs = {
            "thin": fus.RegisteredSign(
                column="thin", family="F2_MOMENTUM_EXTENSION", sign=+1,
                kind="continuous", source="test"),
            "wide": fus.RegisteredSign(
                column="wide", family="F2_MOMENTUM_EXTENSION", sign=+1,
                kind="continuous", source="test"),
        }
        rows = [{"thin": None, "wide": float(i)} for i in range(10)]
        rows[0]["thin"] = 1.0
        admission = fus.admit_members([("n", r) for r in rows], signs=signs)
        assert "thin" not in admission.admitted
        plane = fus.aggregate(rows, admission.admitted, signs=signs)
        plane.members_dropped = [dict(d) for d in admission.dropped]
        plane.admission = admission
        plane.extracted_members = tuple(rows)
        diag = fus.diagnose_structure(
            _keys([f"X{i}" for i in range(10)], ["live"] * 10), plane, signs=signs)
        by_member = {row["member"]: row for row in diag["census"]}
        assert by_member["thin"]["status"] == "below_presence"

        # collapsed_duplicate.
        a = fus.RegisteredSign(column="a", family="F2_MOMENTUM_EXTENSION", sign=+1,
                               kind="continuous", source="test")
        b = fus.RegisteredSign(column="b", family="F2_MOMENTUM_EXTENSION", sign=+1,
                               kind="continuous", source="test")
        dup_rows = [{"a": 1.0, "b": 10.0}, {"a": 2.0, "b": 20.0}]
        dup_plane = fus.aggregate(dup_rows, ["a", "b"], signs={"a": a, "b": b})
        dup_plane.extracted_members = tuple(dup_rows)
        dup_plane.admission = fus.Admission(
            admitted=("a", "b"), dropped=(), frame_dates=1, frame_rows=2)
        dup_diag = fus.diagnose_structure(
            _keys(["P", "Q"], ["live", "live"]), dup_plane, signs={"a": a, "b": b})
        by_member = {row["member"]: row for row in dup_diag["census"]}
        assert by_member["b"]["status"] == "collapsed_duplicate"

        # absent: registered but not extracted.
        missing = fus.RegisteredSign(
            column="ghost", family="F8_ATTENTION_CROWDING", sign=+1,
            kind="flag", source="test")
        ghost_plane = fus.aggregate(
            [{"wide": 1.0}, {"wide": 2.0}], ["wide"], signs={"wide": signs["wide"]})
        ghost_plane.extracted_members = ({"wide": 1.0}, {"wide": 2.0})
        ghost_diag = fus.diagnose_structure(
            _keys(["P", "Q"], ["live", "live"]), ghost_plane,
            signs={"wide": signs["wide"], "ghost": missing})
        by_member = {row["member"]: row for row in ghost_diag["census"]}
        assert by_member["ghost"]["status"] == "absent"


class TestReceiptIsCompactAndOutcomeBlind:
    def test_the_canonical_fusion_receipt_carries_the_compact_structural_block(self):
        floors: dict = {}
        scored = ubr.score_rows(_live_pool(), board_asof="2026-08-15",
                                fusion_floors=floors)
        block = ubr.ranking_block(scored, fusion_floors=floors)
        w3 = block["fusion"]["w3_structural"]
        assert w3["schema"] == fus.W3_DIAGNOSTICS_SCHEMA
        assert w3["canonical_observation"] is True
        assert "lofo" in w3 and "census" in w3
        assert "floors" in block["fusion"]
        assert "w3_structural" not in block["fusion"]["floors"]
        json.dumps(block, allow_nan=False)

    def test_no_new_persistent_engine_write_is_introduced(self):
        source = (ubr.__file__, fus.__file__)
        for path in source:
            text = open(path, encoding="utf-8").read()
            assert "data/us_prophet_rank/w3" not in text
            assert "us_prophet_rank/w3" not in text
