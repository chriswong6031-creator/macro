"""tests/test_us_board_grader_honesty.py — the US board grader's honesty set
(G1-G5 + B3, 2026-08-06).

Each defect below made the published number BETTER than the record supports, and each
is pinned here with its own falsifier — the mutation that would restore the old
behaviour must make the test red, or the test is only describing today's output.

  G1  precision@k scored the top-k OF THE GRADED SUBSET.  A published top name with
      no price promotes the row beneath it into the top-k: a ranking result produced
      by absence.
  G2  `_load_blob` read `.stdout` without checking the return code, so a failed
      `git show` read as "this revision had no board" and the history silently shrank.
  G3  `emit_ledger` excluded the pre-2026-06-25 broad-screen era and `build_track`
      pooled it — one file, two track records, over two different products.
  G4  the outcomes strip filled on the SIGNAL bar (unbuyable), marked every exited
      name at TODAY's close, and divided the win rate by running+stopped only.
  G5  `capture` admitted a NEGATIVE MFE, so realised/MFE on a pure loser is a ratio
      of two negatives: a −11.4% loss scored 2.51, above a perfect winner.
  B3  the featured extension veto fired only on a NUMERIC ext_z above the line, so a
      row with no reading passed it unopposed — 0 vetoes in 59 rows while all 10
      featured names carried ext_z None.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import scripts.grade_us_board as gub  # noqa: E402
from engine import track_scoring as ts  # noqa: E402
from engine import us_board_rank as ubr  # noqa: E402
from tests.test_grade_us_board import _minimal_grade_df  # noqa: E402


# ===========================================================================
# G1 — precision@k scores the PUBLISHED top-k
# ===========================================================================

def _graded(as_of: str, rows: list[tuple[int, float]]) -> pd.DataFrame:
    """(position, excess_spy) pairs → the minimal frame _precision_at_k reads."""
    return pd.DataFrame([
        {"as_of": as_of, "position": pos, "excess_spy": exc, "alpha": -float(pos)}
        for pos, exc in rows
    ])


class TestPrecisionAtKUsesThePublishedRank:

    def test_a_missing_top_name_does_not_promote_the_row_beneath_it(self):
        """Published #0 has no price. Under `head(1)` the #1 row becomes "top-1" and
        its +5% is reported as P@1 = 1.0 — a result the board never produced."""
        df = _graded("2026-07-01", [(1, 0.05), (2, -0.02), (3, -0.03)])
        out = gub._precision_at_k(df)
        assert out["k1"]["n_rows"] == 0, (
            "position 0 did not grade, so there is no graded published top-1; "
            "head(1) would have scored position 1 here"
        )
        assert out["k1"]["basis"] == "published_rank"
        assert out["k1"]["published_topk_rows"] == 1
        assert out["k1"]["graded_topk_rows"] == 0
        assert out["k1"]["coverage"] == 0.0

    def test_the_old_head_k_behaviour_would_have_reported_a_win(self):
        """The falsifier for the test above, computed from the same frame."""
        df = _graded("2026-07-01", [(1, 0.05), (2, -0.02), (3, -0.03)])
        head_k1 = df.sort_values("position").head(1)["excess_spy"]
        assert float((head_k1 > 0).mean()) == 1.0, (
            "fixture must reproduce the defect: head(1) scores the promoted row"
        )

    def test_a_complete_top_k_scores_exactly_the_published_rows(self):
        df = _graded("2026-07-01", [(0, 0.10), (1, -0.05), (2, 0.02), (3, 0.30)])
        out = gub._precision_at_k(df)
        assert out["k3"]["n_rows"] == 3          # positions 0,1,2 — NOT position 3
        assert out["k3"]["pooled_precision"] == round(2 / 3, 4)
        assert out["k3"]["coverage"] == 1.0

    def test_partial_coverage_is_disclosed_as_a_count_not_hidden(self):
        """"nulls printed, not hidden": a thin cell must read as thin."""
        df = _graded("2026-07-01", [(0, 0.10), (2, 0.20)])   # position 1 ungraded
        out = gub._precision_at_k(df)
        assert out["k3"]["graded_topk_rows"] == 2
        assert out["k3"]["published_topk_rows"] == 3
        assert out["k3"]["coverage"] == round(2 / 3, 4)

    def test_a_counterfactual_ordering_is_stamped_as_the_graded_subset(self):
        """An alpha-ordered board exists only over the rows that graded — that IS its
        definition — so it must never claim the published basis."""
        df = _graded("2026-07-01", [(0, 0.10), (1, -0.05), (2, 0.02)])
        out = gub._precision_at_k(df, rank_col="alpha", ascending=False)
        assert out["k1"]["basis"] == "graded_subset"
        assert out["k1"]["n_rows"] == 1

    def test_build_track_top5_lift_uses_the_published_rank(self):
        df = _minimal_grade_df(as_of="2026-06-30", n=8, lane="buy")
        track = gub.build_track(df, [{"as_of": "2026-06-30", "rows": []}],
                                pd.DataFrame())
        top5 = track["per_horizon"]["h5"]["buy_lane"]["p_fwd_pos_top5_vs_base"]
        assert top5["top5_basis"] == "published_rank (position < 5)"
        assert top5["top5_n"] <= 5


# ===========================================================================
# G2 — a broken git read is loud
# ===========================================================================

class TestLoadBlobFailsLoudly:

    def test_a_nonzero_return_code_raises_instead_of_shrinking_the_history(
            self, monkeypatch):
        def _boom(*_a, **_k):
            return subprocess.CompletedProcess(
                args=[], returncode=128, stdout="",
                stderr="fatal: unable to read object 4b825dc")
        monkeypatch.setattr(gub.subprocess, "run", _boom)
        with pytest.raises(RuntimeError, match="truncated history"):
            gub._load_blob("deadbeef")

    def test_a_revision_that_predates_the_board_is_a_legitimate_absence(
            self, monkeypatch):
        """`git show` answers rc=128 for a path that does not exist in a revision.
        That is history, not breakage — the loud guard must not turn every board-less
        commit into a crash."""
        def _absent(*_a, **_k):
            return subprocess.CompletedProcess(
                args=[], returncode=128, stdout="",
                stderr=f"fatal: path '{gub.BOARD_PATH}' does not exist in 'abc123'")
        monkeypatch.setattr(gub.subprocess, "run", _absent)
        assert gub._load_blob("abc123") is None

    def test_an_empty_board_on_a_clean_read_is_still_none(self, monkeypatch):
        monkeypatch.setattr(gub.subprocess, "run", lambda *a, **k:
                            subprocess.CompletedProcess(args=[], returncode=0,
                                                        stdout="   ", stderr=""))
        assert gub._load_blob("abc123") is None

    def test_unparsable_json_on_a_clean_read_is_still_none(self, monkeypatch):
        monkeypatch.setattr(gub.subprocess, "run", lambda *a, **k:
                            subprocess.CompletedProcess(args=[], returncode=0,
                                                        stdout="{not json", stderr=""))
        assert gub._load_blob("abc123") is None


# ===========================================================================
# G3 — one era rule
# ===========================================================================

class TestOneEraRule:

    def test_build_track_excludes_the_era_emit_ledger_already_excludes(self):
        pre = _minimal_grade_df(as_of="2026-06-16", n=4, lane="buy")
        post = _minimal_grade_df(as_of="2026-06-30", n=4, lane="buy")
        both = pd.concat([pre, post], ignore_index=True)
        track = gub.build_track(both, [{"as_of": "2026-06-30", "rows": []}],
                                pd.DataFrame())
        assert track["graded_dates"] == ["2026-06-30"], (
            "the 2026-06-16 broad-screen board is a different product; grading it "
            "here while emit_ledger refuses it publishes two records from one file"
        )
        assert track["graded_rows_total"] == len(post)

    def test_the_boundary_date_itself_is_included(self):
        on = _minimal_grade_df(as_of=gub.LEDGER_HISTORY_FROM, n=3, lane="buy")
        track = gub.build_track(on, [{"as_of": gub.LEDGER_HISTORY_FROM, "rows": []}],
                                pd.DataFrame())
        assert track.get("empty") is not True
        assert track["graded_dates"] == [gub.LEDGER_HISTORY_FROM]

    def test_the_cut_is_counted_in_the_artifact_never_silent(self):
        pre = _minimal_grade_df(as_of="2026-06-16", n=4, lane="buy")
        post = _minimal_grade_df(as_of="2026-06-30", n=2, lane="buy")
        track = gub.build_track(pd.concat([pre, post], ignore_index=True),
                                [{"as_of": "2026-06-30", "rows": []}], pd.DataFrame())
        assert track["history"]["era_from"] == gub.LEDGER_HISTORY_FROM
        assert track["history"]["n_rows_excluded"] == len(pre)
        assert "broad screen" in track["history"]["basis"]

    def test_an_all_pre_era_frame_says_why_it_is_empty(self):
        pre = _minimal_grade_df(as_of="2026-06-16", n=4, lane="buy")
        track = gub.build_track(pre, [{"as_of": "2026-06-16", "rows": []}],
                                pd.DataFrame())
        assert track["empty"] is True
        assert gub.LEDGER_HISTORY_FROM in track["note"]
        assert track["history"]["n_rows_excluded"] == len(pre)

    def test_the_era_constant_is_the_one_both_consumers_read(self):
        """Mutation guard: the ledger and the track record must not be able to drift
        onto different dates."""
        source = (_REPO / "scripts" / "grade_us_board.py").read_text(encoding="utf-8")
        assert source.count('LEDGER_HISTORY_FROM = "') == 1


# ===========================================================================
# G4 — the outcomes strip
# ===========================================================================

def _names_frame(**cols) -> pd.DataFrame:
    idx = pd.bdate_range("2026-01-02", periods=10)
    return pd.DataFrame(cols, index=idx)


def _board(as_of: str, tickers: list[str]) -> dict:
    return {"as_of": as_of, "rank_by": "test",
            "rows": [{"ticker": t, "lane": "buy", "position": i}
                     for i, t in enumerate(tickers)]}


# bdate_range("2026-01-02", 10) → 01-02 01-05 01-06 01-07 01-08 01-09 01-12 ...
# AAA surfaces on 01-05 (idx 1), is gone from the 01-07 board (idx 3).
#   signal bar  01-05 = 100  (unbuyable — the board is computed from this close)
#   next bar    01-06 = 125  (the honest fill)
#   exit bar    01-07 = 150  (the honest mark)
#   afterwards        = 300  (today's drift — must never reach the number)
_AAA = [100.0, 100.0, 125.0, 150.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0]
_BOARDS = [_board("2026-01-05", ["AAA", "KEEP"]),
           _board("2026-01-06", ["AAA", "KEEP"]),
           _board("2026-01-07", ["KEEP"])]


class TestOutcomesStripConventions:

    def _row(self, **extra):
        names = _names_frame(AAA=_AAA, KEEP=[50.0] * 10, **extra)
        out = gub.emit_outcomes(_BOARDS, names)
        return out, next(r for r in out["rows"] if r["ticker"] == "AAA")

    def test_the_fill_is_the_next_bar_not_the_signal_bar(self):
        _out, row = self._row()
        assert row["surfaced_price"] == 125.0, (
            "filled at the 01-05 close (100) — the bar the board is computed from "
            "and published that evening. Unbuyable."
        )

    def test_the_mark_is_the_exit_bar_not_todays_close(self):
        _out, row = self._row()
        assert row["last_price"] == 150.0, (
            "marked at the last available close (300) — three weeks of drift booked "
            "under a board that had already dropped the name"
        )
        assert row["mark_date"] == "2026-01-07"
        assert row["exit_date"] == "2026-01-07"

    def test_the_two_fixes_together_move_the_number(self):
        """Falsifier: the old conventions give +200%, the honest ones +20%."""
        _out, row = self._row()
        assert row["pct_since"] == pytest.approx(20.0, abs=0.05)
        old = (_AAA[-1] / _AAA[1] - 1.0) * 100.0
        assert old == pytest.approx(200.0), "fixture must reproduce the defect"

    def test_flats_stay_in_the_win_rate_denominator(self):
        """96 of 321 rows on the shipped artifact were deleted by the old denominator.
        A flat is not a missing outcome — it is a buy call that went nowhere."""
        idx = pd.bdate_range("2026-01-02", periods=10)
        names = pd.DataFrame({
            "KEEP": [50.0] * 10,
            "UP":   [10.0, 10.0, 10.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0],
            "DOWN": [10.0, 10.0, 10.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0],
            "FLAT": [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
        }, index=idx)
        boards = [_board("2026-01-05", ["UP", "DOWN", "FLAT", "KEEP"]),
                  _board("2026-01-06", ["UP", "DOWN", "FLAT", "KEEP"]),
                  _board("2026-01-07", ["KEEP"])]
        smry = gub.emit_outcomes(boards, names)["summary"]
        assert (smry["n_running"], smry["n_stopped"], smry["n_flat"]) == (1, 1, 1)
        assert smry["win_rate"] == round(1 / 3, 3), (
            "running+stopped only would report 0.5 — deleting the flat"
        )

    def test_a_name_whose_next_bar_has_not_printed_is_skipped_not_filled(self):
        """In flight is not fillable. Filling at the signal bar is the defect; filling
        at nothing is a fabrication. It is counted as a skip, like every other
        no-price exclusion."""
        idx = pd.bdate_range("2026-01-02", periods=10)   # ends 2026-01-15
        # LATE prints on its surfacing bar and never again: there is no next bar to
        # buy at. The signal-bar close (77) is exactly the price the old code used.
        late = [np.nan] * 8 + [77.0] + [np.nan]          # only 2026-01-14
        names = pd.DataFrame({"KEEP": [50.0] * 10, "LATE": late}, index=idx)
        boards = [_board("2026-01-14", ["LATE", "KEEP"]),
                  _board("2026-01-15", ["LATE", "KEEP"]),
                  _board("2026-01-16", ["KEEP"])]
        out = gub.emit_outcomes(boards, names)
        assert "LATE" in (out.get("summary", out).get("skipped_no_price") or []), out
        assert not any(r["ticker"] == "LATE" for r in out.get("rows", [])), (
            "the signal bar was used as the fill — the exact defect")

    def test_the_conventions_are_stated_in_the_artifact(self):
        out, _row = self._row()
        conv = out["summary"]["conventions"]
        assert "next session" in conv["entry"]
        assert "not today" in conv["mark"]
        assert "flats included" in conv["win_rate_denominator"]


# ===========================================================================
# G5 — capture needs a strictly positive MFE
# ===========================================================================

def _episode(pnl: float, mfe: float, mae: float, *, board_date="2026-07-01") -> dict:
    return {"matured": True, "pnl": pnl, "excess": pnl, "mfe": mfe, "mae": mae,
            "held": 10, "board_date": board_date, "entry_date": board_date}


class TestCaptureFloorsTheMfeDenominator:

    def test_a_pure_loser_cannot_score_capture_above_one(self):
        """The audit's row: −11.4% realised, best bar −4.5% — never above entry.
        realised/MFE is a ratio of two negatives and printed 2.51."""
        rows = [_episode(-11.4, -4.54, -12.0)]
        assert (-11.4 / -4.54) > 2.5, "fixture must reproduce the defect"
        out = ts.summarize(rows)
        assert out["capture"] is None
        assert out["n_capture"] == 0
        assert out["n_capture_undefined"] == 1
        assert out["capture_undefined_pct"] == 100.0

    def test_the_undefined_rows_are_counted_not_averaged_away(self):
        rows = [_episode(5.0, 10.0, -1.0), _episode(-11.4, -4.54, -12.0)]
        out = ts.summarize(rows)
        assert out["capture"] == 0.5          # only the real one
        assert out["n_capture"] == 1
        assert out["n_capture_undefined"] == 1
        assert out["capture_undefined_pct"] == 50.0

    def test_dropping_the_poisoned_rows_lowers_the_median(self):
        """Direction check: the fix must move the number DOWN, because every row it
        removes scored implausibly high."""
        real = [_episode(4.0, 10.0, -1.0), _episode(6.0, 10.0, -1.0),
                _episode(8.0, 10.0, -1.0)]
        poisoned = [_episode(-11.4, -4.54, -12.0), _episode(-9.0, -3.0, -10.0)]
        honest = ts.summarize(real + poisoned)["capture"]
        old_style = float(np.median(
            [r["pnl"] / r["mfe"] for r in real + poisoned if abs(r["mfe"]) > 1e-9]))
        assert honest < old_style, (
            f"honest={honest} old={old_style} — the old filter admitted the negatives"
        )

    def test_a_loser_that_did_trade_above_entry_still_has_a_capture(self):
        """The floor removes UNDEFINED rows, not losing ones: a trade that ran +6%
        and closed −3% really did give back more than it made."""
        out = ts.summarize([_episode(-3.0, 6.0, -4.0)])
        assert out["capture"] == -0.5
        assert out["n_capture"] == 1

    def test_a_zero_mfe_is_undefined_not_a_division(self):
        out = ts.summarize([_episode(-2.0, 0.0, -3.0)])
        assert out["capture"] is None
        assert out["n_capture_undefined"] == 1

    def test_the_floor_matches_the_study_that_discovered_it(self):
        """One vocabulary, one place: exit_policy_study recomputed capture with this
        exact rule because summarize's was wrong. They must not drift apart."""
        source = (_REPO / "scripts" / "exit_policy_study.py").read_text(encoding="utf-8")
        assert "_MFE_FLOOR = 1e-9" in source
        assert ts.MFE_FLOOR == 1e-9

    def test_the_counts_ship_even_on_an_empty_sample(self):
        out = ts.summarize([])
        assert out["n_capture"] == 0 and out["n_capture_undefined"] == 0
        assert out["capture_undefined_pct"] is None


# ===========================================================================
# B3 → ANTICIPATION v1 — the featured extension veto fires on EVIDENCE only
#
# B3 (2026-08-06) made an unknown ``ext_z`` a featured veto, on the reasoning that a
# veto whose input is dark cannot be said to have passed.  That reasoning was right
# about the evidence and wrong about the remedy: the very next board proved it, with
# 69 of 69 buy rows carrying no reading (the equity close panel's newest row held 6 of
# 3,034 members and ``extension_signals`` reads one global ``.iloc[-1]``) and a
# featured lane published as 0.  ANTICIPATION v1 (2026-08-08) keeps the veto for a
# KNOWN reading past the parabolic line and replaces the absence-veto with a
# disclosure: ``ext_unknown`` on the row, a coverage count on the block, and a
# ``::warning`` when the input is out on most of the board.  The score leg is
# unchanged — an unmeasured row still earns 0 runway, because fail-closed belongs to
# the POINTS.
# ===========================================================================

def _featurable(ticker="A", **over) -> dict:
    row = {
        "ticker": ticker,
        "sector": "Information Technology",
        "alpha": 1.0,
        "entry_signal": {"status": "buy_now"},
        "signal": {"tier_cascade": "T2", "ticks": 1, "asof": "2026-07-31"},
        "ext_z": 0.0,
    }
    row.update(over)
    return row


class TestFeaturedExtensionVeto:

    def test_an_unknown_extension_is_disclosed_not_blocked(self):
        row = _featurable()
        row.pop("ext_z")
        assert ubr.featured_shortfalls(row) == []
        assert ubr.ext_unknown(row) is True

    def test_a_known_reading_below_the_line_still_qualifies(self):
        """Falsifier: the veto must not have become a blanket block."""
        assert ubr.featured_shortfalls(_featurable(ext_z=1.5)) == []
        assert ubr.featured_shortfalls(_featurable(ext_z=2.0)) == []
        assert "extended" in ubr.featured_shortfalls(_featurable(ext_z=2.5))

    def test_a_nan_reading_counts_as_unknown(self):
        """The 07-31 defect delivered NaN, not a missing key — a float that is not a
        number is not evidence.  It is disclosed as unknown, never read as 0.0."""
        row = _featurable(ext_z=float("nan"))
        assert ubr.ext_unknown(row) is True
        assert ubr.featured_shortfalls(row) == []

    def test_the_row_stays_rankable_and_stays_on_the_board(self):
        """Display-tier only, in BOTH eras: the extension read changes a FLAG, never
        membership and never score.  What moved on 2026-08-08 is which flag."""
        rows = [_featurable("KNOWN", ext_z=0.0), _featurable("UNKNOWN")]
        rows[1].pop("ext_z")
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        assert {r["ticker"] for r in scored} == {"KNOWN", "UNKNOWN"}
        by = {r["ticker"]: r for r in scored}
        assert by["UNKNOWN"]["stage"] == "live"
        assert by["UNKNOWN"]["featured"] is True
        assert by["UNKNOWN"]["ext_unknown"] is True
        assert by["KNOWN"]["featured"] is True
        assert by["KNOWN"]["ext_unknown"] is False
        # The SCORE still fails closed on the unmeasured row — the runway leg pays 0,
        # so the two rows are not scored as if the gap were a reading of "fine".
        assert by["UNKNOWN"]["prophet"]["score"] > 0
        assert by["UNKNOWN"]["prophet"]["components"]["runway"] == 0.0
        assert by["KNOWN"]["prophet"]["components"]["runway"] == 1.0

    def test_the_block_counts_the_rows_whose_evidence_is_missing(self):
        """A board that features rows it could not measure must SAY so. The count is
        recomputed from the rows it ships with, never frozen."""
        rows = [_featurable(f"T{i}") for i in range(3)]
        for r in rows:
            r.pop("ext_z")
        scored = ubr.score_rows(rows, board_asof="2026-07-31")
        block = ubr.ranking_block(scored)
        assert block["featured_count"] == 3
        assert block["ext_unknown_coverage"] == {
            "unknown": 3, "n": 3, "featured_with_unknown": 3}
        # The B3 key survives, still recomputed, and now reads 0 — accurate, since
        # nothing is refused for that reason any more.
        assert block["featured_blocked_unknown_extension"] == 0
        # Mutation: give them readings and the disclosure must move.
        alive = ubr.score_rows([_featurable(f"T{i}", ext_z=0.0) for i in range(3)],
                               board_asof="2026-07-31")
        assert ubr.ranking_block(alive)["ext_unknown_coverage"] == {
            "unknown": 0, "n": 3, "featured_with_unknown": 0}

    def test_the_requirement_text_names_the_unknown_case(self):
        block = ubr.ranking_block([])
        text = " ".join(block["featured_requirements"])
        assert "unknown" in text.lower()
        assert "ext_unknown" in text
