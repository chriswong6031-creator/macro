"""The 2026-08-11 outage RECONSTRUCTION lane, and the properties that make it honest.

Companion to ``tests/test_prophet_outage_backfill.py`` (the 2026-08-09 REPLAY).  The two
windows share a disclosure artifact and a segregation law, and the cross-window
assertions live in that older file so there is exactly one place that says "every
stamped plan belongs to an enumerated, authorised window".

What is pinned HERE is what the 2026-08-09 lane never had to prove, because it replayed
a board that existed:

* PRICE TRUNCATION.  The reconstruction tree is built by appending only the sessions the
  stranded collect never wrote, up to the 2026-08-11 close.  A poisoned 2026-08-12 bar —
  one whose price would visibly reorder any downstream reader — must not reach the tree,
  and the fence that re-proves it must actually fire when a bar is planted.  Neuter
  ``truncate_frame`` and these go red; that is the point of them.
* COLLISION.  The 2026-08-12 nightly originated 25 plans live. Live wins, and the
  ticker+DIRECTION key is what decides it.
* CHRONOLOGY.  A plan whose entry trigger the tape had already taken out by the 08-11
  close is an entry nobody could have taken that night, and it is refused with a named
  reason rather than minted and quietly graded.
* VINTAGE.  The lane runs the engine that predates #5370. A tree at any other commit, or
  one that descends from #5370's merge, is refused.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import scripts.backfill_prophet_outage_20260811 as bf11  # noqa: E402

REAL_PLANS_DIR = _REPO / "site" / "prophet" / "plans"
REAL_DISCLOSURES = _REPO / bf11.DISCLOSURES_RELPATH


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _frame(dates: list[str], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": closes, "high": closes, "low": closes,
                         "volume": [1_000] * len(closes)},
                        index=pd.to_datetime(dates))


def _plan(ticker: str, *, entry: float, trigger: float,
          direction: str = "BULL", **extra) -> dict:
    plan = {
        "schema": "prophet.trade_plan/v1",
        "id": f"{ticker}-{direction}-20260805",
        "asset": ticker,
        "direction": direction,
        "recorded_at": bf11.BACKFILL_ASOF,
        "price_basis_date": bf11.BACKFILL_ASOF,
        "entry": entry,
        "trigger": trigger,
        "invalidation": (entry * 0.9) if isinstance(entry, (int, float)) else None,
    }
    plan.update(extra)
    return plan


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# R1 — the truncation is what makes the reconstruction honest
# ---------------------------------------------------------------------------

class TestPriceTruncation:
    """No bar the 2026-08-11 bake could not have seen may reach the tree it reads."""

    def test_truncate_frame_drops_every_bar_after_the_ceiling(self):
        frame = _frame(["2026-08-10", "2026-08-11", "2026-08-12"], [10.0, 11.0, 99.0])
        kept = bf11.truncate_frame(frame, bf11.TRUNCATE_THROUGH)
        assert list(kept.index.strftime("%Y-%m-%d")) == ["2026-08-10", "2026-08-11"]
        assert kept["close"].max() == 11.0

    def test_truncate_frame_keeps_a_bar_exactly_on_the_ceiling(self):
        """The ceiling is the SESSION being reconstructed, not the day before it."""
        frame = _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0])
        assert len(bf11.truncate_frame(frame, bf11.TRUNCATE_THROUGH)) == 2

    def test_a_poisoned_08_12_bar_cannot_reach_the_reconstruction_tree(self, tmp_path):
        """THE lookahead test.

        The live store carries an 08-12 bar at a price no reader could ignore — a 10x
        gap that would move the name's momentum, its extension, its rank and therefore
        its admission. The overlay must add the 08-11 session and stop, so the tree the
        board builder reads cannot contain the number at all: not filtered downstream,
        not weighted to zero, ABSENT.
        """
        vintage = _frame(["2026-08-07", "2026-08-10"], [10.0, 10.5])
        live = _frame(["2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12"],
                      [10.0, 10.5, 11.0, 110.0])

        merged, provenance = bf11.overlay_sessions(vintage, live,
                                                   bf11.TRUNCATE_THROUGH)

        assert provenance["added"] == ["2026-08-11"]
        assert list(merged.index.strftime("%Y-%m-%d")) == [
            "2026-08-07", "2026-08-10", "2026-08-11"]
        assert 110.0 not in set(merged["close"]), (
            "the 2026-08-12 close reached the reconstruction tree — every price the "
            "board ranks on would then carry a session the 2026-08-11 bake could not "
            "have seen"
        )
        assert merged["close"].max() == 11.0

    def test_the_overlay_keeps_the_vintage_rows_and_only_appends(self, tmp_path):
        """A later restatement of old history must not leak backwards into that night.

        The live store's 2026-08-10 close has been restated (a re-fetch, an adjustment,
        a widened seeing set). The reconstruction is of a night that read the OLD value,
        so the old value is what it must keep.
        """
        vintage = _frame(["2026-08-10"], [10.5])
        live = _frame(["2026-08-10", "2026-08-11"], [10.9, 11.0])

        merged, _ = bf11.overlay_sessions(vintage, live, bf11.TRUNCATE_THROUGH)

        assert merged.loc[pd.Timestamp("2026-08-10"), "close"] == 10.5
        assert merged.loc[pd.Timestamp("2026-08-11"), "close"] == 11.0

    def test_the_fence_fires_on_a_planted_bar(self, tmp_path):
        """The structural claim is re-measured, not asserted."""
        store = tmp_path / "data" / "stocks"
        store.mkdir(parents=True)
        _frame(["2026-08-11", "2026-08-12"], [11.0, 12.0]).to_parquet(
            store / "AAA.parquet")

        with pytest.raises(bf11.BackfillRefused, match="carry bars AFTER"):
            bf11.fence_no_bar_after(tmp_path, bf11.TRUNCATE_THROUGH)

    def test_the_fence_passes_a_clean_tree_and_says_what_it_scanned(self, tmp_path):
        store = tmp_path / "data" / "stocks"
        store.mkdir(parents=True)
        _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0]).to_parquet(
            store / "AAA.parquet")

        report = bf11.fence_no_bar_after(tmp_path, bf11.TRUNCATE_THROUGH)

        assert report["violations"] == 0
        assert report["files_scanned"] == 1
        assert report["max_date_found"] == "2026-08-11"

    def test_the_fence_is_not_vacuous_when_nothing_is_there(self, tmp_path):
        """Guard the guard: a tree with no price files scans nothing and says so."""
        assert bf11.fence_no_bar_after(tmp_path, bf11.TRUNCATE_THROUGH)[
            "files_scanned"] == 0

    def test_a_round_the_clock_bar_ahead_of_the_control_pass_is_reported_not_refused(
            self, tmp_path):
        """FX and crypto trade past the equity close; the vintage really did hold those.

        The control pass truncates to 2026-08-10, but the pinned tree already ships 13
        files dated 2026-08-11 — FX crosses and crypto. Calling those lookahead would
        be calling the bake's own inputs lookahead. They are reported.
        """
        store = tmp_path / "data" / "yahoo"
        store.mkdir(parents=True)
        _frame(["2026-08-10", "2026-08-11"], [1.0, 1.1]).to_parquet(
            store / "EURUSD_X.parquet")

        report = bf11.fence_no_bar_after(tmp_path, bf11.TRUNCATE_THROUGH,
                                         pass_through=bf11.CONTROL_THROUGH)

        assert report["violations"] == 0
        assert report["ahead_of_pass_count"] == 1
        assert report["ahead_of_pass"][0]["max_date"] == "2026-08-11"

    def test_a_file_already_past_the_pass_ceiling_is_rewritten_not_left_alone(self):
        """Truncation is a reason to write, not only appending is.

        Found in flight: the Russell close panel is gitignored, so the git restore
        between passes does not reach it, and it carried a 2026-08-11 row into a
        2026-08-10 control pass. The overlay computed the right frame and then declined
        to write it because nothing had been APPENDED.
        """
        on_disk = _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0])
        live = _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0])
        merged, provenance = bf11.overlay_sessions(on_disk, live,
                                                   bf11.CONTROL_THROUGH)

        assert provenance["added_sessions"] == 0
        assert len(merged) == 1
        assert bf11._needs_write(merged, on_disk, provenance) is True, (
            "the truncated frame would not have been written back"
        )

    def test_an_unchanged_file_is_not_rewritten(self):
        """Guard the guard: the write condition must still be able to say no."""
        on_disk = _frame(["2026-08-10"], [10.0])
        merged, provenance = bf11.overlay_sessions(on_disk, on_disk,
                                                   bf11.CONTROL_THROUGH)
        assert bf11._needs_write(merged, on_disk, provenance) is False

    def test_a_date_in_a_column_frame_is_not_read_as_epoch_nanoseconds(self):
        """The silent-no-op shape: dates in a column, a RangeIndex on the frame.

        `pd.to_datetime(RangeIndex)` SUCCEEDS — 0, 1, 2 become 1970 — so a naive
        conversion keeps every row, writes a fake index back over a real one, and lets
        the fence report "max 1970" and pass. prophet_bridge._load_price_history handles
        this shape explicitly, so it is not hypothetical.
        """
        frame = pd.DataFrame({"date": pd.to_datetime(
            ["2026-08-10", "2026-08-11", "2026-08-12"]), "close": [10.0, 11.0, 99.0]})
        kept = bf11.truncate_frame(frame, bf11.TRUNCATE_THROUGH)
        assert len(kept) == 2, "the 2026-08-12 row survived a truncation"
        assert 99.0 not in set(kept["close"])

    def test_a_frame_with_no_readable_dates_is_left_alone_and_flagged(self, tmp_path):
        """Not truncatable and not silently rewritten — the fence names it instead."""
        frame = pd.DataFrame({"close": [1.0, 2.0]})
        assert bf11.truncate_frame(frame, bf11.TRUNCATE_THROUGH) is frame

        store = tmp_path / "data" / "stocks"
        store.mkdir(parents=True)
        frame.to_parquet(store / "AAA.parquet")
        report = bf11.fence_no_bar_after(tmp_path, bf11.TRUNCATE_THROUGH)
        assert report["unscannable_count"] == 1, (
            "'I could not look' was counted as 'I looked and saw nothing later'"
        )

    def test_several_missing_sessions_are_all_appended(self):
        """A name whose vintage series is stale gets every session up to the ceiling."""
        vintage = _frame(["2026-08-06"], [9.0])
        live = _frame(["2026-08-06", "2026-08-07", "2026-08-10", "2026-08-11",
                       "2026-08-12"], [9.0, 9.5, 10.0, 11.0, 99.0])
        merged, provenance = bf11.overlay_sessions(vintage, live,
                                                   bf11.TRUNCATE_THROUGH)
        assert provenance["added"] == ["2026-08-07", "2026-08-10", "2026-08-11"]
        assert merged["close"].max() == 11.0

    def test_an_empty_vintage_frame_is_reported_as_a_substitution(self):
        """The Russell panel takes this branch every run; calling it an append lies."""
        live = _frame(["2026-08-10", "2026-08-11", "2026-08-12"], [10.0, 11.0, 99.0])
        merged, provenance = bf11.overlay_sessions(None, live, bf11.TRUNCATE_THROUGH)
        assert provenance["substituted"] is True
        assert "substituted" in provenance["note"]
        assert len(merged) == 2 and merged["close"].max() == 11.0

    def test_the_cache_key_describes_the_TREE_not_the_delta(self, tmp_path):
        """An identical tree must produce an identical key however it got there.

        The bug this pins cost a 13-minute board rebuild on every run: the key was
        hashed from the overlay manifest, so reaching 2026-08-10 by truncating down from
        08-11 and reaching it by changing nothing gave two different keys for the same
        tree, and each run discarded the last one's cache.
        """
        store = tmp_path / "data" / "stocks"
        store.mkdir(parents=True)
        _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0]).to_parquet(
            store / "AAA.parquet")
        fence = bf11.fence_no_bar_after(tmp_path, bf11.TRUNCATE_THROUGH)

        truncated_down = {"through": "2026-08-11", "fence": fence,
                          "totals": {"written": 3596, "sessions_added": 0}}
        already_there = {"through": "2026-08-11", "fence": fence,
                         "totals": {"written": 0, "sessions_added": 0}}

        assert bf11.tree_fingerprint(truncated_down) == bf11.tree_fingerprint(
            already_there), "the same tree produced two cache keys"

    def test_a_different_tree_produces_a_different_key(self, tmp_path):
        """Guard the guard — a key that never changes is worse than no key."""
        store = tmp_path / "data" / "stocks"
        store.mkdir(parents=True)
        _frame(["2026-08-10"], [10.0]).to_parquet(store / "AAA.parquet")
        short = bf11.fence_no_bar_after(tmp_path, bf11.TRUNCATE_THROUGH)
        _frame(["2026-08-10", "2026-08-11"], [10.0, 11.0]).to_parquet(
            store / "AAA.parquet")
        long = bf11.fence_no_bar_after(tmp_path, bf11.TRUNCATE_THROUGH)

        assert bf11.tree_fingerprint({"fence": short}) != bf11.tree_fingerprint(
            {"fence": long})

    def test_the_price_surface_covers_every_rung_of_the_plan_price_ladder(self):
        """A truncation that misses a rung is a truncation with a hole in it.

        ``prophet_bridge`` resolves a name through ``data/baskets/ohlcv`` ->
        ``data/stocks`` -> the wide index-constituent close panels, and
        ``build_stock_library.universe()`` reads the same panels plus ``data/yahoo``.
        Every one of those has to be inside the fenced surface.
        """
        covered = {relative for relative, _ in bf11.PRICE_TICKER_STORES}
        assert {"data/baskets/ohlcv", "data/stocks", "data/yahoo"} <= covered
        panels = set(bf11.PRICE_WIDE_PANELS)
        for group in ("breadth", "smallcap_breadth", "midcap_breadth",
                      "russell_breadth"):
            assert f"data/{group}/_closes_cache.parquet" in panels, (
                f"{group}'s close panel is outside the truncated surface"
            )
        assert "data/baskets/extras.parquet" in panels, (
            "universe()'s LAST rung — the curated searchable names no index cache "
            "carries — is outside the truncated surface. Left behind it does not leak "
            "the future, it tears the panel: those members stay a session back while "
            "every other panel advances, which is the shape that made the 2026-08-09 "
            "bake refuse every candidate on panel.mixed_vintage"
        )


# ---------------------------------------------------------------------------
# R2 — collisions: the live nightly always wins
# ---------------------------------------------------------------------------

class TestCollisionRuleLiveWins:

    def test_a_name_the_live_nightly_took_is_an_incumbent(self):
        plans = {"AAA-BULL-20260812": _plan("AAA", entry=10.0, trigger=11.0,
                                            recorded_at="2026-08-12")}
        incumbents = bf11.live_plans_since(plans, bf11.LIVE_WINS_FROM)
        assert "AAA-BULL" in incumbents

    def test_a_plan_recorded_before_the_window_is_not_an_incumbent(self):
        plans = {"AAA-BULL-20260810": _plan("AAA", entry=10.0, trigger=11.0,
                                            recorded_at="2026-08-10")}
        assert bf11.live_plans_since(plans, bf11.LIVE_WINS_FROM) == {}

    def test_a_live_bear_does_not_knock_out_a_reconstructed_bull(self):
        """Different direction, different episode — the engine keys the same way."""
        plans = {"AAA-BEAR-20260812": _plan("AAA", entry=10.0, trigger=9.0,
                                            direction="BEAR",
                                            recorded_at="2026-08-12")}
        incumbents = bf11.live_plans_since(plans, bf11.LIVE_WINS_FROM)
        assert "AAA-BEAR" in incumbents and "AAA-BULL" not in incumbents

    def test_this_lanes_own_output_can_never_be_its_own_incumbent(self):
        """Otherwise a re-run reads its own plans as live and refuses forever."""
        plans = {"AAA-BULL-20260805": _plan(
            "AAA", entry=10.0, trigger=11.0, recorded_at="2026-08-12",
            origination_mode=bf11.ORIGINATION_MODE)}
        assert bf11.live_plans_since(plans, bf11.LIVE_WINS_FROM) == {}

    def test_the_live_wins_cutoff_is_the_nightly_that_actually_ran(self):
        assert bf11.LIVE_WINS_FROM == "2026-08-12", (
            "the 2026-08-12 nightly is the run that collected both stranded sessions "
            "and originated live; it is the boundary the reconstruction yields to"
        )
        assert bf11.LIVE_WINS_FROM > bf11.BACKFILL_ASOF


# ---------------------------------------------------------------------------
# R3 — chronology: an entry already in the past is not a plan
# ---------------------------------------------------------------------------

class TestChronologyRefusal:
    """The chronology gate is the ENGINE's; this lane only sorts what it decided."""

    def test_a_clock_provenance_refusal_is_filed_as_chronology(self):
        """The CCJ/SHEN/URG/UUUU class from the 2026-08-09 window, by its real name."""
        rows = [{"ticker": "CCJ", "plan_id": None,
                 "reason": "engine_refusal:clock_provenance",
                 "detail": ["formation_date '2026-08-05' postdates tier_event_date "
                            "'2026-08-03'"]}]
        chronology, other = bf11.partition_chronology(rows)
        assert other == []
        assert chronology[0]["ticker"] == "CCJ"
        assert chronology[0]["class"] == "chronology"

    def test_an_unlike_refusal_stays_out_of_the_chronology_bucket(self):
        rows = [{"ticker": "AAA", "reason": "engine_refusal:zone_geometry",
                 "detail": []}]
        chronology, other = bf11.partition_chronology(rows)
        assert chronology == [] and len(other) == 1

    def test_the_partition_loses_nothing(self):
        """Every refusal lands in exactly one bucket — the disclosure claims a complete
        counterfactual set, so a row that falls between them is a hole in that claim."""
        rows = [{"ticker": "CCJ", "reason": "engine_refusal:clock_provenance"},
                {"ticker": "AAA", "reason": "engine_refusal:zone_geometry"},
                {"ticker": "BBB", "reason": "engine_refusal:reorigination_blocked"}]
        chronology, other = bf11.partition_chronology(rows)
        assert len(chronology) + len(other) == len(rows)
        assert {r["ticker"] for r in chronology} | {r["ticker"] for r in other} == {
            "CCJ", "AAA", "BBB"}

    def test_the_lane_adds_no_price_based_chronology_gate_of_its_own(self):
        """§0.8 cuts both ways: a lane may not ADD a gate either.

        The rule this replaced refused when the basis close reached the trigger, which
        is the normal shape of a patience row — the live 2026-08-12 plans carry
        entry == trigger with the real buy zone below and the trigger as the
        don't-chase line, so that rule would have refused them for being ordinary.
        """
        source = Path(bf11.__file__).read_text(encoding="utf-8")
        assert "trigger_already_fired" not in source, (
            "a hand-rolled price comparison is back in the lane; the chronology gate "
            "is _resolve_origination_clocks' and its refusals arrive in intake"
        )
        assert bf11.CHRONOLOGY_STAGE == "clock_provenance"


# ---------------------------------------------------------------------------
# R4 — the pinned vintage
# ---------------------------------------------------------------------------

class TestCodeVintageIsPinned:

    def test_a_tree_at_another_commit_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bf11, "_git", lambda *a, **kw: "deadbeef" * 5 + "\n")
        with pytest.raises(bf11.BackfillRefused, match="not the pinned bake-time"):
            bf11.verify_code_vintage(tmp_path, tmp_path)

    def test_a_tree_descending_from_5370_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bf11, "_git",
                            lambda *a, **kw: bf11.VINTAGE_COMMIT + "\n")
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, b"", b""))
        with pytest.raises(bf11.BackfillRefused, match="DESCENDS from #5370"):
            bf11.verify_code_vintage(tmp_path, tmp_path)

    def test_the_pinned_tree_is_ACCEPTED_when_it_is_the_right_one(self):
        """Guard the guard: the other two cases pass for a function that always raises."""
        monkey = {"calls": []}

        def _fake_git(repo, *args, **kwargs):  # noqa: ANN001
            monkey["calls"].append(args)
            return bf11.VINTAGE_COMMIT + "\n"

        def _fake_run(cmd, **kwargs):  # noqa: ANN001
            # `merge-base --is-ancestor #5370 vintage` must FAIL for a pre-#5370 tree.
            raise subprocess.CalledProcessError(1, cmd)

        original_git, original_run = bf11._git, subprocess.run
        bf11._git, subprocess.run = _fake_git, _fake_run
        try:
            result = bf11.verify_code_vintage(Path("/nowhere"), Path("/nowhere"))
        finally:
            bf11._git, subprocess.run = original_git, original_run

        assert result["vintage_commit"] == bf11.VINTAGE_COMMIT
        assert result["pr5370"]["excluded"] is True
        assert result["path_taken"] == "replayed at the pre-#5370 vintage tree"

    def test_the_pinned_vintage_predates_the_5370_merge(self):
        """The whole reason the lane runs an old tree, stated as a constant."""
        assert bf11.VINTAGE_COMMITTED_UTC < bf11.PR5370_MERGED_UTC
        assert bf11.VINTAGE_COMMITTED_UTC <= bf11.BAKE_CRON_UTC

    @pytest.mark.skipif(
        not (_REPO / ".git").exists(), reason="needs the real object database")
    def test_the_pinned_vintage_is_a_real_commit_on_main(self):
        head = subprocess.run(
            ["git", "rev-parse", "--verify", f"{bf11.VINTAGE_COMMIT}^{{commit}}"],
            cwd=_REPO, capture_output=True, text=True)
        if head.returncode != 0:  # shallow clone — the graft hides it
            pytest.skip("shallow checkout: the pinned vintage is beyond the graft")
        assert head.stdout.strip() == bf11.VINTAGE_COMMIT


# ---------------------------------------------------------------------------
# R5 — the reconstructed board has to be the right board
# ---------------------------------------------------------------------------

def _board(**over) -> tuple[dict, bytes]:
    doc = {
        "as_of": bf11.BACKFILL_ASOF,
        "rank_by": bf11.REQUIRED_RANK_BY,
        "ranking": {"definition": bf11.REQUIRED_RANK_BY},
        "staleness": {"price_through": bf11.BACKFILL_ASOF, "basis": "panel_majority",
                      "inputs": {"panel": {"members_total": 3041}}},
        "buy": [{"ticker": "AAA"}],
    }
    doc.update(over)
    return doc, json.dumps(doc).encode("utf-8")


class TestTheReconstructedBoardIsFenced:

    def test_the_right_board_passes_and_is_marked_synthetic(self):
        identity = bf11.verify_board_identity(*_board())
        assert identity["as_of"] == bf11.BACKFILL_ASOF
        assert identity["synthetic"] is True, (
            "a board that never existed must never be described as one that did"
        )

    def test_another_days_board_is_refused(self):
        with pytest.raises(bf11.BackfillRefused, match="as_of"):
            bf11.verify_board_identity(*_board(as_of="2026-08-12"))

    def test_a_board_priced_through_another_session_is_refused(self):
        """The clock contract: the price basis must BE the recorded session."""
        doc, _ = _board()
        doc["staleness"]["price_through"] = "2026-08-10"
        with pytest.raises(bf11.BackfillRefused, match="prices through"):
            bf11.verify_board_identity(doc, json.dumps(doc).encode("utf-8"))

    def test_the_wrong_ranker_is_refused(self):
        with pytest.raises(bf11.BackfillRefused, match="ranker"):
            bf11.verify_board_identity(*_board(rank_by="us_prophet_v1",
                                               ranking={"definition": "us_prophet_v1"}))


class TestHarnessFidelity:
    """A reconstruction is worth what its reproduction of an observed board is worth."""

    def test_an_exact_rebuild_scores_one(self):
        board = {"buy": [{"ticker": "AAA"}, {"ticker": "BBB"}], "as_of": "2026-08-10"}
        score = bf11.board_fidelity(board, board)
        assert score["jaccard"] == 1.0 and score["exact_order_match"] is True
        assert score["passes_floor"] is True

    def test_a_half_wrong_rebuild_fails_the_floor_and_names_both_directions(self):
        rebuilt = {"buy": [{"ticker": "AAA"}, {"ticker": "CCC"}]}
        reference = {"buy": [{"ticker": "AAA"}, {"ticker": "BBB"}], "as_of": "2026-08-10"}
        score = bf11.board_fidelity(rebuilt, reference)
        assert score["passes_floor"] is False
        assert score["missing_from_rebuild"] == ["BBB"]
        assert score["extra_in_rebuild"] == ["CCC"]

    def test_membership_agreement_without_order_agreement_is_reported_as_such(self):
        rebuilt = {"buy": [{"ticker": "BBB"}, {"ticker": "AAA"}]}
        reference = {"buy": [{"ticker": "AAA"}, {"ticker": "BBB"}], "as_of": "2026-08-10"}
        score = bf11.board_fidelity(rebuilt, reference)
        assert score["jaccard"] == 1.0 and score["exact_order_match"] is False


# ---------------------------------------------------------------------------
# R6 — funnel arithmetic
# ---------------------------------------------------------------------------

class TestReconciliation:

    def test_both_identities_close_on_a_consistent_funnel(self):
        counts = {"admitted": 10, "duplicate_id_blocked": 3,
                  "reorigination_blocked": 2, "reorigination_blocked_rows": 2,
                  "eligible_after_skips": 5, "minted": 4, "collided": 1,
                  "chronology_refused": 1, "still_refused": 1}
        result = bf11.check_reconciliation(counts)
        assert result["admission_identity"]["holds"]
        assert result["disposition_identity"]["holds"]

    def test_blocked_rows_and_blocked_keys_are_counted_separately(self):
        """Two admitted rows on one ticker block once but are counted twice upstream.

        The engine appends one blocked key per admitted ROW, while this lane disposes of
        each distinct KEY once. Collapsing the two would abort a perfectly correct run
        at the reconciliation gate — a guard failing on its own arithmetic rather than
        on the thing it guards.
        """
        counts = {"admitted": 10, "duplicate_id_blocked": 3,
                  "reorigination_blocked": 2,        # distinct keys
                  "reorigination_blocked_rows": 3,   # rows the engine counted
                  "eligible_after_skips": 4, "minted": 4, "collided": 1,
                  "chronology_refused": 0, "still_refused": 1}
        result = bf11.check_reconciliation(counts)
        assert result["admission_identity"]["holds"], "3 + 3 + 4 == 10 on rows"
        assert result["disposition_identity"]["holds"], "4 + 2 == 4 + 1 + 0 + 1 on keys"

    def test_a_lost_candidate_breaks_the_disposition_identity(self):
        """The point of the identity: a name that vanishes cannot vanish quietly."""
        counts = {"admitted": 10, "duplicate_id_blocked": 3,
                  "reorigination_blocked": 2, "reorigination_blocked_rows": 2,
                  "eligible_after_skips": 5, "minted": 4, "collided": 1,
                  "chronology_refused": 0, "still_refused": 1}
        assert not bf11.check_reconciliation(counts)["disposition_identity"]["holds"]

    def test_chronology_refusals_are_inside_the_identity(self):
        """They were added by this lane, so the arithmetic has to account for them."""
        statement = bf11.check_reconciliation({})["disposition_identity"]["statement"]
        assert "chronology_refused" in statement


# ---------------------------------------------------------------------------
# R7 — the disclosure this lane is required to write
# ---------------------------------------------------------------------------

class TestDisclosureCopy:
    """§0.10: plain-word and bilingual, and the ZH written as Chinese."""

    def test_every_copy_field_is_bilingual(self):
        for key, value in bf11.DISCLOSURE_COPY.items():
            assert set(value) == {"en", "zh"}, f"{key} is not bilingual"
            assert value["en"].strip() and value["zh"].strip()

    def test_the_zh_is_chinese_not_an_english_sentence(self):
        """Han density, not han count: a headline is short, a body is not.

        The failure this catches is the one the ZH audit actually found — copy that is
        English in shape with Chinese words dropped in, or worse, an English clause left
        untranslated inside a Chinese sentence.
        """
        for key, value in bf11.DISCLOSURE_COPY.items():
            zh = value["zh"]
            letters = [ch for ch in zh if not ch.isspace()]
            han = [ch for ch in letters if "一" <= ch <= "鿿"]
            assert len(han) >= 4, f"{key}'s zh is too short to be copy: {zh!r}"
            assert len(han) / len(letters) >= 0.5, (
                f"{key}'s zh is only {len(han)}/{len(letters)} han — English-shaped?"
            )
            assert not any(word in zh for word in ("backfill", "reconstruction",
                                                   "outage")), (
                f"{key}'s zh leaks an untranslated internal term"
            )

    def test_the_front_facing_copy_uses_no_internal_vocabulary(self):
        banned = ("backfill", "mixed vintage", "origination_mode", "selection_era",
                  "us_prophet", "anticipation-v1", "falsif", "refut")
        for key, value in bf11.DISCLOSURE_COPY.items():
            lowered = value["en"].lower()
            for word in banned:
                assert word not in lowered, f"{key}'s en copy leaks {word!r}"

    def test_the_copy_says_it_was_never_published_that_night(self):
        """The one fact a reader most needs, in both languages."""
        assert "not" in bf11.DISCLOSURE_COPY["not_a_live_call"]["en"].lower()
        assert "没有" in bf11.DISCLOSURE_COPY["not_a_live_call"]["zh"]


class TestWriteArtifactsProtectsWhatItDidNotWrite:

    def _args(self, tmp_path: Path, plan_id: str = "AAA-BULL-20260805") -> dict:
        plan = {"schema": "prophet.trade_plan/v1", "id": plan_id, "asset": "AAA",
                "recorded_at": bf11.BACKFILL_ASOF,
                "origination_mode": bf11.ORIGINATION_MODE}
        return {"minted": [plan], "receipt": {"schema": "x"},
                "receipt_id": "backfill-20260811-aaaaaaaaaaaaaaaa",
                "document": {"backfills": []}}

    def test_a_plan_this_lane_did_not_write_is_never_overwritten(self, tmp_path):
        plans = tmp_path / bf11.PLANS_RELDIR
        plans.mkdir(parents=True)
        live = plans / "AAA-BULL-20260805.json"
        live.write_text(json.dumps({"id": "AAA-BULL-20260805", "asset": "AAA"}))

        with pytest.raises(SystemExit):
            bf11.write_artifacts(tmp_path, **self._args(tmp_path))

        assert json.loads(live.read_text()) == {"id": "AAA-BULL-20260805",
                                                "asset": "AAA"}, "live plan clobbered"

    def test_this_lanes_own_output_can_be_rewritten_before_it_is_committed(self, tmp_path):
        """Otherwise the lane is single-shot per checkout rather than per window."""
        plans = tmp_path / bf11.PLANS_RELDIR
        plans.mkdir(parents=True)
        (plans / "AAA-BULL-20260805.json").write_text(json.dumps(
            {"id": "AAA-BULL-20260805", "origination_mode": bf11.ORIGINATION_MODE}))

        bf11.write_artifacts(tmp_path, **self._args(tmp_path))

        assert json.loads((plans / "AAA-BULL-20260805.json").read_text())["asset"] == "AAA"


class TestTheBoardFootnoteSurvivesASecondWindow:
    """The front-facing clause has to stop being about one night.

    Until this window there was one lost night and the hover said "over the weekend of
    9 Aug". 2026-08-09 was a Sunday; 2026-08-11 was a Tuesday. Left alone, the hover
    would have told every reader that a Tuesday outage happened at the weekend, and
    dated a board full of 08-11 picks to 08-09.
    """

    def _rows(self, *dates: str) -> list[dict]:
        return [{"origination_mode": f"outage_backfill_{d.replace('-', '_')}",
                 "recorded_at": d} for d in dates]

    def test_one_lost_night_names_that_night(self):
        from engine.prophet_bridge import origination_disclosure  # noqa: PLC0415
        out = origination_disclosure(self._rows("2026-08-09"))
        assert "9 Aug 2026" in out["tip_en"]
        assert "2026年8月9日" in out["tip_zh"]

    def test_two_lost_nights_name_both(self):
        from engine.prophet_bridge import origination_disclosure  # noqa: PLC0415
        out = origination_disclosure(self._rows("2026-08-09", "2026-08-11"))
        assert out["dates"] == ["2026-08-09", "2026-08-11"]
        assert "9 Aug 2026" in out["tip_en"] and "11 Aug 2026" in out["tip_en"]
        assert "2026年8月9日" in out["tip_zh"] and "2026年8月11日" in out["tip_zh"]
        assert out["date"] == "2026-08-09", (
            "the machine-readable field stays the earliest date — a range there would "
            "break every consumer that reads it as a day"
        )

    def test_no_surface_calls_a_tuesday_outage_a_weekend(self):
        from engine import prophet_bridge as pb  # noqa: PLC0415
        for name in ("RECONSTRUCTED_FOOTNOTE_TIP_EN", "RECONSTRUCTED_FOOTNOTE_TIP_ZH",
                     "RECONSTRUCTED_FOOTNOTE_TIP_MULTI_EN",
                     "RECONSTRUCTED_FOOTNOTE_TIP_MULTI_ZH"):
            text = getattr(pb, name)
            assert "weekend" not in text.lower() and "周末" not in text, (
                f"{name} still characterises the lost night as a weekend; "
                f"{bf11.BACKFILL_ASOF} was a Tuesday"
            )

    def test_the_zh_takes_no_space_before_its_particle(self):
        """The ZH-was-English-shaped trap: a date slot followed by a bare space + 的."""
        from engine import prophet_bridge as pb  # noqa: PLC0415
        for name in ("RECONSTRUCTED_FOOTNOTE_TIP_ZH",
                     "RECONSTRUCTED_FOOTNOTE_TIP_MULTI_ZH"):
            assert " 的" not in getattr(pb, name), f"{name} spaces before 的"
            assert " 和" not in getattr(pb, name), f"{name} spaces before 和"


class TestTheLaneIsScopedToOneNight:

    def test_the_constants_all_name_the_same_night(self):
        assert bf11.BACKFILL_ASOF == "2026-08-11"
        assert bf11.ORIGINATION_MODE.endswith("2026_08_11")
        assert bf11.WINDOW_ID.endswith("2026-08-11")

    def test_there_is_no_date_flag_to_widen_the_scope(self):
        """Each outage is chartered separately; a date flag would be a generic lane.

        Reads the ACTUAL parser rather than a docstring — an earlier version of this
        asserted `"--date" not in bf11.main.__doc__ or ""`, and `main` has no docstring,
        so it was asserting a substring is absent from the empty string.
        """
        import argparse  # noqa: PLC0415

        captured: list[str] = []
        real_add = argparse.ArgumentParser.add_argument

        def _spy(self, *args, **kwargs):  # noqa: ANN001
            captured.extend(a for a in args if isinstance(a, str))
            return real_add(self, *args, **kwargs)

        argparse.ArgumentParser.add_argument = _spy
        try:
            with pytest.raises(SystemExit):
                bf11.main(["--help"])
        finally:
            argparse.ArgumentParser.add_argument = real_add

        assert captured, "the spy captured no flags — the test would be vacuous"
        for banned in ("--asof", "--as-of", "--date", "--night", "--window"):
            assert banned not in captured, (
                f"{banned} turns a chartered one-off into the generic backfill lane "
                "research/DO_NOT_REBUILD.md forbids"
            )


# ---------------------------------------------------------------------------
# R8 — the design of record and the artifact cannot disagree
# ---------------------------------------------------------------------------

REAL_SCHEMA_DOC = _REPO / "research" / "PROPHET_LEDGER_SCHEMA.md"


class TestTheDocsAndTheArtifactCannotDisagree:
    """Always runs, including before the reconstruction has executed."""

    def test_the_schema_doc_carries_a_dated_addendum_for_this_window(self):
        text = REAL_SCHEMA_DOC.read_text(encoding="utf-8")
        assert "Addendum 2026-08-13" in text, (
            "research/PROPHET_LEDGER_SCHEMA.md carries no addendum for the 2026-08-11 "
            "reconstruction; an undocumented exception reads as a repeal of the "
            "no-backfill law"
        )
        assert bf11.BACKFILL_ASOF in text
        assert "us-board-frozen-alpha-2026-08" in text, (
            "the addendum does not name the ruling that keeps 08-03→08-06 refused"
        )

    def test_the_addendum_says_the_board_never_existed(self):
        """The one sentence that separates this window from the 2026-08-09 replay."""
        text = REAL_SCHEMA_DOC.read_text(encoding="utf-8")
        assert "never existed anywhere in this repository" in text

    def test_a_marker_claiming_execution_requires_the_artifact(self):
        """Mirrors the 2026-08-09 guard — and covers the direction that one missed.

        That guard keys on the marker's PRESENCE and skips when absent, so a doc that
        UNDERclaims is invisible to it; the 2026-08-09 marker sat unset for two days
        after its artifacts had merged. Here the absent-marker branch asserts the
        converse explicitly instead of skipping, so an executed window with no marker
        fails rather than passing quietly.
        """
        text = REAL_SCHEMA_DOC.read_text(encoding="utf-8")
        claims_executed = any(
            line.startswith(f"executed_window: {bf11.WINDOW_ID}")
            for line in text.splitlines()
        )
        row_exists = False
        if REAL_DISCLOSURES.exists():
            document = json.loads(REAL_DISCLOSURES.read_text(encoding="utf-8"))
            row_exists = any(row.get("id") == bf11.WINDOW_ID
                             for row in (document.get("backfills") or []))
        assert claims_executed == row_exists, (
            f"the schema doc says executed={claims_executed} but the disclosure "
            f"artifact says executed={row_exists}. Either the doc claims something "
            "that never happened, or an executed window is undocumented."
        )


# ---------------------------------------------------------------------------
# R9 — against the tree that actually ships
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not REAL_DISCLOSURES.exists(),
    reason="the reconstruction has not been executed in this tree yet",
)
class TestTheShippedReconstructionRow:

    def _row(self) -> dict | None:
        document = json.loads(REAL_DISCLOSURES.read_text(encoding="utf-8"))
        return next((r for r in (document.get("backfills") or [])
                     if r.get("id") == bf11.WINDOW_ID), None)

    def test_the_row_declares_itself_a_reconstruction(self):
        row = self._row()
        if row is None:
            pytest.skip("this window has not been executed in this tree yet")
        assert row["kind"] == "reconstruction"
        assert "never existed" in row["kind_note"]

    def test_the_row_pins_its_code_vintage(self):
        row = self._row()
        if row is None:
            pytest.skip("this window has not been executed in this tree yet")
        vintage = row["code_vintage"]
        assert vintage["vintage_commit"] == bf11.VINTAGE_COMMIT
        assert vintage["pr5370"]["excluded"] is True

    def test_the_row_proves_its_truncation(self):
        row = self._row()
        if row is None:
            pytest.skip("this window has not been executed in this tree yet")
        truncation = row["inputs"]["price_truncation"]
        assert truncation["ceiling"] == bf11.TRUNCATE_THROUGH
        assert truncation["fence"]["violations"] == 0
        assert truncation["fence"]["files_scanned"] > 0, (
            "a fence that scanned nothing proved nothing"
        )

    def test_the_row_scores_its_own_harness(self):
        row = self._row()
        if row is None:
            pytest.skip("this window has not been executed in this tree yet")
        fidelity = row["harness_fidelity"]
        assert fidelity["measured"] is True, (
            "an unscored reconstruction is an unfalsifiable one"
        )
        assert fidelity["reference_sha256"] == bf11.CONTROL_BOARD_SHA256

    def test_the_row_says_the_board_is_synthetic(self):
        row = self._row()
        if row is None:
            pytest.skip("this window has not been executed in this tree yet")
        assert row["inputs"]["board"]["synthetic"] is True
        assert row["inputs"]["board"]["as_of"] == bf11.BACKFILL_ASOF

    def test_the_row_carries_the_bilingual_reader_copy(self):
        row = self._row()
        if row is None:
            pytest.skip("this window has not been executed in this tree yet")
        assert row["disclosure_copy"] == bf11.DISCLOSURE_COPY


@pytest.mark.skipif(
    not REAL_PLANS_DIR.exists(),
    reason="sparse checkout: site/prophet/plans is not materialised here",
)
class TestTheReceiptSatisfiesTheRealAuditor:
    """The receipt shape is load-bearing, so it is checked against the real validator.

    ``audit_prophet_plan_chronology`` validates EVERY receipt present in a plan's
    creation commit before it will audit that plan — so a receipt that merely looks like
    the nightly's would take every plan created in this commit out of audit with it.
    The 2026-08-09 sibling pins this; without the same test here the module docstring's
    "SHAPE IS LOAD-BEARING, not cosmetic" is an unbacked claim.
    """

    def _receipt(self) -> dict:
        board = {
            "as_of": bf11.BACKFILL_ASOF,
            "rank_by": bf11.REQUIRED_RANK_BY,
            "gate_go": True,
            "staleness": {"price_through": bf11.BACKFILL_ASOF, "basis": "panel_majority",
                          "delayed": False, "unknown": False},
            "buy": [{"ticker": "AAA", "price": 10.0}],
        }
        plan = {"schema": "prophet.trade_plan/v1", "id": "AAA-BULL-20260805",
                "asset": "AAA", "direction": "BULL", "formation_date": "2026-08-05",
                "recorded_at": bf11.BACKFILL_ASOF}
        return bf11._build_receipt(
            receipt_id="backfill-20260811-deadbeefdeadbeef", board=board,
            board_blob=json.dumps(board).encode("utf-8"),
            baseline_sha="a" * 40, minted=[plan], intake={"admitted": 1},
            executed_at="2026-08-13T00:00:00+00:00",
            code_vintage={"vintage_commit": bf11.VINTAGE_COMMIT},
            overlay={"live_price_source_commit": "b" * 40, "fence": {"violations": 0},
                     "files": {}},
            alpha={"as_of": bf11.BACKFILL_ASOF}, fidelity={"measured": True},
        )

    def test_the_real_auditor_accepts_the_receipt(self):
        from scripts.audit_prophet_plan_chronology import (  # noqa: PLC0415
            _validate_receipt_shape,
        )
        source, by_id = _validate_receipt_shape(
            self._receipt(),
            receipt_path=(f"{bf11.RECEIPTS_RELDIR}/"
                          "backfill-20260811-deadbeefdeadbeef.json"),
        )
        assert source["price_through"] == bf11.BACKFILL_ASOF
        assert "AAA-BULL-20260805" in by_id

    def test_the_receipt_carries_its_price_basis_explicitly(self):
        """The auditor raises "must be explicit" on a null, and takes the commit with it."""
        receipt = self._receipt()
        assert receipt["source"]["price_through"] == bf11.BACKFILL_ASOF
        assert receipt["source"]["source_asof"] == receipt["source"]["price_through"]

    def test_the_receipt_says_it_is_a_backfill_rather_than_an_actions_run(self):
        receipt = self._receipt()
        assert receipt["run"]["is_backfill"] is True
        assert receipt["run"]["actor"].endswith("backfill_prophet_outage_20260811.py")


@pytest.mark.skipif(
    not REAL_PLANS_DIR.exists(),
    reason="sparse checkout: site/prophet/plans is not materialised here",
)
class TestTheShippedPlansOfThisWindow:

    def _plans(self) -> list[dict]:
        out = []
        for path in REAL_PLANS_DIR.glob("*.json"):
            try:
                plan = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if plan.get("origination_mode") == bf11.ORIGINATION_MODE:
                out.append(plan)
        return out

    def test_every_plan_of_this_window_is_stamped_and_dated_to_it(self):
        for plan in self._plans():
            assert str(plan.get("recorded_at"))[:10] == bf11.BACKFILL_ASOF
            assert plan.get("backfill_executed_at"), (
                f"{plan.get('id')} carries no backfill_executed_at — the stamp that "
                "says WHEN the row was written is half the provenance"
            )

    def test_no_plan_of_this_window_prices_off_a_later_session(self):
        """The last honest check on the whole lane, read off the shipped artifacts."""
        for plan in self._plans():
            basis = str(plan.get("price_basis_date") or "")[:10]
            assert basis <= bf11.TRUNCATE_THROUGH, (
                f"{plan.get('id')} is priced off {basis}, after the truncation ceiling"
            )
