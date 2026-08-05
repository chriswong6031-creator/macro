"""US board ledger: ROW-PERSISTENCE + OUTAGE CONTINUITY.

Operator report 2026-08-05: VALE sat in the US board's buy lane on five board dates
(2026-07-24 .. 2026-07-31, verifiable in data/us_board_ledger/snapshots.jsonl), then
had ZERO rows in retro_grades.parquet and never appeared in the Track-record dialog —
while NEM, admitted in the same era, showed fine.

Root cause, and the class these tests close:

  The board's universe (scripts/build_stock_library.py::universe) is a UNION of three
  sources — data/stocks deep history, the breadth close caches, and the curated
  `stock_search.extra_tickers` extras read from the yahoo store (foreign ADRs, recent
  IPOs outside the S&P 1500). Every grader in scripts/grade_us_board.py priced from
  exactly ONE of them: engine.equity_factors._closes("broad"), the breadth caches.
  A name admitted through the extras lane therefore had `tk not in names.columns`, hit
  `continue`, and left NOTHING in the artifact. It was not delisted and not stale —
  data/yahoo/VALE.parquet carried 6,131 closes through 2026-08-03. The whole shipped
  `tickers_skipped` list was one class: ASTS BIDU CRDO NET NVO NXE PL RKLB TEAM U UROY
  VALE, all recoverable from the very store the board admitted them from.

Two independent halves are pinned here, and BOTH have to hold:

  1. the price panel covers what the board ADMITS (Section 1) — otherwise a whole
     admission lane is structurally ungradeable forever, not merely late;
  2. no admission is ever DELETED (Section 2). A pick the desk can no longer price is
     still a pick: it publishes as an unscored row with a plain reason and sits in no
     summary number. Mirrors the CN precedent's "no row is ever lost" count
     (tests/test_cn_track_ledger_eras.py::TestUnknownStampIsNeverDropped) — the US
     emitter is a separate code path (scripts/grade_us_board.py::emit_ledger vs
     scripts/build_china_library.py::emit_cn_track_ledger), so the idiom is mirrored,
     not shared.

Section 3 pins the OTHER way this went unseen for three days: the forward ledger only
advances in the nightly, so when the nightly died the snapshots simply stopped and
every downstream surface kept publishing the last good record with a stale `as_of` and
no complaint. The staleness clock must NOT be the board's own price source — a build
that never ran leaves board and prices frozen together and reads as perfectly fresh.

Prices are synthetic throughout so the arithmetic is deterministic; the emitter, the
episode builder and the scorer are the REAL ones (no forked scoring math).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import grade_us_board as g  # noqa: E402

# Board dates must be >= LEDGER_HISTORY_FROM or the emitter counts them as a different
# instrument and drops them from board_days (grade_us_board.LEDGER_HISTORY_FROM).
_D = ["2026-06-25", "2026-06-26", "2026-06-29", "2026-06-30", "2026-07-01"]


def _idx(n: int = 400, end: str = "2026-07-10") -> pd.DatetimeIndex:
    return pd.bdate_range(end=end, periods=n)


def _ramp(idx: pd.DatetimeIndex, start: float = 100.0, step: float = 0.25) -> pd.Series:
    """A monotone series — every episode matures a WIN, so any change in the win rate
    is caused by the population, not by noise."""
    return pd.Series([start + step * i for i in range(len(idx))], index=idx, dtype=float)


def _board(as_of: str, tickers: list[str], sector: str = "Materials") -> dict:
    return {"as_of": as_of, "rank_by": "conviction",
            "rows": [{"ticker": t, "lane": "buy", "sector": sector,
                      "position": i, "align_tier": "aligned"}
                     for i, t in enumerate(tickers)]}


@pytest.fixture()
def etfs() -> pd.DataFrame:
    idx = _idx()
    return pd.DataFrame({g.BENCH: _ramp(idx, 400.0, 0.1)}, index=idx)


# --------------------------------------------------------------------------- #
# Section 1 — the price panel must cover what the board ADMITS
# --------------------------------------------------------------------------- #
class TestAdmittedNamesArePriced:
    def test_an_extras_lane_admission_is_recovered_from_the_admission_store(
        self, monkeypatch,
    ):
        """The VALE shape: on the board, absent from the breadth cache, present in the
        yahoo store the board itself read."""
        idx = _idx()
        names = pd.DataFrame({"INCACHE": _ramp(idx)}, index=idx)
        boards = [_board(_D[0], ["INCACHE", "EXTRAS"])]

        monkeypatch.setattr(
            g, "load_dead_prices", lambda *a, **k: {}, raising=True)
        from lib import store
        monkeypatch.setattr(
            store, "read",
            lambda grp, t: (pd.DataFrame({"close": _ramp(idx)}, index=idx)
                            if (grp, t) == ("yahoo", "EXTRAS") else None),
            raising=True)

        out, receipt = g.extend_prices_to_admitted(names, boards)
        assert "EXTRAS" in out.columns
        assert receipt["n_recovered_from_admitted_store"] == 1
        assert receipt["recovered"] == ["EXTRAS"]
        assert receipt["n_unresolved"] == 0
        # additive only — a column that was already usable is untouched
        pd.testing.assert_series_equal(out["INCACHE"], names["INCACHE"])

    def test_a_name_with_no_series_anywhere_warns_and_STARTS_the_line(
        self, monkeypatch, capsys,
    ):
        """GitHub drops a ::warning that does not start the line, and every logger in
        this repo prefixes it — so the column is the assertion, not the wording."""
        idx = _idx()
        names = pd.DataFrame({"INCACHE": _ramp(idx)}, index=idx)
        boards = [_board(_D[0], ["INCACHE", "GHOST"])]

        monkeypatch.setattr(g, "load_dead_prices", lambda *a, **k: {}, raising=True)
        from lib import store
        monkeypatch.setattr(store, "read", lambda grp, t: None, raising=True)

        _, receipt = g.extend_prices_to_admitted(names, boards)
        assert receipt["n_unresolved"] == 1
        assert receipt["unresolved"] == ["GHOST"]

        lines = capsys.readouterr().out.splitlines()
        hits = [ln for ln in lines
                if "us-board-admitted-name-unpriced" in ln]
        assert hits, "no annotation emitted for an unpriceable admission"
        for ln in hits:
            assert ln.startswith("::warning"), f"annotation not at column 0: {ln!r}"
        assert "GHOST" in hits[0]

    def test_the_nightly_entry_point_actually_calls_the_widener(self):
        """WIRING. Section 1's other tests prove the function works; this proves it is
        not dead code. `main()` is a script entry point — running it end-to-end here
        would drag in git archaeology and the regime-vector store, so the pin is an AST
        read of main's body (a LIVE Call node, so a commented-out or deleted call fails
        where a substring grep would still pass on a docstring mention). It does NOT
        prove ordering; the two behavioural tests above own the semantics."""
        import ast
        src = (ROOT / "scripts" / "grade_us_board.py").read_text()
        fn = next(n for n in ast.parse(src).body
                  if isinstance(n, ast.FunctionDef) and n.name == "main")
        called = {n.func.id for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "extend_prices_to_admitted" in called, (
            "the nightly grades a narrower universe than the board admits")
        assert "warn_if_stale" in called, "a dead nightly would stay silent"

    def test_a_dead_name_is_not_re_read_from_the_extras_store(self, monkeypatch):
        """engine.grading.resolve_series already extends live closes with the edgar
        dead-name terminals; re-reading a delisted name from yahoo would resurrect a
        stale survivor price over its terminal value."""
        idx = _idx()
        names = pd.DataFrame({"INCACHE": _ramp(idx)}, index=idx)
        boards = [_board(_D[0], ["INCACHE", "DEADCO"])]

        monkeypatch.setattr(
            g, "load_dead_prices",
            lambda *a, **k: {"DEADCO": pd.Series([1.0], index=idx[:1])}, raising=True)
        from lib import store
        calls: list[tuple] = []

        def _read(grp, t):
            calls.append((grp, t))
            return None
        monkeypatch.setattr(store, "read", _read, raising=True)

        _, receipt = g.extend_prices_to_admitted(names, boards)
        assert ("yahoo", "DEADCO") not in calls
        assert receipt["n_unresolved"] == 0


# --------------------------------------------------------------------------- #
# Section 2 — ROW-PERSISTENCE: an admission is never deleted
# --------------------------------------------------------------------------- #
class TestNoAdmissionIsEverLost:
    @pytest.fixture()
    def departed(self, etfs):
        """DEPARTED is admitted on the first two board dates and gone from every later
        one — the operator's 'vanished from the live board' shape — while STAYS rides
        the whole window. Both are fully priced, so any missing row is a population
        bug, not a data hole."""
        idx = _idx()
        names = pd.DataFrame(
            {"STAYS": _ramp(idx), "DEPARTED": _ramp(idx, 50.0, 0.1)}, index=idx)
        boards = [_board(_D[0], ["STAYS", "DEPARTED"]),
                  _board(_D[1], ["STAYS", "DEPARTED"]),
                  _board(_D[2], ["STAYS"]),
                  _board(_D[3], ["STAYS"]),
                  _board(_D[4], ["STAYS"])]
        return g.emit_ledger(boards, names, etfs), boards

    def test_a_boarded_then_departed_name_still_has_a_row(self, departed):
        doc, _ = departed
        rows = [r for r in doc["rows"] if r["t"] == "DEPARTED"]
        assert rows, "a name that left the board vanished from the ledger"
        assert rows[0]["d"] == _D[0], "the row is anchored to its ADMISSION, not its exit"
        assert rows[0]["e"] is not None, "a fully-priced departed name must carry an entry"

    def test_every_admitted_episode_reaches_some_row(self, departed):
        """The count that actually pins the bug (CN Section 3 idiom): the emitter's
        own episode builder and its published rows must agree, name for name."""
        from engine import track_scoring as ts
        doc, boards = departed
        board_days = {b["as_of"]: {r["ticker"] for r in b["rows"] if r["lane"] == "buy"}
                      for b in boards}
        episodes = {(e["ticker"], e["entry_date"]) for e in ts.build_episodes(board_days)}
        published = {(r["t"], r["d"]) for r in doc["rows"]}
        assert published == episodes
        assert doc["meta"]["n_total"] == len(episodes)

    def test_an_unpriceable_admission_publishes_unscored_instead_of_disappearing(
        self, monkeypatch, etfs,
    ):
        idx = _idx()
        names = pd.DataFrame({"STAYS": _ramp(idx)}, index=idx)  # GHOST has no column
        boards = [_board(_D[0], ["STAYS", "GHOST"]), _board(_D[1], ["STAYS"])]
        doc = g.emit_ledger(boards, names, etfs)

        ghost = [r for r in doc["rows"] if r["t"] == "GHOST"]
        assert len(ghost) == 1, "an unpriceable admission was deleted"
        assert ghost[0]["st"] == "unscored"
        assert ghost[0]["xr"] == "no price data", "the reason must be stated, not implied"
        assert ghost[0]["p"] is None and ghost[0]["e"] is None
        assert ghost[0]["m"] is False
        # ...and it stays out of every published number
        assert doc["summary"]["n_skipped_no_price"] == 1
        assert doc["meta"]["survivorship"]["tickers_skipped"] == ["GHOST"]

    def test_an_unscored_row_moves_no_summary_number(self, monkeypatch, etfs):
        """The honest-disclosure half: publishing the row must not quietly enter it
        into the record. Same boards, GHOST priced vs unpriced — the matured stats are
        identical because GHOST never matures either way."""
        idx = _idx()
        boards = [_board(_D[0], ["STAYS", "GHOST"]), _board(_D[1], ["STAYS", "GHOST"])]
        without = g.emit_ledger(
            boards, pd.DataFrame({"STAYS": _ramp(idx)}, index=idx), etfs)
        # a control that never admitted GHOST at all
        control = g.emit_ledger(
            [_board(_D[0], ["STAYS"]), _board(_D[1], ["STAYS"])],
            pd.DataFrame({"STAYS": _ramp(idx)}, index=idx), etfs)
        for k in ("win_pct", "expectancy_pct", "profit_factor", "n_matured", "median_pct"):
            assert without["summary"][k] == control["summary"][k], k

    def test_narrowing_the_population_breaks_the_coverage_invariant(
        self, monkeypatch, etfs,
    ):
        """MUTATION CHECK. Re-narrowing the population — dropping unpriceable episodes
        the way the pre-fix emitter did — is exactly what makes the coverage assertion
        above false. If someone restores that `continue`, `n_dropped` goes to zero and
        this test reddens along with `test_every_admitted_episode_reaches_some_row`."""
        idx = _idx()
        names = pd.DataFrame({"STAYS": _ramp(idx)}, index=idx)
        boards = [_board(_D[0], ["STAYS", "GHOST"]), _board(_D[1], ["STAYS"])]
        doc = g.emit_ledger(boards, names, etfs)

        narrowed = [r for r in doc["rows"] if r["st"] != "unscored"]
        n_dropped = len(doc["rows"]) - len(narrowed)
        assert n_dropped == 1, "the unscored row is the ONLY thing keeping coverage whole"
        assert "GHOST" not in {r["t"] for r in narrowed}


# --------------------------------------------------------------------------- #
# Section 3 — outage continuity: a dead nightly is visible the next morning
# --------------------------------------------------------------------------- #
class TestOutageIsDisclosedNeverBackfilled:
    def _stale(self):
        """Board frozen at 2026-06-30 while the benchmark keeps printing to 07-10 —
        the 08-02/08-03 collect outage in miniature."""
        idx = _idx()
        names = pd.DataFrame({"STAYS": _ramp(idx)}, index=idx)
        etfs = pd.DataFrame({g.BENCH: _ramp(idx, 400.0, 0.1)}, index=idx)
        boards = [_board(_D[0], ["STAYS"]), _board(_D[3], ["STAYS"])]
        return boards, names, etfs

    def test_a_stale_snapshot_warns_and_STARTS_the_line(self, capsys):
        boards, names, etfs = self._stale()
        cont = g.continuity_block(boards, names, etfs)
        assert cont["n_stale_sessions"] > 0
        assert g.warn_if_stale(cont) is True

        lines = capsys.readouterr().out.splitlines()
        hits = [ln for ln in lines if "us-board-ledger-stale" in ln]
        assert hits, "a dead nightly produced no annotation"
        for ln in hits:
            assert ln.startswith("::warning"), f"annotation not at column 0: {ln!r}"

    def test_a_current_snapshot_is_silent(self, capsys):
        """An alarm that fires on a healthy night trains readers to ignore the alarm
        that matters — so the quiet direction is pinned too."""
        idx = _idx()
        last = str(idx.max())[:10]
        names = pd.DataFrame({"STAYS": _ramp(idx)}, index=idx)
        etfs = pd.DataFrame({g.BENCH: _ramp(idx, 400.0, 0.1)}, index=idx)
        boards = [_board(_D[0], ["STAYS"]), _board(last, ["STAYS"])]

        cont = g.continuity_block(boards, names, etfs)
        assert cont["n_stale_sessions"] == 0
        assert g.warn_if_stale(cont) is False
        assert not [ln for ln in capsys.readouterr().out.splitlines()
                    if ln.startswith("::warning")]

    def test_the_clock_is_not_the_boards_own_price_source(self):
        """ANTI-CIRCULARITY. A build that never ran leaves the board AND its breadth
        prices frozen together; measuring staleness against the board's own panel then
        reads as perfectly fresh. The benchmark ETF is refreshed by a different lane,
        so it still moves when the board lane is dead."""
        frozen = _idx(end="2026-06-30")
        fresh = _idx(end="2026-07-10")
        names = pd.DataFrame({"STAYS": _ramp(frozen)}, index=frozen)   # frozen with it
        etfs = pd.DataFrame({g.BENCH: _ramp(fresh, 400.0, 0.1)}, index=fresh)
        boards = [_board(_D[3], ["STAYS"])]                            # as_of 2026-06-30

        cont = g.continuity_block(boards, names, etfs)
        assert cont["clock"] == f"{g.BENCH} close"
        assert cont["last_session"] == str(fresh.max())[:10]
        assert cont["n_stale_sessions"] > 0, (
            "staleness measured against the board's own frozen panel — the outage "
            "would be invisible exactly when it matters")

    def test_the_gap_is_disclosed_in_the_artifact_and_never_backfilled(self):
        boards, names, etfs = self._stale()
        doc = g.emit_ledger(boards, names, etfs)
        cont = doc["meta"]["continuity"]

        assert cont["n_stale_sessions"] == len(cont["stale_sessions"]) or \
            cont["n_stale_sessions"] >= len(cont["stale_sessions"])
        assert cont["note_en"] and cont["note_zh"], "bilingual disclosure is required"
        # NO snapshot is invented for a session the board did not run on
        logged = {r["d"] for r in doc["rows"]}
        assert not (logged & set(cont["stale_sessions"])), (
            "a row was anchored to a session with no board — that is a backfill")
        assert set(logged) <= {b["as_of"] for b in boards}

    def test_a_current_ledger_carries_no_continuity_block(self):
        """Absent key on a healthy night → the dialog renders exactly as before."""
        idx = _idx()
        last = str(idx.max())[:10]
        names = pd.DataFrame({"STAYS": _ramp(idx)}, index=idx)
        etfs = pd.DataFrame({g.BENCH: _ramp(idx, 400.0, 0.1)}, index=idx)
        doc = g.emit_ledger([_board(_D[0], ["STAYS"]), _board(last, ["STAYS"])],
                            names, etfs)
        assert "continuity" not in doc["meta"]


# --------------------------------------------------------------------------- #
# Section 4 — the dialog says it in plain words
# --------------------------------------------------------------------------- #
_DLG = (ROOT / "templates" / "_track_record_dlg.html.j2").read_text()


class TestDialogSurfacesIt:
    def test_the_unscored_status_has_a_word_in_both_languages(self):
        """A status the emitter writes but the dictionary lacks falls through to the
        raw slug (`mp[st]||st`) — 'unscored' printing at the glance tier is exactly the
        slug leak the doctrine bans."""
        assert "unscored:'No price data'" in _DLG
        assert "unscored:'无价格数据'" in _DLG
        assert "unscored:L('unscored')" in _DLG
        assert "unscored:'trd-dot-flat'" in _DLG

    def test_the_outage_line_reads_the_artifacts_continuity_block(self):
        assert "(DATA.meta || {}).continuity" in _DLG
        assert "cont.n_stale_sessions" in _DLG
        assert "cont.note_zh" in _DLG and "cont.note_en" in _DLG

    def test_the_outage_line_is_absent_when_there_is_no_gap(self):
        """The guard must be on the COUNT, not merely on the key's presence — a
        continuity block reporting zero stale sessions must print nothing."""
        i = _DLG.index("(DATA.meta || {}).continuity")
        block = _DLG[i:i + 400]
        assert "if(cont && cont.n_stale_sessions)" in block
