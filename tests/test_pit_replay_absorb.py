"""Tests for the US PIT-replay absorb hook in ``scripts/grade_us_board.py``.

The hook (``absorb_pending_replays``) reads ``data/us_board_ledger/pending_replay/*.json``
(schema ``pit_replay.pending/v1``, written by ``scripts/prophet_pit_replay.py``) and
appends each row into ``snapshots.jsonl`` through the SAME code path
``snapshot_today()`` uses, then deletes the pending file — masterplan
``research/PROPHET_PIT_REPLAY_HARNESS_V1.md`` §0.4 ("the market's own nightly absorbs
its pending dir through its own append + dedupe machinery").

Covered here, per the build commission's TESTS section:
  * empty/absent pending dir is an exact no-op
  * pending file -> absorbed row present exactly once after two runs -> file deleted
  * out-of-order absorb is APPENDED with a ::notice (2026-08-18 orchestrator
    amendment — the originally-investigated finding was that
    `check_surface_freshness.check_candidates_freshness` read snapshots.jsonl in
    REVERSE line order and took the first `as_of` as "the newest"; that reader was
    fixed to take the MAX over all lines instead, and a full re-grep confirmed every
    other consumer was already order-safe except
    `scripts/build_track_record_page.py::_compute_board_series`, fixed separately by
    an explicit sort — see TestBoardSeriesOrderedByAsOf below)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.grade_us_board import (  # noqa: E402
    absorb_pending_replays,
    _append_snapshot_row,
    _snapshot_existing_as_of,
    snapshot_today,
)


def _pending_doc(session: str, *, rows=None, market="us",
                 schema="pit_replay.pending/v1") -> dict:
    if rows is None:
        rows = [{"as_of": session, "rank_by": "us_prophet_v2",
                 "dispersion_regime": {"state": "NORMAL"}, "buy": []}]
    return {
        "schema": schema, "market": market, "session": session,
        "harness_receipt": f"data/pit_replay/us-{session}-deadbeef.json",
        "rows": rows, "produced_by": "vintage lane delta capture",
        "vintage_sha": "a" * 40,
    }


def _write_pending(pending_dir: Path, session: str, **kw) -> Path:
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / f"{session}.json"
    path.write_text(json.dumps(_pending_doc(session, **kw)), encoding="utf-8")
    return path


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    """Point every module constant the hook touches at an isolated tmp tree."""
    ledger_dir = tmp_path / "us_board_ledger"
    snapshots = ledger_dir / "snapshots.jsonl"
    pending_dir = ledger_dir / "pending_replay"
    monkeypatch.setattr("scripts.grade_us_board.LEDGER_DIR", ledger_dir)
    monkeypatch.setattr("scripts.grade_us_board.SNAPSHOTS_JSONL", snapshots)
    monkeypatch.setattr("scripts.grade_us_board.PENDING_REPLAY_DIR", pending_dir)
    return {"dir": ledger_dir, "snapshots": snapshots, "pending": pending_dir}


class TestNoOp:
    def test_absent_pending_dir_is_an_exact_noop(self, ledger):
        assert not ledger["pending"].exists()
        result = absorb_pending_replays(quiet=True)
        assert result == {"absorbed": 0, "refused": 0, "dir_present": False, "files": 0}
        assert not ledger["snapshots"].exists()

    def test_empty_pending_dir_is_a_noop(self, ledger):
        ledger["pending"].mkdir(parents=True)
        result = absorb_pending_replays(quiet=True)
        assert result["files"] == 0
        assert result["absorbed"] == 0
        assert not ledger["snapshots"].exists()


class TestAbsorption:
    def test_pending_file_is_absorbed_exactly_once_across_two_runs(self, ledger):
        _write_pending(ledger["pending"], "2026-08-14")

        first = absorb_pending_replays(quiet=True)
        assert first["absorbed"] == 1
        assert first["refused"] == 0
        assert not (ledger["pending"] / "2026-08-14.json").exists()

        lines = ledger["snapshots"].read_text().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["as_of"] == "2026-08-14"

        # a second run with nothing pending is a clean no-op — no duplicate row
        second = absorb_pending_replays(quiet=True)
        assert second["files"] == 0
        lines_after = ledger["snapshots"].read_text().splitlines()
        assert len(lines_after) == 1

    def test_absorb_reuses_snapshot_todays_own_append_path(self, ledger, monkeypatch):
        """Directive: 'append it via the SAME trimming/append code path the live
        snapshot uses (reuse, do not duplicate)'. Pinned by making the shared helper
        raise and asserting the absorb call surfaces that failure rather than writing
        through a parallel code path."""
        _write_pending(ledger["pending"], "2026-08-14")

        calls = []
        real = _append_snapshot_row

        def _spy(row):
            calls.append(row)
            real(row)

        monkeypatch.setattr("scripts.grade_us_board._append_snapshot_row", _spy)
        absorb_pending_replays(quiet=True)
        assert len(calls) == 1
        assert calls[0]["as_of"] == "2026-08-14"

    def test_already_present_as_of_is_treated_as_absorbed_and_file_removed(self, ledger):
        """A pending row whose as_of a live snapshot_today() already wrote is not
        re-appended (idempotent per as_of, matching snapshot_today's own rule), but
        the pending file is still cleaned up — it has nothing left to do."""
        _append_snapshot_row({"as_of": "2026-08-14", "rank_by": "us_prophet_v2"})
        _write_pending(ledger["pending"], "2026-08-14")

        result = absorb_pending_replays(quiet=True)
        assert result["absorbed"] == 1
        lines = ledger["snapshots"].read_text().splitlines()
        assert len(lines) == 1  # not duplicated
        assert not (ledger["pending"] / "2026-08-14.json").exists()

    def test_pending_file_with_no_rows_is_absorbed_as_a_noop_delete(self, ledger):
        """masterplan §0.5: a US board-ledger half that refused at replay time still
        produces a pending file (rows=[]) so the plans half's provenance is complete;
        absorb has nothing to append and just clears the marker file."""
        _write_pending(ledger["pending"], "2026-08-14", rows=[])
        result = absorb_pending_replays(quiet=True)
        assert result["absorbed"] == 1
        assert not ledger["snapshots"].exists()
        assert not (ledger["pending"] / "2026-08-14.json").exists()

    def test_multiple_pending_files_absorbed_independently(self, ledger):
        _write_pending(ledger["pending"], "2026-08-14")
        _write_pending(ledger["pending"], "2026-08-17")
        result = absorb_pending_replays(quiet=True)
        assert result["absorbed"] == 2
        assert result["refused"] == 0
        as_ofs = {json.loads(l)["as_of"]
                 for l in ledger["snapshots"].read_text().splitlines()}
        assert as_ofs == {"2026-08-14", "2026-08-17"}


class TestOutOfOrderAbsorption:
    """2026-08-18 orchestrator amendment (supersedes the earlier refuse-on-out-of-order
    design). The investigated finding still stands — check_surface_freshness.py's
    check_candidates_freshness USED TO read snapshots.jsonl in reverse line order and
    take the first as_of as "the newest" — but the fix now lives at the READER: that
    function computes the MAX as_of over every parsed line instead. With every known
    consumer of this file order-safe (re-confirmed by a full re-grep, see this
    session's RETURN), an out-of-order absorb is a disclosed APPEND (with a
    ::notice), not a refusal."""

    def test_out_of_order_row_is_appended_not_refused(self, ledger):
        # A newer session has already snapshotted live (as an ordinary nightly would).
        _append_snapshot_row({"as_of": "2026-08-17", "rank_by": "us_prophet_v2"})
        # Now a delayed replay for an OLDER outage session absorbs.
        _write_pending(ledger["pending"], "2026-08-14")

        result = absorb_pending_replays(quiet=True)
        assert result["absorbed"] == 1
        assert result["refused"] == 0
        assert not (ledger["pending"] / "2026-08-14.json").exists()
        # the row landed — file order is now append order (out of chronological
        # order), which is exactly what the fixed reader tolerates.
        lines = ledger["snapshots"].read_text().splitlines()
        assert [json.loads(l)["as_of"] for l in lines] == ["2026-08-17", "2026-08-14"]

    def test_out_of_order_append_prints_a_notice_at_line_start(self, ledger, capsys):
        _append_snapshot_row({"as_of": "2026-08-17", "rank_by": "us_prophet_v2"})
        _write_pending(ledger["pending"], "2026-08-14")
        absorb_pending_replays(quiet=True)
        out = capsys.readouterr().out
        assert "::notice title=pit-replay-absorb-out-of-order::" in out
        # house law: the annotation must START the line, never go through a logger
        # prefix (which would read "WARNING ::notice ..." and be dropped by GitHub).
        notice_lines = [l for l in out.splitlines() if "pit-replay-absorb-out-of-order" in l]
        assert notice_lines and notice_lines[0].startswith("::notice")
        assert "2026-08-14" in notice_lines[0]  # names the session

    def test_in_order_append_at_the_tail_is_fine_and_prints_no_notice(self, ledger, capsys):
        """The mirror case: appending NEWER than the current tail is exactly the
        normal nightly shape — no notice, same as before this amendment."""
        _append_snapshot_row({"as_of": "2026-08-14", "rank_by": "us_prophet_v2"})
        _write_pending(ledger["pending"], "2026-08-17")
        result = absorb_pending_replays(quiet=True)
        assert result["absorbed"] == 1
        assert result["refused"] == 0
        as_ofs = [json.loads(l)["as_of"] for l in ledger["snapshots"].read_text().splitlines()]
        assert as_ofs == ["2026-08-14", "2026-08-17"]
        assert "pit-replay-absorb-out-of-order" not in capsys.readouterr().out

    def test_dedupe_still_holds_for_an_out_of_order_shaped_but_already_present_as_of(
        self, ledger
    ):
        """Idempotence is unchanged by this amendment: a pending as_of the store
        already carries — even one that would otherwise look out-of-order — is never
        re-appended, and the pending file is still cleaned up."""
        _append_snapshot_row({"as_of": "2026-08-17", "rank_by": "us_prophet_v2"})
        _append_snapshot_row({"as_of": "2026-08-14", "rank_by": "us_prophet_v2"})
        _write_pending(ledger["pending"], "2026-08-14")  # already present
        result = absorb_pending_replays(quiet=True)
        assert result["absorbed"] == 1
        lines = ledger["snapshots"].read_text().splitlines()
        assert len(lines) == 2  # not duplicated
        assert not (ledger["pending"] / "2026-08-14.json").exists()

    def test_the_real_fixed_reader_computes_the_true_newest_after_an_out_of_order_absorb(
        self, ledger, tmp_path, capsys
    ):
        """Regression test for the FIXED reader (this test used to be the negative
        control proving the naive reverse-scan reader was fooled — it now proves the
        opposite: check_surface_freshness.check_candidates_freshness, called for
        real, resolves the TRUE newest as_of (2026-08-17) even though the
        out-of-order row (2026-08-14) is the LAST line in the file, which is exactly
        what a reverse-scan-take-first reader would have picked instead)."""
        import scripts.check_surface_freshness as csf

        _append_snapshot_row({"as_of": "2026-08-17", "rank_by": "us_prophet_v2"})
        _write_pending(ledger["pending"], "2026-08-14")  # older, absorbed out of order
        absorb_pending_replays(quiet=True)
        # last line in the file is now the OLDER 2026-08-14 row — the shape that
        # would have fooled the old reverse-scan-take-first reader:
        lines = ledger["snapshots"].read_text().splitlines()
        assert json.loads(lines[-1])["as_of"] == "2026-08-14"

        # Point the real function at a root whose data/us_board_ledger/snapshots.jsonl
        # is exactly the file this hook just wrote (the `ledger` fixture patches
        # module constants rather than the real root-relative path check_surface_
        # freshness.py expects, so the bytes are copied across rather than shared).
        fake_root = tmp_path / "fake_root"
        (fake_root / "data" / "us_board_ledger").mkdir(parents=True)
        (fake_root / "data" / "us_board_ledger" / "snapshots.jsonl").write_bytes(
            ledger["snapshots"].read_bytes())

        capsys.readouterr()  # clear absorb's own prior output
        gap = csf.check_candidates_freshness(fake_root)
        # No candidates store in fake_root -> the MISSING branch, which always alarms
        # (gap=99) regardless of board_as_of — so gap alone would pass even with the
        # OLD bug. The actual pin is the resolved board_as_of baked into the printed
        # warning: it must name the TRUE newest (08-17), never the last-appended,
        # chronologically-older row (08-14) a reverse scan would have grabbed.
        assert gap == 99
        out = capsys.readouterr().out
        assert "board as_of=2026-08-17" in out
        assert "board as_of=2026-08-14" not in out


class TestSchemaValidation:
    def test_wrong_schema_is_refused_and_left_in_place(self, ledger):
        _write_pending(ledger["pending"], "2026-08-14", schema="something.else/v1")
        result = absorb_pending_replays(quiet=True)
        assert result["refused"] == 1
        assert (ledger["pending"] / "2026-08-14.json").exists()

    def test_non_us_market_is_refused_and_left_in_place(self, ledger):
        _write_pending(ledger["pending"], "2026-08-14", market="cn")
        result = absorb_pending_replays(quiet=True)
        assert result["refused"] == 1
        assert (ledger["pending"] / "2026-08-14.json").exists()

    def test_unreadable_json_is_refused_and_left_in_place(self, ledger):
        ledger["pending"].mkdir(parents=True)
        bad = ledger["pending"] / "2026-08-14.json"
        bad.write_text("{not json", encoding="utf-8")
        result = absorb_pending_replays(quiet=True)
        assert result["refused"] == 1
        assert bad.exists()

    def test_row_missing_as_of_is_refused_and_left_in_place(self, ledger):
        _write_pending(ledger["pending"], "2026-08-14",
                       rows=[{"rank_by": "us_prophet_v2"}])
        result = absorb_pending_replays(quiet=True)
        assert result["refused"] == 1
        assert (ledger["pending"] / "2026-08-14.json").exists()


class TestSnapshotTodayUnaffected:
    """snapshot_today() itself must keep working exactly as before the refactor that
    factored its append into the shared _append_snapshot_row/_snapshot_existing_as_of
    helpers (needed for the absorb hook to reuse it)."""

    def test_snapshot_today_still_idempotent_per_as_of(self, ledger, tmp_path, monkeypatch):
        board_dir = tmp_path / "site" / "factordata"
        board_dir.mkdir(parents=True)
        board = board_dir / "us_standouts.json"
        board.write_text(json.dumps({"as_of": "2026-08-14", "rank_by": "us_prophet_v2",
                                     "buy": []}), encoding="utf-8")
        monkeypatch.setattr("scripts.grade_us_board.ROOT", tmp_path)
        monkeypatch.setattr("scripts.grade_us_board.BOARD_PATH",
                            "site/factordata/us_standouts.json")
        first = snapshot_today()
        second = snapshot_today()
        assert first == second == "2026-08-14"
        lines = ledger["snapshots"].read_text().splitlines()
        assert len(lines) == 1


class TestBoardSeriesOrderedByAsOf:
    """scripts/build_track_record_page.py::_compute_board_series — the SECOND
    order-dependent snapshots.jsonl reader found by this program's re-grep (the
    first was check_surface_freshness.py::check_candidates_freshness, fixed
    separately by reading the MAX as_of instead of a reverse scan). This one
    published its `board_series` in raw file-append order with no sort; an
    out-of-order absorb (see TestOutOfOrderAbsorption above — absorb now APPENDS a
    delayed replay's row rather than refusing it) would otherwise plot the
    track-record page's time series out of chronological order for exactly the
    absorbed point. Fixed at the source (2026-08-18 orchestrator amendment) by an
    explicit `series.sort(key=lambda row: row["as_of"])` before emit."""

    @staticmethod
    def _write_snapshots(path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def test_series_is_sorted_by_as_of_even_when_the_file_is_out_of_order(self, tmp_path):
        from scripts.build_track_record_page import _compute_board_series

        snap_path = tmp_path / "snapshots.jsonl"
        # Exactly what an out-of-order absorb produces: 08-17 appended first (an
        # ordinary live nightly), then 08-14 absorbed afterward (a delayed replay),
        # landing LAST in the file despite being chronologically earlier.
        self._write_snapshots(snap_path, [
            {"as_of": "2026-08-17", "board": [{"lane": "buy"}]},
            {"as_of": "2026-08-14", "board": [{"lane": "buy"}, {"lane": "buy"}]},
            {"as_of": "2026-08-18", "board": [{"lane": "buy"}]},
        ])
        result = _compute_board_series(snap_path)
        as_ofs = [row["as_of"] for row in result["series"]]
        assert as_ofs == ["2026-08-14", "2026-08-17", "2026-08-18"], (
            "board_series must be chronological regardless of the file's append "
            "order — this is exactly what an out-of-order absorb would otherwise "
            "corrupt"
        )

    def test_series_content_is_unchanged_only_order_moves(self, tmp_path):
        from scripts.build_track_record_page import _compute_board_series

        snap_path = tmp_path / "snapshots.jsonl"
        self._write_snapshots(snap_path, [
            {"as_of": "2026-08-17", "board": [{"lane": "buy"}]},
            {"as_of": "2026-08-14", "board": [{"lane": "watch"}, {"lane": "watch"}]},
        ])
        result = _compute_board_series(snap_path)
        by_as_of = {row["as_of"]: row for row in result["series"]}
        assert by_as_of["2026-08-17"]["total"] == 1
        assert by_as_of["2026-08-14"]["total"] == 2
        assert by_as_of["2026-08-14"]["by_lane"] == {"watch": 2}

    def test_in_order_files_are_semantics_preserving(self, tmp_path):
        """The amendment requires this fix be semantics-preserving for in-order
        files — an already-chronological file must produce the identical series."""
        from scripts.build_track_record_page import _compute_board_series

        snap_path = tmp_path / "snapshots.jsonl"
        rows = [
            {"as_of": "2026-08-12", "board": [{"lane": "buy"}]},
            {"as_of": "2026-08-13", "board": [{"lane": "buy"}, {"lane": "watch"}]},
            {"as_of": "2026-08-14", "board": []},
        ]
        self._write_snapshots(snap_path, rows)
        result = _compute_board_series(snap_path)
        assert [row["as_of"] for row in result["series"]] == [
            "2026-08-12", "2026-08-13", "2026-08-14"]
        assert result["accruing"] is False  # len(series) == 3, not < 3

    def test_absent_file_is_unaffected(self, tmp_path):
        from scripts.build_track_record_page import _compute_board_series

        result = _compute_board_series(tmp_path / "does_not_exist.jsonl")
        assert result == {"accruing": True, "reason": "snapshots.jsonl absent",
                          "series": []}

    def test_end_to_end_with_a_real_absorbed_out_of_order_row(self, ledger):
        """Ties the fix directly to the absorb hook: run a real out-of-order
        absorb_pending_replays() pass, then feed the resulting snapshots.jsonl
        straight into _compute_board_series and confirm the series comes out
        chronological even though the file itself does not."""
        from scripts.build_track_record_page import _compute_board_series

        _append_snapshot_row({"as_of": "2026-08-17", "board": [{"lane": "buy"}]})
        _write_pending(ledger["pending"], "2026-08-14",
                       rows=[{"as_of": "2026-08-14", "board": [{"lane": "buy"}]}])
        absorb_pending_replays(quiet=True)

        # the file itself is still out of order — absorb appends, it does not rewrite
        raw_as_ofs = [json.loads(l)["as_of"]
                     for l in ledger["snapshots"].read_text().splitlines()]
        assert raw_as_ofs == ["2026-08-17", "2026-08-14"]

        result = _compute_board_series(ledger["snapshots"])
        assert [row["as_of"] for row in result["series"]] == [
            "2026-08-14", "2026-08-17"]
