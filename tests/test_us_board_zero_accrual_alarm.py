"""US board grader: a night that records NOTHING must say so, and say why.

MEASURED OUTAGE (2026-07-31 -> 2026-08-06). data/us_board_ledger/retro_grades.parquet
sat at 2,282 rows for nine days with max as_of 2026-07-21, while the daily.yml step
concluded `success` every single night. Nothing in this module was broken: the breadth
close caches (engine.equity_factors._closes) froze at 2026-07-31 when the collect lane's
"data: daily collection" commit wedged, so no horizon could mature and the grader
correctly emitted nothing. Correct, and completely invisible — ran-clean-no-op,
crashed-and-suppressed-by-`|| true`, and worked-fine all render identically from outside.

Three ways the obvious alarm would have been VACUOUS, each pinned below:

  1. STORE GROWTH, NOT len(fresh). grade_boards re-computes every matured row on every
     run and _merge_into_store is keep-fresh, so the fresh frame is re-grades. The
     2026-08-04 nightly logged "[grade] 1332 new matured rows this run" while the store
     went 2282 -> 2282. An alarm keyed on the fresh frame is silent through the whole
     outage.  -> TestAccrualIsStoreGrowthNotFreshRows

  2. THE PANEL'S INDEX MAX IS A LIAR. extend_prices_to_admitted (#4554) splices in
     yahoo-sourced columns that run ahead of the breadth caches. On origin/main
     2026-08-06 the frame's index.max() read 2026-08-04 while 1498 of its 1540 columns
     ended 2026-07-31 — reading the index would have diagnosed the outage as "panel is
     current, nothing matured".  -> TestPanelReachIsModalNotIndexMax

  3. A SHALLOW CHECKOUT KILLS THE RETRO HALF SILENTLY. _git_revisions is loud when git
     ERRORS (the 2026-07-26 class), but `actions/checkout@v4` defaults to fetch-depth: 1,
     where `git log -- site/factordata/us_standouts.json` exits 0 with one revision. The
     nightlies' own logs show it: "[boards] 13 distinct as_of dates" (2026-07-27) and
     "[boards] 17" (2026-08-05) — both exactly the snapshot count — against 524
     revisions / 32 board dates over a full local checkout.
     -> TestTruncatedHistoryIsLoud

Both quiet directions are pinned too: an alarm that fires on a healthy night trains
readers to ignore the alarm that matters.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import grade_us_board as g  # noqa: E402


def _idx(n: int = 60, end: str = "2026-07-31") -> pd.DatetimeIndex:
    return pd.bdate_range(end=end, periods=n)


def _ramp(idx: pd.DatetimeIndex, start: float = 100.0, step: float = 0.25) -> pd.Series:
    return pd.Series([start + step * i for i in range(len(idx))], index=idx, dtype=float)


def _board(as_of: str, tickers: list[str]) -> dict:
    return {"as_of": as_of, "rank_by": "conviction",
            "rows": [{"ticker": t, "lane": "buy", "sector": "Materials",
                      "position": i, "align_tier": "aligned"}
                     for i, t in enumerate(tickers)]}


def _starved():
    """The outage in miniature: the board panel frozen at 2026-07-31 while the
    benchmark ETF — refreshed by a DIFFERENT lane — keeps printing to 2026-08-04."""
    panel = _idx(end="2026-07-31")
    clock = _idx(end="2026-08-04")
    names = pd.DataFrame({"AAA": _ramp(panel), "BBB": _ramp(panel)}, index=panel)
    etfs = pd.DataFrame({g.BENCH: _ramp(clock, 400.0, 0.1)}, index=clock)
    boards = [_board("2026-07-24", ["AAA", "BBB"]), _board("2026-07-31", ["AAA", "BBB"])]
    return boards, names, etfs


def _healthy():
    """Panel level with the session clock — nothing to grade, and nothing wrong."""
    idx = _idx(end="2026-07-31")
    names = pd.DataFrame({"AAA": _ramp(idx)}, index=idx)
    etfs = pd.DataFrame({g.BENCH: _ramp(idx, 400.0, 0.1)}, index=idx)
    boards = [_board("2026-07-24", ["AAA"]), _board("2026-07-31", ["AAA"])]
    return boards, names, etfs


def _warn_lines(capsys, title: str) -> list[str]:
    return [ln for ln in capsys.readouterr().out.splitlines() if title in ln]


# --------------------------------------------------------------------------- #
# Section 1 — the alarm fires on a genuine no-op, and stays quiet otherwise
# --------------------------------------------------------------------------- #
class TestZeroAccrualIsAnnounced:
    def test_a_nightly_that_adds_nothing_warns_and_STARTS_the_line(self, capsys):
        boards, names, etfs = _starved()
        cont = g.continuity_block(boards, names, etfs)

        assert g.warn_if_no_accrual(
            0, nightly=True, boards=boards, names=names, cont=cont,
            ungraded=["2026-07-31"], skipped_no_price=0) is True

        hits = _warn_lines(capsys, "us-board-ledger-no-accrual")
        assert hits, "nine days of recording nothing produced no annotation"
        for ln in hits:
            assert ln.startswith("::warning"), f"annotation not at column 0: {ln!r}"

    def test_a_night_that_records_rows_is_silent(self, capsys):
        """An alarm that fires on a healthy night trains readers to ignore the alarm
        that matters — so the quiet direction is pinned too."""
        boards, names, etfs = _starved()
        cont = g.continuity_block(boards, names, etfs)

        assert g.warn_if_no_accrual(
            141, nightly=True, boards=boards, names=names, cont=cont,
            ungraded=[], skipped_no_price=0) is False
        assert not [ln for ln in capsys.readouterr().out.splitlines()
                    if ln.startswith("::warning")]

    def test_an_off_lane_run_is_silent(self, capsys):
        """Only the nightly advances the forward ledger (ledger lane-gate law), so a
        retro/manual invocation recording nothing is not news."""
        boards, names, etfs = _starved()
        cont = g.continuity_block(boards, names, etfs)

        assert g.warn_if_no_accrual(
            0, nightly=False, boards=boards, names=names, cont=cont,
            ungraded=["2026-07-31"], skipped_no_price=0) is False
        assert not [ln for ln in capsys.readouterr().out.splitlines()
                    if ln.startswith("::warning")]

    def test_the_annotation_names_the_store_and_refuses_a_backfill(self, capsys):
        boards, names, etfs = _starved()
        cont = g.continuity_block(boards, names, etfs)
        g.warn_if_no_accrual(0, nightly=True, boards=boards, names=names, cont=cont,
                             ungraded=["2026-07-31"], skipped_no_price=0)
        line = _warn_lines(capsys, "us-board-ledger-no-accrual")[0]
        assert g.RETRO_PARQUET.name in line
        assert "backfill" in line, "a graded row is a point-in-time claim"


# --------------------------------------------------------------------------- #
# Section 2 — the reason has to be the RIGHT reason
# --------------------------------------------------------------------------- #
class TestTheReasonNamesTheCause:
    def test_a_frozen_price_lane_reads_as_starved_not_as_a_quiet_night(self):
        """The whole outage. The panel is behind the independent session clock, so the
        collect lane is what has to move — the alarm must point there, not at maturity."""
        boards, names, etfs = _starved()
        cont = g.continuity_block(boards, names, etfs)
        slug, why = g.no_accrual_reason(boards=boards, names=names, cont=cont,
                                        ungraded=["2026-07-31"], skipped_no_price=0)
        assert slug == "price_panel_stale"
        assert "2026-07-31" in why and "2026-08-04" in why

    def test_a_panel_level_with_the_clock_reads_as_nothing_to_grade(self):
        boards, names, etfs = _healthy()
        cont = g.continuity_block(boards, names, etfs)
        slug, _ = g.no_accrual_reason(boards=boards, names=names, cont=cont,
                                      ungraded=[], skipped_no_price=0)
        assert slug == "no_new_maturity"

    def test_the_discriminator_is_a_lane_the_board_does_not_feed(self):
        """ANTI-CIRCULARITY, inherited from continuity_block. A build that never ran
        leaves board AND breadth prices frozen together; judged against its own panel
        the outage reads as a perfectly ordinary weekend. Holding the panel fixed and
        moving ONLY the benchmark lane must flip the verdict."""
        boards, names, _ = _healthy()
        frozen = g.continuity_block(
            boards, names,
            pd.DataFrame({g.BENCH: _ramp(names.index, 400.0, 0.1)}, index=names.index))
        moved_clock = _idx(end="2026-08-04")
        moved = g.continuity_block(
            boards, names,
            pd.DataFrame({g.BENCH: _ramp(moved_clock, 400.0, 0.1)}, index=moved_clock))

        assert g.no_accrual_reason(boards=boards, names=names, cont=frozen,
                                   ungraded=[], skipped_no_price=0)[0] == "no_new_maturity"
        assert g.no_accrual_reason(boards=boards, names=names, cont=moved,
                                   ungraded=[], skipped_no_price=0)[0] == "price_panel_stale"

    def test_an_unpriceable_board_reads_as_unpriceable(self):
        boards, names, etfs = _starved()
        cont = g.continuity_block(boards, names, etfs)
        n_rows = sum(len(b["rows"]) for b in boards)
        slug, _ = g.no_accrual_reason(boards=boards, names=names, cont=cont,
                                      ungraded=[], skipped_no_price=n_rows)
        assert slug == "no_priceable_names"

    def test_no_board_at_all_reads_as_no_board(self):
        slug, _ = g.no_accrual_reason(boards=[], names=pd.DataFrame(), cont={},
                                      ungraded=[], skipped_no_price=0)
        assert slug == "no_boards"


# --------------------------------------------------------------------------- #
# Section 3 — vacuity trap #2: the panel's index max is a liar
# --------------------------------------------------------------------------- #
class TestPanelReachIsModalNotIndexMax:
    def test_one_fresh_column_does_not_make_a_frozen_panel_look_current(self):
        """Reproduces origin/main 2026-08-06 exactly: extend_prices_to_admitted spliced
        the extras-lane names in from the yahoo store, so the frame's index reached
        2026-08-04 while every breadth column stopped at 2026-07-31. Five rows graded
        that night (VALE, NXE, TEAM, RKLB) — enough to move the index, not enough to be
        a working ledger. Reading index.max() diagnoses this as a healthy night."""
        panel = _idx(end="2026-07-31")
        extra = _idx(end="2026-08-04")
        frame = pd.DataFrame({"AAA": _ramp(panel), "BBB": _ramp(panel)}).reindex(extra)
        frame["VALE"] = _ramp(extra)                    # the extras-lane admission
        boards = [_board("2026-07-24", ["AAA", "BBB", "VALE"])]

        assert str(frame.index.max())[:10] == "2026-08-04", "fixture no longer poses the trap"
        assert g._panel_reach(frame, boards) == "2026-07-31"

    def test_reach_is_measured_over_the_names_the_board_actually_holds(self):
        """A panel column nobody was picked from cannot vouch for the board's freshness."""
        panel = _idx(end="2026-07-31")
        fresh = _idx(end="2026-08-04")
        frame = pd.DataFrame({"AAA": _ramp(panel)}).reindex(fresh)
        frame["UNPICKED"] = _ramp(fresh)
        assert g._panel_reach(frame, [_board("2026-07-24", ["AAA"])]) == "2026-07-31"


# --------------------------------------------------------------------------- #
# Section 4 — vacuity trap #1: accrual is store growth, never the fresh frame
# --------------------------------------------------------------------------- #
class TestAccrualIsStoreGrowthNotFreshRows:
    def test_a_full_regrade_of_already_stored_rows_grows_the_store_by_zero(self, tmp_path,
                                                                          monkeypatch):
        """THE trap. Every row the grader emits this run is already in the store, so the
        fresh frame is large and the accrual is zero. `len(df)` cannot tell them apart —
        this is the arithmetic behind "[grade] 1332 new matured rows" on a 2282 -> 2282
        night."""
        monkeypatch.setattr(g, "LEDGER_DIR", tmp_path, raising=True)
        monkeypatch.setattr(g, "RETRO_PARQUET", tmp_path / "retro_grades.parquet",
                            raising=True)
        stored = pd.DataFrame([
            {"as_of": "2026-07-21", "ticker": f"T{i}", "lane": "buy", "horizon": 5,
             "fwd_ret_5": 0.01}
            for i in range(83)
        ])
        stored.to_parquet(g.RETRO_PARQUET, index=False)

        fresh = stored.copy()                       # a faithful re-grade, same keys
        n_before = len(pd.read_parquet(g.RETRO_PARQUET))
        merged = g._merge_into_store(fresh)

        assert len(fresh) == 83, "fixture no longer poses the trap"
        assert len(merged) - n_before == 0, "keep-fresh must not duplicate a re-grade"

    def test_a_genuinely_new_board_date_does_grow_the_store(self, tmp_path, monkeypatch):
        monkeypatch.setattr(g, "LEDGER_DIR", tmp_path, raising=True)
        monkeypatch.setattr(g, "RETRO_PARQUET", tmp_path / "retro_grades.parquet",
                            raising=True)
        stored = pd.DataFrame([{"as_of": "2026-07-21", "ticker": "T0", "lane": "buy",
                                "horizon": 5, "fwd_ret_5": 0.01}])
        stored.to_parquet(g.RETRO_PARQUET, index=False)
        fresh = pd.DataFrame([
            {"as_of": "2026-07-21", "ticker": "T0", "lane": "buy", "horizon": 5,
             "fwd_ret_5": 0.01},                                   # re-grade
            {"as_of": "2026-07-24", "ticker": "T0", "lane": "buy", "horizon": 5,
             "fwd_ret_5": 0.02},                                   # accrual
        ])
        assert len(g._merge_into_store(fresh)) - 1 == 1

    def test_main_feeds_the_alarm_store_growth_and_not_the_fresh_frame(self):
        """INDIRECTION PIN. Sections above prove the two numbers differ; this proves
        main() hands the alarm the one that moved. Without it the guard passes on a
        wiring that would have stayed silent for all nine days."""
        src = (ROOT / "scripts" / "grade_us_board.py").read_text()
        fn = next(n for n in ast.parse(src).body
                  if isinstance(n, ast.FunctionDef) and n.name == "main")
        calls = {n.func.id: n for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "warn_if_no_accrual" in calls, "a silent nightly would stay silent"
        assert "warn_if_history_truncated" in calls, "a dark retro half would stay dark"

        arg = calls["warn_if_no_accrual"].args[0]
        assert isinstance(arg, ast.Name), "accrual must be a computed quantity"
        # the name main() passes must be assigned from a store-length difference
        assigned = [n for n in ast.walk(fn)
                    if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == arg.id for t in n.targets)]
        assert assigned, f"{arg.id} is never assigned in main()"
        expr = ast.dump(assigned[0].value)
        assert "full_df" in expr and "Sub" in expr, (
            f"{arg.id} must be store growth (len(full_df) - rows before), not len(df) — "
            "the fresh frame counts re-grades and is non-zero through a total outage")


# --------------------------------------------------------------------------- #
# Section 5 — vacuity trap #3: git succeeded, and still told us nothing
# --------------------------------------------------------------------------- #
class TestTruncatedHistoryIsLoud:
    def test_a_shallow_checkout_warns_and_STARTS_the_line(self, capsys):
        receipt = {"n_git_revisions": 1, "n_from_snapshots": 17, "n_from_git": 0,
                   "n_boards": 17}
        assert g.warn_if_history_truncated(receipt) is True
        hits = _warn_lines(capsys, "us-board-ledger-history-truncated")
        assert hits, "the retro half went dark with no annotation"
        for ln in hits:
            assert ln.startswith("::warning"), f"annotation not at column 0: {ln!r}"
        assert "fetch-depth" in hits[0], "the annotation must name the actual fix"

    def test_a_full_checkout_is_silent(self, capsys):
        receipt = {"n_git_revisions": 524, "n_from_snapshots": 17, "n_from_git": 15,
                   "n_boards": 32}
        assert g.warn_if_history_truncated(receipt) is False
        assert not [ln for ln in capsys.readouterr().out.splitlines()
                    if ln.startswith("::warning")]

    def test_a_first_ever_run_is_not_accused(self, capsys):
        """One revision of one board is a new ledger, not a truncated one."""
        assert g.warn_if_history_truncated(
            {"n_git_revisions": 1, "n_from_snapshots": 0, "n_from_git": 1,
             "n_boards": 1}) is False
        assert not [ln for ln in capsys.readouterr().out.splitlines()
                    if ln.startswith("::warning")]

    def test_collect_boards_reports_the_provenance_split(self, monkeypatch, tmp_path):
        """The split is the evidence. Without it the [boards] count alone cannot say
        whether the retro leg contributed or was dark.

        2026-08-06: the receipt gained the live-vs-RECOVERED split and the fallback
        state when the git-history dates were recovered into the ledger
        (scripts/backfill_us_board_snapshots.py). The four original counters keep their
        exact meanings — asserted item-by-item rather than as a whole-dict equality, so
        this test pins the evidence instead of the receipt's current key set."""
        snap = tmp_path / "snapshots.jsonl"
        snap.write_text(
            '{"as_of":"2026-07-30","buy":[{"ticker":"AAA"}]}\n'
            '{"as_of":"2026-07-31","buy":[{"ticker":"AAA"}]}\n')
        monkeypatch.setattr(g, "SNAPSHOTS_JSONL", snap, raising=True)
        monkeypatch.setattr(g, "_git_revisions", lambda: [], raising=True)

        receipt: dict = {}
        boards = g.collect_boards(receipt)
        assert len(boards) == 2
        for k, v in {"n_git_revisions": 0, "n_from_snapshots": 2,
                     "n_from_git": 0, "n_boards": 2}.items():
            assert receipt[k] == v, f"{k} lost its meaning"
        # a ledger with no recovered entries still runs the archaeology leg, and the
        # receipt says which leg ran and why
        assert receipt["n_from_ledger_recovered"] == 0
        assert receipt["n_from_ledger_live"] == 2
        assert receipt["git_fallback_used"] is True
        assert receipt["git_fallback_reason"]

    def test_a_git_error_is_still_loud_the_old_way(self, monkeypatch):
        """The 2026-07-26 guard must survive: an ERRORING git still raises rather than
        degrading to a silently smaller ledger."""
        class _Proc:
            returncode = 1
            stdout = ""
            stderr = "fatal: not a git repository"
        monkeypatch.setattr(g.subprocess, "run", lambda *a, **k: _Proc(), raising=True)
        with pytest.raises(RuntimeError, match="silently truncated"):
            g._git_revisions()
