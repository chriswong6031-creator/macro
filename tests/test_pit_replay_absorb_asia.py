"""Tests for the CN/HK PIT-replay absorb hooks and registry completion
(research/PROPHET_PIT_REPLAY_HARNESS_V1.md §0.4, §1) — this build's scope:

  * engine/china_standout_track.py::absorb_pending_replay (+ _merge_and_write)
  * engine/board_ledger.py::absorb_pending_replay (HK-only)
  * scripts/build_hk_pick_lab.py::absorb_pending_replay (via
    engine.pick_lab.ledger.append_fires, already public/reusable)
  * scripts/prophet_pit_replay.py's cn/hk MARKETS registry entries,
    _cn_session_valid / _hk_session_valid

Mirrors tests/test_pit_replay_absorb.py's pattern (the US absorb hook) for the
CN/HK/pick-lab absorb hooks this build adds. Fast, no real board builds, no
network — synthetic frames + tmp-dir fixtures only, except TestResolveOnlyRealRepo
(cheap real-repo `--resolve-only` checks: registry + gap-guard + vintage
resolution only, no board build — see scripts/prophet_pit_replay.py
_cmd_resolve_only).
"""
from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from lib import config  # noqa: E402
import engine.board_ledger as bl  # noqa: E402
import engine.china_standout_track as cst  # noqa: E402
import scripts.build_hk_pick_lab as bhpl  # noqa: E402
import scripts.prophet_pit_replay as ppr  # noqa: E402

PENDING_SCHEMA = "pit_replay.pending/v1"


def _pending_doc(market: str, session: str, rows: list, **kw) -> dict:
    return {
        "schema": PENDING_SCHEMA, "market": market, "session": session,
        "harness_receipt": f"data/pit_replay/{market}-{session}-deadbeef.json",
        "rows": rows, "produced_by": "vintage lane delta capture",
        "vintage_sha": "a" * 40, **kw,
    }


def _write_pending(pending_dir: Path, session: str, market: str, rows: list,
                   **kw) -> Path:
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / f"{session}.json"
    path.write_text(json.dumps(_pending_doc(market, session, rows, **kw)),
                    encoding="utf-8")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# CN board-ledger absorb — engine/china_standout_track.py
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def cn_store(tmp_path, monkeypatch):
    """Isolated CN board-track store; session guard defaulted to SETTLED
    (deterministic — the partial-session guard is covered separately)."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    import lib.store as lstore
    monkeypatch.setattr(lstore, "read_status", lambda: {})
    return tmp_path


def _cn_row(session: str, ticker: str, board_definition: str = "legacy",
           **extra) -> dict:
    row = {
        "date": session, "ticker": ticker, "board_rank": 1,
        "board_definition": board_definition, "lane": "featured",
        "prophet_score": 0.5,
    }
    row.update(extra)
    return row


class TestCNBoardAbsorb:
    def test_absent_pending_dir_is_an_exact_noop(self, cn_store):
        assert not cst._pending_replay_dir().exists()
        result = cst.absorb_pending_replay()
        assert result == {"absorbed_files": 0, "absorbed_rows": 0, "files": []}
        assert not cst._store_path().exists()

    def test_empty_pending_dir_is_a_noop(self, cn_store):
        cst._pending_replay_dir().mkdir(parents=True)
        result = cst.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert not cst._store_path().exists()

    def test_pending_file_absorbed_exactly_once_across_two_runs(self, cn_store):
        row = _cn_row("2026-08-17", "600000.SS")
        _write_pending(cst._pending_replay_dir(), "2026-08-17", "cn", [row])

        first = cst.absorb_pending_replay()
        assert first["absorbed_files"] == 1
        assert first["absorbed_rows"] == 1
        assert not (cst._pending_replay_dir() / "2026-08-17.json").exists()

        df = pd.read_parquet(cst._store_path())
        assert len(df) == 1
        assert df.iloc[0]["ticker"] == "600000.SS"

        # a second run with nothing pending is a clean no-op — no duplicate row
        second = cst.absorb_pending_replay()
        assert second["absorbed_files"] == 0
        assert len(pd.read_parquet(cst._store_path())) == 1

    def test_dedupe_key_respects_date_ticker_board_definition(self, cn_store):
        """A colliding (date, ticker, board_definition) row does not double —
        reuses append_board's own keep-first dedupe (via _merge_and_write), never
        a re-implementation of it."""
        cst.append_board([{"ticker": "600001.SS", "price": 10.0}],
                         asof="2026-08-17", lane="asia")
        assert len(pd.read_parquet(cst._store_path())) == 1

        row = _cn_row("2026-08-17", "600001.SS", prophet_score=0.99)  # colliding key
        _write_pending(cst._pending_replay_dir(), "2026-08-17", "cn", [row])
        cst.absorb_pending_replay()

        df = pd.read_parquet(cst._store_path())
        assert len(df) == 1  # keep-first: no duplicate row
        assert pd.isna(df.iloc[0]["prophet_score"])  # live row (score=None) wins

    def test_multiple_cohort_rows_in_one_pending_file_all_absorbed(self, cn_store):
        """masterplan §0.4: 'all cohorts' captured in one pending file — five
        board_definition cohorts share the (date, ticker, board_definition) key."""
        rows = [
            _cn_row("2026-08-17", "600000.SS", board_definition="legacy"),
            _cn_row("2026-08-17", "600000.SS", board_definition="cn_prophet_v2_shadow"),
            _cn_row("2026-08-17", "600000.SS", board_definition="cn_prophet_v3_shadow"),
            _cn_row("2026-08-17", "600001.SS", board_definition="reversal_watch"),
            _cn_row("2026-08-17", "600002.SS", board_definition="continuation_watch"),
        ]
        _write_pending(cst._pending_replay_dir(), "2026-08-17", "cn", rows)
        result = cst.absorb_pending_replay()
        assert result["absorbed_rows"] == 5
        assert len(pd.read_parquet(cst._store_path())) == 5

    def test_pending_file_with_no_rows_is_a_noop_delete(self, cn_store):
        """masterplan §0.5: a half that refused at replay time still produces a
        pending file (rows=[]); absorb has nothing to append and clears the
        marker file."""
        _write_pending(cst._pending_replay_dir(), "2026-08-17", "cn", [])
        result = cst.absorb_pending_replay()
        assert result["absorbed_files"] == 1
        assert result["absorbed_rows"] == 0
        assert not cst._store_path().exists()
        assert not (cst._pending_replay_dir() / "2026-08-17.json").exists()

    def test_multiple_pending_files_absorbed_independently(self, cn_store):
        _write_pending(cst._pending_replay_dir(), "2026-08-14", "cn",
                       [_cn_row("2026-08-14", "600000.SS")])
        _write_pending(cst._pending_replay_dir(), "2026-08-17", "cn",
                       [_cn_row("2026-08-17", "600000.SS")])
        result = cst.absorb_pending_replay()
        assert result["absorbed_files"] == 2
        assert result["absorbed_rows"] == 2
        dates = set(pd.read_parquet(cst._store_path())["date"])
        assert dates == {"2026-08-14", "2026-08-17"}

    def test_append_board_calls_absorb_automatically(self, cn_store):
        """The absorb hook fires as a side effect of a normal live append — the
        seam chosen in engine/china_standout_track.py::append_board."""
        row = _cn_row("2026-08-14", "600002.SS")
        _write_pending(cst._pending_replay_dir(), "2026-08-14", "cn", [row])

        cst.append_board([{"ticker": "600003.SS", "price": 10.0}],
                         asof="2026-08-17", lane="asia")

        df = pd.read_parquet(cst._store_path())
        assert set(df["ticker"]) == {"600002.SS", "600003.SS"}
        assert not (cst._pending_replay_dir() / "2026-08-14.json").exists()

    def test_repeated_cohort_calls_absorb_at_most_once_effectively(self, cn_store):
        """The 5 real call sites in scripts/build_china_library.py each call
        append_board once per night; absorb runs on every one, but the pending
        dir is gone after the first, so repeats are provably free."""
        row = _cn_row("2026-08-14", "600002.SS")
        _write_pending(cst._pending_replay_dir(), "2026-08-14", "cn", [row])

        for _ in range(5):  # mirrors the 5 real cohort call sites
            cst.append_board([{"ticker": "600003.SS", "price": 10.0}],
                             asof="2026-08-17", lane="asia")

        df = pd.read_parquet(cst._store_path())
        # exactly one absorbed row + one live row per pass (keep-first on the live
        # row across the 5 repeated calls)
        assert set(df["ticker"]) == {"600002.SS", "600003.SS"}
        assert len(df) == 2

    def test_absorb_reuses_append_boards_own_dedupe_path(self, cn_store, monkeypatch):
        """Directive: absorb must reuse the SAME dedupe path, never duplicate it.
        Pinned by spying on _merge_and_write."""
        calls = []
        real = cst._merge_and_write

        def _spy(new):
            calls.append(len(new))
            return real(new)

        monkeypatch.setattr(cst, "_merge_and_write", _spy)
        row = _cn_row("2026-08-17", "600000.SS")
        _write_pending(cst._pending_replay_dir(), "2026-08-17", "cn", [row])
        cst.absorb_pending_replay()
        assert calls == [1]

    def test_unreadable_pending_json_is_left_in_place(self, cn_store):
        cst._pending_replay_dir().mkdir(parents=True)
        bad = cst._pending_replay_dir() / "2026-08-14.json"
        bad.write_text("{not json", encoding="utf-8")
        result = cst.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert bad.exists()


class TestCNAbsorbOrderingAndValidation:
    """Build commission F8/F9: stable-sort by date after keep-first dedupe, a
    pending-session ordering sanity check, and schema/market validation parity
    with the US absorb hook — all via bare ``print("::warning ...")``, never a
    logger (house law; tests/test_gh_annotation_line_start.py guards this)."""

    def test_absorb_of_an_older_session_lands_in_chronological_position(self, cn_store):
        """F8 TEST 1: absorb an older session -> rows land in chronological
        position and iloc[-1] is still the live newest."""
        # live nightly writes the NEWER session first (the ordinary shape)
        cst.append_board([{"ticker": "600099.SS", "price": 10.0}],
                         asof="2026-08-17", lane="asia")
        # a delayed replay absorbs an OLDER session afterward
        row = _cn_row("2026-08-14", "600000.SS")
        _write_pending(cst._pending_replay_dir(), "2026-08-14", "cn", [row])
        cst.absorb_pending_replay()

        df = pd.read_parquet(cst._store_path())
        assert list(df["date"]) == ["2026-08-14", "2026-08-17"], (
            "the older replay row must land in CHRONOLOGICAL position, not at "
            "the physical append tail"
        )
        assert df.iloc[-1]["ticker"] == "600099.SS", (
            "iloc[-1] (every positional consumer) must still resolve to the "
            "live, NEWEST row after an out-of-order absorb"
        )

    def test_pending_dated_not_older_than_store_max_is_refused_with_warning(
        self, cn_store, capsys
    ):
        """F8 TEST 2: a pending file dated >= the store max is refused with a
        warning — a replay is by definition a backfill for a PAST date."""
        cst.append_board([{"ticker": "600099.SS", "price": 10.0}],
                         asof="2026-08-14", lane="asia")
        row = _cn_row("2026-08-17", "600000.SS")  # NOT older than the store's tape
        _write_pending(cst._pending_replay_dir(), "2026-08-17", "cn", [row])

        result = cst.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (cst._pending_replay_dir() / "2026-08-17.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-not-older" in l]
        assert lines and lines[0].startswith("::warning")
        assert "2026-08-17" in lines[0]

    def test_live_shape_in_order_append_is_unaffected_by_the_sort(self, cn_store):
        """F8 TEST 3: an already-chronological (live) shape is semantics-preserving
        — the stable sort is a byte-level no-op when nothing was out of order."""
        cst.append_board([{"ticker": "600000.SS", "price": 10.0}],
                         asof="2026-08-14", lane="asia")
        cst.append_board([{"ticker": "600001.SS", "price": 10.0}],
                         asof="2026-08-17", lane="asia")
        df = pd.read_parquet(cst._store_path())
        assert list(df["date"]) == ["2026-08-14", "2026-08-17"]
        assert list(df["ticker"]) == ["600000.SS", "600001.SS"]

    def test_wrong_schema_is_refused_with_a_warning_and_left_in_place(self, cn_store, capsys):
        row = _cn_row("2026-08-14", "600000.SS")
        _write_pending(cst._pending_replay_dir(), "2026-08-14", "cn", [row],
                       schema="something.else/v1")
        result = cst.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (cst._pending_replay_dir() / "2026-08-14.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-schema" in l]
        assert lines and lines[0].startswith("::warning")

    def test_wrong_market_is_refused_with_a_warning_and_left_in_place(self, cn_store, capsys):
        row = _cn_row("2026-08-14", "600000.SS")
        _write_pending(cst._pending_replay_dir(), "2026-08-14", "us", [row])
        result = cst.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (cst._pending_replay_dir() / "2026-08-14.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-schema" in l]
        assert lines and lines[0].startswith("::warning")

    def test_a_raise_inside_the_merge_prints_a_warning_not_a_logger(
        self, cn_store, monkeypatch, capsys
    ):
        """F9: 'a row set that raises inside the merge -> same warning path' —
        i.e. the bare-print ::warning path, not log.warning (which GitHub would
        silently drop)."""
        def _boom(new):
            raise ValueError("synthetic merge failure")

        monkeypatch.setattr(cst, "_merge_and_write", _boom)
        row = _cn_row("2026-08-14", "600000.SS")
        _write_pending(cst._pending_replay_dir(), "2026-08-14", "cn", [row])
        result = cst.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (cst._pending_replay_dir() / "2026-08-14.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-failed" in l]
        assert lines and lines[0].startswith("::warning")


# ─────────────────────────────────────────────────────────────────────────────
# HK board-ledger absorb — engine/board_ledger.py (HK only; CA untouched)
# ─────────────────────────────────────────────────────────────────────────────

def _hk_row(ticker: str = "0700.HK", **extra) -> dict:
    row = {"ticker": ticker, "group": "entry_open", "edge_z": 1.5,
          "gate_tier": "T1", "align_tier": "aligned", "entry_state": "open",
          "close_asof": 380.0, "board_definition": "hk_prophet_v1"}
    row.update(extra)
    return row


@pytest.fixture()
def hk_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")
    monkeypatch.setattr(bl, "_pending_replay_dir", lambda: tmp_path / "pending_replay")
    monkeypatch.setenv("CN_LANE", "asia")
    return tmp_path


class TestHKBoardAbsorb:
    def test_absent_pending_dir_is_an_exact_noop(self, hk_ledger):
        result = bl.absorb_pending_replay()
        assert result == {"absorbed_files": 0, "absorbed_rows": 0, "files": []}

    def test_empty_pending_dir_is_a_noop(self, hk_ledger):
        (hk_ledger / "pending_replay").mkdir(parents=True)
        result = bl.absorb_pending_replay()
        assert result["absorbed_files"] == 0

    def test_pending_file_absorbed_exactly_once_across_two_runs(self, hk_ledger):
        row = {"date": "2026-08-17", "market": "HK", **_hk_row()}
        _write_pending(hk_ledger / "pending_replay", "2026-08-17", "hk", [row])

        first = bl.absorb_pending_replay()
        assert first["absorbed_files"] == 1
        assert first["absorbed_rows"] == 1
        assert not (hk_ledger / "pending_replay" / "2026-08-17.json").exists()

        df = pd.read_parquet(bl._store_path("HK"))
        assert len(df) == 1

        second = bl.absorb_pending_replay()
        assert second["absorbed_files"] == 0
        assert len(pd.read_parquet(bl._store_path("HK"))) == 1

    def test_dedupe_key_respects_date_ticker(self, hk_ledger):
        bl.append_board([_hk_row(ticker="0005.HK")], "HK", asof="2026-08-17")
        assert len(pd.read_parquet(bl._store_path("HK"))) == 1

        row = {"date": "2026-08-17", "market": "HK",
              **_hk_row(ticker="0005.HK", edge_z=9.9)}  # colliding key
        _write_pending(hk_ledger / "pending_replay", "2026-08-17", "hk", [row])
        bl.absorb_pending_replay()

        df = pd.read_parquet(bl._store_path("HK"))
        assert len(df) == 1
        assert float(df.iloc[0]["edge_z"]) != 9.9  # keep-first: live row wins

    def test_pending_file_with_no_rows_is_a_noop_delete(self, hk_ledger):
        _write_pending(hk_ledger / "pending_replay", "2026-08-17", "hk", [])
        result = bl.absorb_pending_replay()
        assert result["absorbed_files"] == 1
        assert not bl._store_path("HK").exists()

    def test_append_board_calls_absorb_only_for_hk_not_ca(self, hk_ledger, monkeypatch):
        """Guarded to the HK/asia lane pass — arming CA's own lane gate too so its
        append actually reaches the tail proves the ``if m == 'HK'`` guard, not
        just an earlier off-lane refusal."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        row = {"date": "2026-08-14", "market": "HK", **_hk_row(ticker="0011.HK")}
        _write_pending(hk_ledger / "pending_replay", "2026-08-14", "hk", [row])

        n = bl.append_board([_hk_row(ticker="0012.HK")], "CA", asof="2026-08-17")
        assert n == 1  # CA append actually succeeded (lane armed)
        assert (hk_ledger / "pending_replay" / "2026-08-14.json").exists()

        bl.append_board([_hk_row(ticker="0013.HK")], "HK", asof="2026-08-17")
        assert not (hk_ledger / "pending_replay" / "2026-08-14.json").exists()

    def test_absorb_reuses_append_boards_own_dedupe_path(self, hk_ledger, monkeypatch):
        calls = []
        real = bl._merge_and_write

        def _spy(market, new):
            calls.append((market, len(new)))
            return real(market, new)

        monkeypatch.setattr(bl, "_merge_and_write", _spy)
        row = {"date": "2026-08-17", "market": "HK", **_hk_row()}
        _write_pending(hk_ledger / "pending_replay", "2026-08-17", "hk", [row])
        bl.absorb_pending_replay()
        assert calls == [("HK", 1)]


class TestHKAbsorbOrderingAndValidation:
    """Build commission F8/F9 — HK mirror of TestCNAbsorbOrderingAndValidation."""

    def test_absorb_of_an_older_session_lands_in_chronological_position(self, hk_ledger):
        bl.append_board([_hk_row(ticker="0099.HK")], "HK", asof="2026-08-17")
        row = {"date": "2026-08-14", "market": "HK", **_hk_row(ticker="0700.HK")}
        _write_pending(hk_ledger / "pending_replay", "2026-08-14", "hk", [row])
        bl.absorb_pending_replay()

        df = pd.read_parquet(bl._store_path("HK"))
        assert list(df["date"]) == ["2026-08-14", "2026-08-17"]
        assert df.iloc[-1]["ticker"] == "0099.HK"

    def test_pending_dated_not_older_than_store_max_is_refused_with_warning(
        self, hk_ledger, capsys
    ):
        bl.append_board([_hk_row(ticker="0099.HK")], "HK", asof="2026-08-14")
        row = {"date": "2026-08-17", "market": "HK", **_hk_row(ticker="0700.HK")}
        _write_pending(hk_ledger / "pending_replay", "2026-08-17", "hk", [row])

        result = bl.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (hk_ledger / "pending_replay" / "2026-08-17.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-not-older" in l]
        assert lines and lines[0].startswith("::warning")

    def test_live_shape_in_order_append_is_unaffected_by_the_sort(self, hk_ledger):
        bl.append_board([_hk_row(ticker="0005.HK")], "HK", asof="2026-08-14")
        bl.append_board([_hk_row(ticker="0700.HK")], "HK", asof="2026-08-17")
        df = pd.read_parquet(bl._store_path("HK"))
        assert list(df["date"]) == ["2026-08-14", "2026-08-17"]
        assert list(df["ticker"]) == ["0005.HK", "0700.HK"]

    def test_wrong_schema_is_refused_with_a_warning_and_left_in_place(self, hk_ledger, capsys):
        row = {"date": "2026-08-14", "market": "HK", **_hk_row()}
        _write_pending(hk_ledger / "pending_replay", "2026-08-14", "hk", [row],
                       schema="something.else/v1")
        result = bl.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (hk_ledger / "pending_replay" / "2026-08-14.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-schema" in l]
        assert lines and lines[0].startswith("::warning")

    def test_wrong_market_is_refused_with_a_warning_and_left_in_place(self, hk_ledger, capsys):
        row = {"date": "2026-08-14", "market": "HK", **_hk_row()}
        _write_pending(hk_ledger / "pending_replay", "2026-08-14", "cn", [row])
        result = bl.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (hk_ledger / "pending_replay" / "2026-08-14.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-schema" in l]
        assert lines and lines[0].startswith("::warning")

    def test_a_raise_inside_the_merge_prints_a_warning_not_a_logger(
        self, hk_ledger, monkeypatch, capsys
    ):
        def _boom(market, new):
            raise ValueError("synthetic merge failure")

        monkeypatch.setattr(bl, "_merge_and_write", _boom)
        row = {"date": "2026-08-14", "market": "HK", **_hk_row()}
        _write_pending(hk_ledger / "pending_replay", "2026-08-14", "hk", [row])
        result = bl.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (hk_ledger / "pending_replay" / "2026-08-14.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-failed" in l]
        assert lines and lines[0].startswith("::warning")


# ─────────────────────────────────────────────────────────────────────────────
# HK pick-lab absorb — scripts/build_hk_pick_lab.py, via the already-public
# engine.pick_lab.ledger.append_fires (no dedupe re-implementation needed)
# ─────────────────────────────────────────────────────────────────────────────

def _fire_row(engine_id: str = "hk_flagship", ticker: str = "0700.HK",
             fire_date: str = "2026-08-17", **extra) -> dict:
    row = {"engine_id": engine_id, "ticker": ticker, "fire_date": fire_date,
          "authority": "display_only", "entry_px": 380.0}
    row.update(extra)
    return row


@pytest.fixture()
def hk_pick_lab_profile(tmp_path, monkeypatch):
    from engine.pick_lab.profile import HK_PROFILE
    import engine.pick_lab.profile as profile_mod
    test_profile = dataclasses.replace(
        HK_PROFILE,
        fires_path=tmp_path / "fires.jsonl",
        grades_path=tmp_path / "grades.jsonl",
        lh_fires_path=tmp_path / "lh_fires.jsonl",
        lh_grades_path=tmp_path / "lh_grades.jsonl",
    )
    monkeypatch.setattr(profile_mod, "HK_PROFILE", test_profile)
    monkeypatch.setattr(bhpl, "_pending_replay_dir", lambda: tmp_path / "pending_replay")
    return tmp_path, test_profile


class TestHKPickLabAbsorb:
    def test_absent_pending_dir_is_an_exact_noop(self, hk_pick_lab_profile):
        result = bhpl.absorb_pending_replay()
        assert result == {"absorbed_files": 0, "absorbed_rows": 0, "files": []}

    def test_empty_pending_dir_is_a_noop(self, hk_pick_lab_profile):
        tmp_path, _ = hk_pick_lab_profile
        (tmp_path / "pending_replay").mkdir(parents=True)
        result = bhpl.absorb_pending_replay()
        assert result["absorbed_files"] == 0

    def test_pending_file_absorbed_exactly_once_across_two_runs(self, hk_pick_lab_profile):
        tmp_path, profile = hk_pick_lab_profile
        _write_pending(tmp_path / "pending_replay", "2026-08-17", "hk", [_fire_row()])

        first = bhpl.absorb_pending_replay()
        assert first["absorbed_files"] == 1
        assert first["absorbed_rows"] == 1
        assert not (tmp_path / "pending_replay" / "2026-08-17.json").exists()

        from engine.pick_lab.ledger import load_fires
        fires = load_fires(profile=profile)
        assert len(fires) == 1
        assert fires[0]["ticker"] == "0700.HK"

        second = bhpl.absorb_pending_replay()
        assert second["absorbed_files"] == 0
        assert len(load_fires(profile=profile)) == 1

    def test_dedupe_key_respects_engine_ticker_fire_date(self, hk_pick_lab_profile):
        tmp_path, profile = hk_pick_lab_profile
        from engine.pick_lab.ledger import append_fires, load_fires
        append_fires([_fire_row(entry_px=1.0)], profile=profile)  # live row first

        row = _fire_row(entry_px=999.0)  # colliding (engine_id, ticker, fire_date)
        _write_pending(tmp_path / "pending_replay", "2026-08-17", "hk", [row])
        bhpl.absorb_pending_replay()

        fires = load_fires(profile=profile)
        assert len(fires) == 1  # not duplicated
        assert fires[0]["entry_px"] == 1.0  # keep-first: live row wins

    def test_pending_file_with_no_rows_is_a_noop_delete(self, hk_pick_lab_profile):
        tmp_path, profile = hk_pick_lab_profile
        _write_pending(tmp_path / "pending_replay", "2026-08-17", "hk", [])
        result = bhpl.absorb_pending_replay()
        assert result["absorbed_files"] == 1
        from engine.pick_lab.ledger import load_fires
        assert load_fires(profile=profile) == []

    def test_absorb_reuses_append_fires_public_api_never_duplicates_dedupe(
        self, hk_pick_lab_profile, monkeypatch
    ):
        calls = []
        import engine.pick_lab.ledger as ledger_mod
        real = ledger_mod.append_fires

        def _spy(fires, **kw):
            calls.append(len(fires))
            return real(fires, **kw)

        monkeypatch.setattr(ledger_mod, "append_fires", _spy)
        tmp_path, _profile = hk_pick_lab_profile
        _write_pending(tmp_path / "pending_replay", "2026-08-17", "hk", [_fire_row()])
        bhpl.absorb_pending_replay()
        assert calls == [1]


class TestHKPickLabAbsorbValidation:
    """Coordinator amendment: F9 parity (schema/market) + F8-style staleness for
    scripts/build_hk_pick_lab.py::absorb_pending_replay, mirroring the CN/HK board
    absorbs' validation shape."""

    def test_wrong_schema_is_refused_with_a_warning_and_left_in_place(
        self, hk_pick_lab_profile, capsys
    ):
        tmp_path, _profile = hk_pick_lab_profile
        _write_pending(tmp_path / "pending_replay", "2026-08-17", "hk", [_fire_row()],
                       schema="something.else/v1")
        result = bhpl.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (tmp_path / "pending_replay" / "2026-08-17.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-schema" in l]
        assert lines and lines[0].startswith("::warning")

    def test_wrong_market_is_refused_with_a_warning_and_left_in_place(
        self, hk_pick_lab_profile, capsys
    ):
        tmp_path, _profile = hk_pick_lab_profile
        _write_pending(tmp_path / "pending_replay", "2026-08-17", "cn", [_fire_row()])
        result = bhpl.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (tmp_path / "pending_replay" / "2026-08-17.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-schema" in l]
        assert lines and lines[0].startswith("::warning")

    def test_valid_file_still_absorbs_exactly_as_before(self, hk_pick_lab_profile):
        """The F9/F8 additions must not regress the ordinary happy path."""
        tmp_path, profile = hk_pick_lab_profile
        _write_pending(tmp_path / "pending_replay", "2026-08-17", "hk", [_fire_row()])
        result = bhpl.absorb_pending_replay()
        assert result["absorbed_files"] == 1
        assert result["absorbed_rows"] == 1
        assert not (tmp_path / "pending_replay" / "2026-08-17.json").exists()
        from engine.pick_lab.ledger import load_fires
        fires = load_fires(profile=profile)
        assert len(fires) == 1
        assert fires[0]["ticker"] == "0700.HK"

    def test_a_raise_inside_append_fires_prints_a_warning_not_a_logger(
        self, hk_pick_lab_profile, monkeypatch, capsys
    ):
        import engine.pick_lab.ledger as ledger_mod

        def _boom(fires, **kw):
            raise ValueError("synthetic append_fires failure")

        monkeypatch.setattr(ledger_mod, "append_fires", _boom)
        tmp_path, _profile = hk_pick_lab_profile
        _write_pending(tmp_path / "pending_replay", "2026-08-17", "hk", [_fire_row()])
        result = bhpl.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (tmp_path / "pending_replay" / "2026-08-17.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-failed" in l]
        assert lines and lines[0].startswith("::warning")

    def test_a_pending_session_ahead_of_the_live_tape_is_refused_with_a_warning(
        self, hk_pick_lab_profile, capsys
    ):
        """F8-style staleness: a replay must not be pointed at a fire_date the live
        tape has not reached yet."""
        tmp_path, profile = hk_pick_lab_profile
        from engine.pick_lab.ledger import append_fires

        append_fires([_fire_row(fire_date="2026-08-14")], profile=profile)  # live
        _write_pending(tmp_path / "pending_replay", "2026-08-17", "hk",
                       [_fire_row(fire_date="2026-08-17", ticker="0005.HK")])

        result = bhpl.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert (tmp_path / "pending_replay" / "2026-08-17.json").exists()
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "pit-replay-absorb-not-older" in l]
        assert lines and lines[0].startswith("::warning")

    def test_a_pending_session_on_the_same_date_as_the_live_tape_still_absorbs(
        self, hk_pick_lab_profile
    ):
        """The staleness check is STRICT (>, not >=): a same-day fire_date collision
        across different tickers/engines is normal and must still absorb via the
        ordinary keep-first dedupe, not be refused as 'not older'."""
        tmp_path, profile = hk_pick_lab_profile
        from engine.pick_lab.ledger import append_fires, load_fires

        append_fires([_fire_row(fire_date="2026-08-17", ticker="0700.HK")],
                    profile=profile)  # live row
        _write_pending(tmp_path / "pending_replay", "2026-08-17", "hk",
                       [_fire_row(fire_date="2026-08-17", ticker="0005.HK")])  # same date

        result = bhpl.absorb_pending_replay()
        assert result["absorbed_files"] == 1
        assert result["absorbed_rows"] == 1
        fires = load_fires(profile=profile)
        assert {r["ticker"] for r in fires} == {"0700.HK", "0005.HK"}

    def test_unreadable_pending_json_is_left_in_place(self, hk_pick_lab_profile):
        tmp_path, _profile = hk_pick_lab_profile
        (tmp_path / "pending_replay").mkdir(parents=True)
        bad = tmp_path / "pending_replay" / "2026-08-14.json"
        bad.write_text("{not json", encoding="utf-8")
        result = bhpl.absorb_pending_replay()
        assert result["absorbed_files"] == 0
        assert bad.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Registry resolution — scripts/prophet_pit_replay.py MARKETS["cn"/"hk"]
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistryResolution:
    def test_cn_is_fully_resolved(self):
        entry = ppr.get_market_entry("cn")
        assert "unresolved" not in entry
        assert entry["board_relpath"] == "site/factordata/china_standouts.json"
        assert isinstance(entry["price_surface"], ppr.PriceSurface)
        assert entry["env_pins"]["CN_LANE"] == "asia"
        assert entry["stamps_price_through"] is True
        assert entry["plans_supported"] is False
        assert entry["pending_dir"] == "data/china_standout_track/pending_replay"
        assert entry["fidelity_floor"] == 0.85
        assert entry["gaps_file"] is None

    def test_hk_is_fully_resolved(self):
        entry = ppr.get_market_entry("hk")
        assert "unresolved" not in entry
        assert entry["board_relpath"] == "site/factordata/hk_standouts.json"
        assert isinstance(entry["price_surface"], ppr.PriceSurface)
        assert entry["env_pins"]["CN_LANE"] == "asia"
        assert entry["stamps_price_through"] is False
        assert entry["plans_supported"] is False
        assert entry["pending_dir"] == "data/board_ledger/pending_replay"
        assert entry["hk_pick_lab_pending_dir"] == "data/hk_pick_lab/pending_replay"
        assert entry["fidelity_floor"] == 0.85

    def test_ca_and_intl_still_declared_unresolved(self):
        for market in ("ca", "intl"):
            with pytest.raises(ppr.PitReplayRefused, match="DECLARED-UNRESOLVED"):
                ppr.get_market_entry(market)

    def test_cn_hk_price_surfaces_exclude_ticker_indexed_meta_tables(self):
        """members.parquet / constituents.parquet are ticker-indexed metadata
        (name/sector), never date-indexed — deliberately excluded (see the
        registry entries' inline comments + this build's RETURN)."""
        cn = ppr.get_market_entry("cn")["price_surface"]
        hk = ppr.get_market_entry("hk")["price_surface"]
        for panel in cn.wide_panels:
            assert "members" not in panel and "constituents" not in panel
        for panel in hk.wide_panels:
            assert "constituents" not in panel

    def test_cn_hk_bake_slot_is_asia_close_0830z(self):
        import datetime as dt
        for market in ("cn", "hk"):
            entry = ppr.get_market_entry(market)
            slot = entry["bake_slot"]("2026-08-17")
            assert slot == dt.datetime(2026, 8, 17, 8, 30, tzinfo=dt.timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Session validation
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionValidation:
    def test_cn_session_valid_matches_calendar(self):
        assert ppr._cn_session_valid("2026-08-17") is True    # Monday, A-share session
        assert ppr._cn_session_valid("2026-08-16") is False   # Sunday

    def test_hk_session_valid_matches_calendar(self):
        assert ppr._hk_session_valid("2026-08-17") is True    # Monday, HKEX session
        assert ppr._hk_session_valid("2026-08-16") is False   # Sunday, non-session

    def test_cn_session_valid_wired_into_registry(self):
        entry = ppr.get_market_entry("cn")
        assert entry["session_valid"]("2026-08-16") is False
        assert entry["session_valid"]("2026-08-17") is True

    def test_hk_session_valid_wired_into_registry(self):
        entry = ppr.get_market_entry("hk")
        assert entry["session_valid"]("2026-08-16") is False
        assert entry["session_valid"]("2026-08-17") is True


# ─────────────────────────────────────────────────────────────────────────────
# Unmarked-row assertion — absorbed rows carry NO extra columns/fields vs a
# live-appended row (masterplan §0.4: "Rows enter UNMARKED — no replay/backfill
# field on any row")
# ─────────────────────────────────────────────────────────────────────────────

class TestUnmarkedRows:
    def test_cn_absorbed_row_has_no_extra_columns_vs_live(self, cn_store):
        cst.append_board([{"ticker": "600005.SS", "price": 10.0}],
                         asof="2026-08-14", lane="asia")
        live_cols = set(pd.read_parquet(cst._store_path()).columns)

        # a "captured" row is exactly the shape a real live-written row has (the
        # harness's capture_cn_board_rows reads board.parquet rows verbatim)
        captured = pd.read_parquet(cst._store_path()).iloc[0].to_dict()
        captured["date"] = "2026-08-17"
        captured["ticker"] = "600006.SS"
        _write_pending(cst._pending_replay_dir(), "2026-08-17", "cn", [captured])
        cst.absorb_pending_replay()

        after_cols = set(pd.read_parquet(cst._store_path()).columns)
        assert after_cols == live_cols
        assert not any(kw in c.lower() for c in after_cols
                      for kw in ("replay", "backfill", "origination_mode"))

    def test_hk_board_absorbed_row_has_no_extra_columns_vs_live(self, hk_ledger):
        bl.append_board([_hk_row(ticker="0700.HK")], "HK", asof="2026-08-14")
        live_cols = set(pd.read_parquet(bl._store_path("HK")).columns)

        row = {"date": "2026-08-17", "market": "HK", **_hk_row(ticker="0701.HK")}
        _write_pending(hk_ledger / "pending_replay", "2026-08-17", "hk", [row])
        bl.absorb_pending_replay()

        after_cols = set(pd.read_parquet(bl._store_path("HK")).columns)
        assert after_cols == live_cols
        assert not any(kw in c.lower() for c in after_cols
                      for kw in ("replay", "backfill", "origination_mode"))

    def test_hk_pick_lab_absorbed_row_has_no_extra_fields_vs_live(
        self, hk_pick_lab_profile
    ):
        tmp_path, profile = hk_pick_lab_profile
        from engine.pick_lab.ledger import append_fires, load_fires
        append_fires([_fire_row(ticker="0700.HK")], profile=profile)
        live_keys = set(load_fires(profile=profile)[0].keys())

        row = _fire_row(ticker="0701.HK")
        _write_pending(tmp_path / "pending_replay", "2026-08-17", "hk", [row])
        bhpl.absorb_pending_replay()

        fires = load_fires(profile=profile)
        absorbed = next(f for f in fires if f["ticker"] == "0701.HK")
        assert set(absorbed.keys()) == live_keys
        assert not any(kw in k.lower() for k in absorbed.keys()
                      for kw in ("replay", "backfill", "origination_mode"))


# ─────────────────────────────────────────────────────────────────────────────
# Real-repo --resolve-only (cheap: registry + gap-guard + vintage resolution
# only, no board build — see scripts/prophet_pit_replay.py _cmd_resolve_only)
# ─────────────────────────────────────────────────────────────────────────────

def _origin_main_history_reachable() -> bool:
    """True when `git rev-list origin/main` can actually walk in THIS checkout.

    CI runners check out a SHALLOW tree (actions/checkout default), where
    `rev-list --first-parent --before=... origin/main` exits 128 — the same
    shallow-clone class the harness's own `assert_ancestor_of_main` refuses
    with the `--deepen` remediation. The two resolve tests below are real-repo
    integration conveniences, not the pin on resolver logic (that pin is the
    synthetic first-parent repo in tests/test_prophet_pit_replay.py), so on a
    history-less checkout they SKIP by name instead of failing the pack.
    """
    probe = subprocess.run(
        ["git", "rev-list", "-1", "origin/main"],
        cwd=_REPO, capture_output=True, text=True,
    )
    return probe.returncode == 0


_needs_main_history = pytest.mark.skipif(
    not _origin_main_history_reachable(),
    reason="origin/main history not walkable in this checkout (shallow CI clone)",
)


class TestResolveOnlyRealRepo:
    @_needs_main_history
    def test_cn_resolve_only_resolves(self):
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.prophet_pit_replay",
             "--market", "cn", "--session", "2026-08-17", "--resolve-only"],
            cwd=_REPO, capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "registry: OK" in proc.stdout
        assert "vintage_sha=" in proc.stdout

    @_needs_main_history
    def test_hk_resolve_only_resolves(self):
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.prophet_pit_replay",
             "--market", "hk", "--session", "2026-08-17", "--resolve-only"],
            cwd=_REPO, capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "registry: OK" in proc.stdout
        assert "vintage_sha=" in proc.stdout

    def test_ca_resolve_only_still_refuses(self):
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.prophet_pit_replay",
             "--market", "ca", "--session", "2026-08-17", "--resolve-only"],
            cwd=_REPO, capture_output=True, text=True,
        )
        assert proc.returncode == 2
        assert "DECLARED-UNRESOLVED" in (proc.stdout + proc.stderr)

    def test_intl_resolve_only_still_refuses(self):
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.prophet_pit_replay",
             "--market", "intl", "--session", "2026-08-17", "--resolve-only"],
            cwd=_REPO, capture_output=True, text=True,
        )
        assert proc.returncode == 2
        assert "DECLARED-UNRESOLVED" in (proc.stdout + proc.stderr)
