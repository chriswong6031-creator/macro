"""SA-W5 tests: v2 parallel grader lane isolation.

Guards the core invariant: v2 rows never leak into main lane stores or aggregates.

Covers:
  * snapshot_v2_today: idempotent per as_of; writes V2_SNAPSHOTS_JSONL only
  * collect_v2_boards: parses v2 lane names (v2_entry_open / v2_setting_up)
  * _merge_v2_into_store: accumulator writes V2_RETRO_PARQUET only; keep-first
  * run_v2_lane: writes V2_TRACK_JSON only; never touches RETRO_PARQUET / TRACK_JSON
  * Accountability VM builder: present / absent / corrupt JSON paths
  * Calibration hub standout_tracks field present and read-only
"""
import json
import sys
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.grade_us_board import (  # noqa: E402
    V2_BOARD_PATH,
    V2_LANES,
    V2_RETRO_PARQUET,
    V2_SNAPSHOTS_JSONL,
    V2_TRACK_JSON,
    RETRO_PARQUET,
    TRACK_JSON,
    _v2_board_to_record,
    collect_v2_boards,
    snapshot_v2_today,
    _merge_v2_into_store,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _minimal_v2_board(as_of: str = "2026-07-13") -> dict:
    """Minimal us_standouts_v2.json payload for testing."""
    return {
        "as_of": as_of,
        "rank_by": "test",
        "lanes": {
            "entry_open": [
                {"ticker": "AAPL", "lane": "entry_open"},
                {"ticker": "MSFT", "lane": "entry_open"},
            ],
            "setting_up": [
                {"ticker": "GOOG", "lane": "setting_up"},
            ],
        },
    }


def _minimal_grade_df_v2(as_of: str = "2026-07-13", n: int = 2, horizon: int = 5) -> pd.DataFrame:
    """Tiny v2 graded DataFrame with required columns."""
    rows = []
    for i in range(n):
        rows.append({
            "as_of": as_of, "ticker": f"V2TK{i}", "lane": f"v2_entry_open",
            "horizon": horizon, "position": i,
            "excess_spy": 0.01 + i * 0.005,
            "excess_sector": 0.005, "ret": 0.02, "spy_ret": 0.01,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# snapshot_v2_today
# ---------------------------------------------------------------------------

def _write_v2_board(root: Path, board: dict) -> None:
    """Write board to root/site/factordata/us_standouts_v2.json (mirrors V2_BOARD_PATH)."""
    dest = root / "site" / "factordata"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "us_standouts_v2.json").write_text(json.dumps(board))


def test_snapshot_v2_today_idempotent(tmp_path):
    """snapshot_v2_today is idempotent — a second call for the same as_of is a no-op."""
    board = _minimal_v2_board()
    _write_v2_board(tmp_path, board)
    snaps_path = tmp_path / "snapshots_v2.jsonl"

    with (
        mock.patch("scripts.grade_us_board.ROOT", tmp_path),
        mock.patch("scripts.grade_us_board.V2_SNAPSHOTS_JSONL", snaps_path),
        mock.patch("scripts.grade_us_board.LEDGER_DIR", tmp_path),
    ):
        result1 = snapshot_v2_today()
        result2 = snapshot_v2_today()

    assert result1 == "2026-07-13"
    assert result2 == "2026-07-13"
    lines = [l for l in snaps_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 1, f"Expected 1 snapshot line, got {len(lines)}"


def test_snapshot_v2_today_absent(tmp_path):
    """snapshot_v2_today returns None when v2 board is absent."""
    with (
        mock.patch("scripts.grade_us_board.ROOT", tmp_path),
        mock.patch("scripts.grade_us_board.V2_SNAPSHOTS_JSONL", tmp_path / "snapshots_v2.jsonl"),
        mock.patch("scripts.grade_us_board.LEDGER_DIR", tmp_path),
    ):
        result = snapshot_v2_today()
    assert result is None


def test_snapshot_v2_does_not_touch_main_snapshots(tmp_path):
    """snapshot_v2_today must not write to snapshots.jsonl."""
    board = _minimal_v2_board()
    _write_v2_board(tmp_path, board)
    main_snaps = tmp_path / "snapshots.jsonl"
    v2_snaps = tmp_path / "snapshots_v2.jsonl"

    with (
        mock.patch("scripts.grade_us_board.ROOT", tmp_path),
        mock.patch("scripts.grade_us_board.V2_SNAPSHOTS_JSONL", v2_snaps),
        mock.patch("scripts.grade_us_board.SNAPSHOTS_JSONL", main_snaps),
        mock.patch("scripts.grade_us_board.LEDGER_DIR", tmp_path),
    ):
        snapshot_v2_today()

    assert not main_snaps.exists(), "snapshot_v2_today must NOT write snapshots.jsonl"
    assert v2_snaps.exists(), "snapshot_v2_today must write snapshots_v2.jsonl"


# ---------------------------------------------------------------------------
# _v2_board_to_record
# ---------------------------------------------------------------------------

def test_v2_board_to_record_lane_prefix():
    """v2 board rows get v2_ prefix on lane names."""
    board = _minimal_v2_board()
    rec = _v2_board_to_record(board)
    assert rec is not None
    lanes = {r["lane"] for r in rec["rows"]}
    assert "v2_entry_open" in lanes
    assert "v2_setting_up" in lanes
    # Main lane names must NOT appear
    assert "entry_open" not in lanes
    assert "setting_up" not in lanes
    assert "buy" not in lanes


def test_v2_board_to_record_no_as_of():
    """_v2_board_to_record returns None when as_of is missing."""
    board = {"lanes": {"entry_open": [{"ticker": "AAPL"}]}}
    assert _v2_board_to_record(board) is None


def test_v2_board_to_record_empty_lanes():
    """_v2_board_to_record returns None when all lanes are empty."""
    board = {"as_of": "2026-07-13", "lanes": {"entry_open": [], "setting_up": []}}
    assert _v2_board_to_record(board) is None


# ---------------------------------------------------------------------------
# collect_v2_boards
# ---------------------------------------------------------------------------

def test_collect_v2_boards_empty(tmp_path):
    """collect_v2_boards returns [] when snapshot file is absent."""
    with mock.patch("scripts.grade_us_board.V2_SNAPSHOTS_JSONL", tmp_path / "snapshots_v2.jsonl"):
        result = collect_v2_boards()
    assert result == []


def test_collect_v2_boards_parses_lanes(tmp_path):
    """collect_v2_boards parses v2_entry_open / v2_setting_up lanes."""
    snap_path = tmp_path / "snapshots_v2.jsonl"
    board = _minimal_v2_board()
    snap_path.write_text(json.dumps(board) + "\n")
    with mock.patch("scripts.grade_us_board.V2_SNAPSHOTS_JSONL", snap_path):
        boards = collect_v2_boards()
    assert len(boards) == 1
    lanes = {r["lane"] for r in boards[0]["rows"]}
    assert "v2_entry_open" in lanes


# ---------------------------------------------------------------------------
# _merge_v2_into_store
# ---------------------------------------------------------------------------

def test_merge_v2_does_not_touch_main_parquet(tmp_path):
    """_merge_v2_into_store writes V2_RETRO_PARQUET only; RETRO_PARQUET is untouched."""
    main_parquet = tmp_path / "retro_grades.parquet"
    v2_parquet = tmp_path / "retro_grades_v2.parquet"
    fresh = _minimal_grade_df_v2()

    with (
        mock.patch("scripts.grade_us_board.V2_RETRO_PARQUET", v2_parquet),
        mock.patch("scripts.grade_us_board.RETRO_PARQUET", main_parquet),
        mock.patch("scripts.grade_us_board.LEDGER_DIR", tmp_path),
    ):
        result = _merge_v2_into_store(fresh)

    assert not main_parquet.exists(), "_merge_v2_into_store must NOT write retro_grades.parquet"
    assert v2_parquet.exists(), "_merge_v2_into_store must write retro_grades_v2.parquet"
    assert len(result) == len(fresh)


def test_merge_v2_keep_first_on_dedup(tmp_path):
    """_merge_v2_into_store keep-first: stored rows win on (as_of, ticker, lane, horizon)."""
    v2_parquet = tmp_path / "retro_grades_v2.parquet"

    first = _minimal_grade_df_v2(as_of="2026-07-13", n=2, horizon=5)
    first["excess_spy"] = 0.99  # sentinel value

    with (
        mock.patch("scripts.grade_us_board.V2_RETRO_PARQUET", v2_parquet),
        mock.patch("scripts.grade_us_board.LEDGER_DIR", tmp_path),
    ):
        _merge_v2_into_store(first)  # store first batch

        # Second batch: same dedup keys, different excess_spy
        second = _minimal_grade_df_v2(as_of="2026-07-13", n=2, horizon=5)
        second["excess_spy"] = 0.01  # different value

        merged = _merge_v2_into_store(second)

    # Fresh rows replace stored rows (keep-fresh convention: second batch wins)
    assert len(merged) == 2
    # After second merge, the fresh rows (excess_spy=0.01) overwrite stored (0.99)
    assert all(abs(merged["excess_spy"] - 0.01) < 0.001)


def test_merge_v2_empty_fresh_returns_stored(tmp_path):
    """_merge_v2_into_store returns existing store unchanged when fresh is empty."""
    v2_parquet = tmp_path / "retro_grades_v2.parquet"
    first = _minimal_grade_df_v2()

    with (
        mock.patch("scripts.grade_us_board.V2_RETRO_PARQUET", v2_parquet),
        mock.patch("scripts.grade_us_board.LEDGER_DIR", tmp_path),
    ):
        _merge_v2_into_store(first)
        empty = pd.DataFrame()
        result = _merge_v2_into_store(empty)

    assert len(result) == len(first)


# ---------------------------------------------------------------------------
# run_v2_lane isolation
# ---------------------------------------------------------------------------

def test_run_v2_lane_does_not_touch_main_track(tmp_path):
    """run_v2_lane must not write us_board_track.json."""
    main_track = tmp_path / "us_board_track.json"
    v2_track = tmp_path / "us_board_track_v2.json"

    # Provide a snapshot so collect_v2_boards has something
    snap_path = tmp_path / "snapshots_v2.jsonl"
    board = _minimal_v2_board("2026-07-01")
    snap_path.write_text(json.dumps(board) + "\n")

    prices = pd.DataFrame(
        {"AAPL": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0],
         "MSFT": [200.0, 201.0, 202.0, 203.0, 204.0, 205.0, 206.0, 207.0, 208.0],
         "GOOG": [150.0, 151.0, 152.0, 153.0, 154.0, 155.0, 156.0, 157.0, 158.0]},
        index=pd.date_range("2026-06-25", periods=9, freq="B"),
    )
    etfs = pd.DataFrame(
        {"SPY": [400.0, 401.0, 402.0, 403.0, 404.0, 405.0, 406.0, 407.0, 408.0]},
        index=pd.date_range("2026-06-25", periods=9, freq="B"),
    )

    from scripts.grade_us_board import run_v2_lane
    with (
        mock.patch("scripts.grade_us_board.V2_SNAPSHOTS_JSONL", snap_path),
        mock.patch("scripts.grade_us_board.V2_RETRO_PARQUET", tmp_path / "retro_grades_v2.parquet"),
        mock.patch("scripts.grade_us_board.V2_TRACK_JSON", v2_track),
        mock.patch("scripts.grade_us_board.RETRO_PARQUET", main_track),
        mock.patch("scripts.grade_us_board.TRACK_JSON", main_track),
        mock.patch("scripts.grade_us_board.LEDGER_DIR", tmp_path),
    ):
        run_v2_lane(prices, etfs, quiet=True)

    assert not main_track.exists(), "run_v2_lane must NOT write us_board_track.json"


# ---------------------------------------------------------------------------
# Accountability VM builder
# ---------------------------------------------------------------------------

def test_accountability_vm_absent():
    """_build_accountability_vm returns present=False when scoreboard is None."""
    from engine.pick_lab.render import _build_accountability_vm
    vm = _build_accountability_vm(None)
    assert vm["present"] is False


def test_accountability_vm_empty_dict():
    """_build_accountability_vm returns present=False when scoreboard is empty dict."""
    from engine.pick_lab.render import _build_accountability_vm
    vm = _build_accountability_vm({})
    assert vm["present"] is False


def test_accountability_vm_present():
    """_build_accountability_vm returns present=True with correct fields."""
    from engine.pick_lab.render import _build_accountability_vm
    scoreboard = {
        "schema": "standout_audit.scoreboard.v1",
        "as_of": "2026-07-12",
        "buy_lane_rows": 0,
        "all_lanes_rows": 0,
        "strata": {},
        "coverage_monitor": {
            "frozen_baseline": None,
            "trailing_4wk_buy_count": 365,
            "weekly_history": [],
            "data_gap": None,
        },
        "gate_suppressed": {"state": "data_gap", "reason": "test"},
    }
    vm = _build_accountability_vm(scoreboard)
    assert vm["present"] is True
    assert vm["as_of"] == "2026-07-12"
    assert vm["buy_lane_rows"] == 0
    assert vm["coverage_monitor"]["trailing_4wk_buy_count"] == 365


def test_cn_accountability_vm_absent():
    """_build_cn_accountability_vm returns present=False when scoreboard is None."""
    from engine.pick_lab.render_cn import _build_cn_accountability_vm
    vm = _build_cn_accountability_vm(None)
    assert vm["present"] is False


def test_cn_accountability_vm_present():
    """_build_cn_accountability_vm returns present=True with CN schema fields.

    Uses cn_audit_scoreboard.v1 schema (cells/outcome_cause_mix/process_fault_mix),
    NOT the US schema (buy_lane_rows/coverage_monitor/strata).
    """
    from engine.pick_lab.render_cn import _build_cn_accountability_vm
    vm = _build_cn_accountability_vm({
        "as_of": "2026-07-12",
        "schema": "cn_audit_scoreboard.v1",
        "taxonomy_version": "v2",
        "note": "accruing",
        "cells": [{"stratum": "us_proxy", "raw_n": 5, "state": "ACCRUING"}],
        "outcome_cause_mix": {},
        "process_fault_mix": {},
        "us_proxy_note": "Pre-store rows.",
    })
    assert vm["present"] is True
    assert "cells" in vm
    assert vm["taxonomy_version"] == "v2"
    # CN schema must NOT carry US-schema keys
    assert "buy_lane_rows" not in vm


# ---------------------------------------------------------------------------
# calibration hub: standout_tracks field
# ---------------------------------------------------------------------------

def test_calibration_hub_has_standout_tracks(tmp_path):
    """calibration_hub.build() returns standout_tracks list (SA-W5)."""
    from engine.calibration_hub import build
    # Mock the trial ledger so build() doesn't require full data setup
    with mock.patch("engine.calibration_hub.TrialLedger") as mock_tl:
        instance = mock_tl.return_value
        instance.families.return_value = []
        result = build(root=tmp_path)
    assert "standout_tracks" in result, "calibration hub must include standout_tracks (SA-W5)"
    assert isinstance(result["standout_tracks"], list)


def test_calibration_hub_standout_tracks_cold_on_absent_json(tmp_path):
    """standout_tracks entries are 'cold' when track JSON is absent."""
    from engine.calibration_hub import build
    with mock.patch("engine.calibration_hub.TrialLedger") as mock_tl:
        instance = mock_tl.return_value
        instance.families.return_value = []
        result = build(root=tmp_path)
    for entry in result["standout_tracks"]:
        assert entry["health"] == "cold", (
            f"standout_track '{entry['name']}' expected health='cold' when JSON absent, "
            f"got '{entry['health']}'"
        )


# ---------------------------------------------------------------------------
# US lab render: accountability key present in vm
# ---------------------------------------------------------------------------

def test_us_lab_vm_has_accountability():
    """build_vm always returns an 'accountability' key."""
    from engine.pick_lab.render import build_vm
    vm = build_vm(pick_lab_dict=None, longhold_dict=None)
    assert "accountability" in vm, "build_vm must include 'accountability' key"
    assert "present" in vm["accountability"]


def test_cn_lab_vm_has_accountability():
    """CN build_vm always returns an 'accountability' key."""
    from engine.pick_lab.render_cn import build_vm
    vm = build_vm(cn_pick_lab_dict=None)
    assert "accountability" in vm, "CN build_vm must include 'accountability' key"
    assert "present" in vm["accountability"]


# ---------------------------------------------------------------------------
# Template renders without error in the absent-data state
# ---------------------------------------------------------------------------

def _render_us_lab(vm: dict, templates_dir: Path) -> str:
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
    return env.get_template("us_stocks_lab.html.j2").render(**vm)


def _render_cn_lab(vm: dict, templates_dir: Path) -> str:
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
    return env.get_template("china_stocks_lab.html.j2").render(**vm)


def test_us_lab_accountability_tab_renders_empty_state():
    """us_stocks_lab.html.j2 renders the Accountability tab in the absent-data state."""
    from engine.pick_lab.render import build_vm
    templates = ROOT / "templates"
    vm = build_vm(pick_lab_dict=None, longhold_dict=None)
    html = _render_us_lab(vm, templates)
    assert "accountability" in html.lower() or "Record" in html or "ACCRUING" in html, (
        "Accountability tab content not found in rendered US lab page"
    )
    # SA-R10: 'validated' must not appear
    assert "validated" not in html.lower(), (
        "'validated' must not appear in rendered page (CI-enforced SA-R10)"
    )


def test_cn_lab_accountability_tab_renders_empty_state():
    """china_stocks_lab.html.j2 renders the Accountability tab in the absent-data state."""
    from engine.pick_lab.render_cn import build_vm
    templates = ROOT / "templates"
    vm = build_vm(cn_pick_lab_dict=None)
    html = _render_cn_lab(vm, templates)
    assert "accountability" in html.lower() or "Record" in html or "ACCRUING" in html, (
        "Accountability tab content not found in rendered CN lab page"
    )
    assert "validated" not in html.lower(), (
        "'validated' must not appear in rendered page (CI-enforced SA-R10)"
    )


# ---------------------------------------------------------------------------
# F1: render_page builder-style call path — committed scoreboard surfaces
# ---------------------------------------------------------------------------

def test_render_page_builder_path_shows_committed_scoreboard(tmp_path):
    """F1: render_page called builder-style (no explicit audit_scoreboard arg to
    build_vm) must still surface the committed scoreboard's coverage data.

    This is the production call path: build_pick_lab.py passes audit_scoreboard
    to build_vm, but render_page's belt-and-suspenders fallback also fires when
    vm["accountability"]["present"] is False.

    The committed us_audit_scoreboard.json has trailing_4wk_buy_count=365.
    The rendered page must contain "365".
    """
    import json as _json
    from engine.pick_lab.render import build_vm, render_page

    # Write the committed fixture to tmp_path/factordata/
    factordata = tmp_path / "factordata"
    factordata.mkdir(parents=True, exist_ok=True)
    committed_sb = {
        "schema": "standout_audit.scoreboard.v1",
        "as_of": "2026-07-12",
        "note": "test",
        "buy_lane_rows": 0,
        "all_lanes_rows": 0,
        "strata": {},
        "coverage_monitor": {
            "frozen_baseline": None,
            "trailing_4wk_buy_count": 365,
            "weekly_history": [],
            "data_gap": None,
        },
        "gate_suppressed": {"state": "data_gap", "reason": "test_reason"},
    }
    (factordata / "us_audit_scoreboard.json").write_text(_json.dumps(committed_sb))

    # Simulate builder-style call: build_vm WITHOUT audit_scoreboard arg
    # (as the old buggy path did; render_page must now fix it via fallback)
    vm = build_vm(pick_lab_dict=None, longhold_dict=None)
    # Confirm vm has present=False (the bug: disk fallback was dead before this fix)
    assert vm["accountability"]["present"] is False, (
        "Pre-condition: build_vm without audit_scoreboard should emit present=False"
    )

    render_page(vm, site=tmp_path)
    html = (tmp_path / "us_stocks_lab.html").read_text()
    assert "365" in html, (
        "F1 FAIL: render_page did not surface trailing_4wk_buy_count=365 "
        "from committed scoreboard (disk fallback still broken)"
    )


# ---------------------------------------------------------------------------
# F3: CN accountability extractor uses real cn_audit_scoreboard.v1 schema
# ---------------------------------------------------------------------------

def test_cn_accountability_vm_uses_cells_schema():
    """F3: _build_cn_accountability_vm must read 'cells', not 'strata'/'buy_lane_rows'.

    The real cn_audit_scoreboard.json has schema cn_audit_scoreboard.v1 with:
      cells, outcome_cause_mix, process_fault_mix, us_proxy_note, taxonomy_version.
    The old extractor read the US schema fields (strata, coverage_monitor, buy_lane_rows)
    which all return None/empty for CN, causing present=True but empty display.
    """
    from engine.pick_lab.render_cn import _build_cn_accountability_vm

    cn_scoreboard = {
        "as_of": "2026-07-12",
        "schema": "cn_audit_scoreboard.v1",
        "taxonomy_version": "v2",
        "note": "no matured rows yet — accruing",
        "cells": [],
        "outcome_cause_mix": {},
        "process_fault_mix": {},
        "us_proxy_note": "Pre-store rows carry stratum='us_proxy'.",
    }
    vm = _build_cn_accountability_vm(cn_scoreboard)
    assert vm["present"] is True
    assert "cells" in vm, "F3 FAIL: 'cells' key missing from CN accountability vm"
    assert "has_cells" in vm
    assert "outcome_cause_mix" in vm
    assert "has_outcome_cause_mix" in vm
    assert "process_fault_mix" in vm
    assert "has_process_fault_mix" in vm
    assert "us_proxy_note" in vm
    assert vm["taxonomy_version"] == "v2"
    # Must NOT contain US-schema keys
    assert "buy_lane_rows" not in vm, (
        "F3 FAIL: CN vm should not contain US-schema key 'buy_lane_rows'"
    )
    assert "strata" not in vm, (
        "F3 FAIL: CN vm should not contain US-schema key 'strata'"
    )
    assert "coverage_monitor" not in vm, (
        "F3 FAIL: CN vm should not contain US-schema key 'coverage_monitor'"
    )


def test_cn_accountability_vm_cells_with_us_proxy():
    """F3: cells list with us_proxy stratum must set is_us_proxy=True."""
    from engine.pick_lab.render_cn import _build_cn_accountability_vm

    cn_scoreboard = {
        "as_of": "2026-07-12",
        "schema": "cn_audit_scoreboard.v1",
        "taxonomy_version": "v2",
        "note": "test",
        "cells": [
            {"stratum": "us_proxy", "raw_n": 42, "effective_n": 15, "state": "ACCRUING"},
            {"stratum": "own_market", "raw_n": 10, "effective_n": 5, "state": "ACCRUING"},
        ],
        "outcome_cause_mix": {"macro_headwind": 3, "timing_early": 5},
        "process_fault_mix": {"signal_lag": 2},
        "us_proxy_note": "Some note.",
    }
    vm = _build_cn_accountability_vm(cn_scoreboard)
    assert vm["present"] is True
    assert vm["has_cells"] is True
    assert len(vm["cells"]) == 2
    us_proxy_cell = next(c for c in vm["cells"] if c["stratum"] == "us_proxy")
    assert us_proxy_cell["is_us_proxy"] is True
    own_cell = next(c for c in vm["cells"] if c["stratum"] == "own_market")
    assert own_cell["is_us_proxy"] is False
    assert vm["has_outcome_cause_mix"] is True
    assert vm["outcome_cause_mix"]["macro_headwind"] == 3


def test_cn_accountability_render_with_committed_json(tmp_path):
    """F3: render_page with the real committed cn_audit_scoreboard.json surfaces cells/mix.

    Reads the actual committed site/factordata/cn_audit_scoreboard.json.
    Even with cells=[] (no matured rows yet), present=True and us_proxy_note should appear.
    """
    import json as _json
    from engine.pick_lab.render_cn import build_vm, render_page

    committed_json = ROOT / "site" / "factordata" / "cn_audit_scoreboard.json"
    if not committed_json.exists():
        pytest.skip("cn_audit_scoreboard.json not found in repo")

    factordata = tmp_path / "factordata"
    factordata.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy(committed_json, factordata / "cn_audit_scoreboard.json")

    scoreboard = _json.loads(committed_json.read_text())
    vm = build_vm(cn_pick_lab_dict=None, audit_scoreboard=scoreboard)
    assert vm["accountability"]["present"] is True, (
        "F3 FAIL: CN accountability should be present=True with committed JSON"
    )
    render_page(vm, site=tmp_path)
    html = (tmp_path / "china_stocks_lab.html").read_text()
    # The us_proxy_note text should appear in the rendered page
    assert "us_proxy" in html, (
        "F3 FAIL: us_proxy label not found in rendered CN accountability tab"
    )
    assert "validated" not in html.lower()


# ---------------------------------------------------------------------------
# F5: v2 track has non-degenerate buy_lane when fed synthetic v2 rows
# ---------------------------------------------------------------------------

def test_v2_track_has_non_degenerate_buy_lane(tmp_path):
    """F5: run_v2_lane must emit a non-empty buy_lane block in us_board_track_v2.json.

    Before this fix, build_track's `lane == "buy"` filter returned 0 rows because
    v2 rows carry lane='v2_entry_open'.  The fix maps v2_entry_open → 'buy' in the
    track-computation copy only (raw parquet stays unchanged).
    """
    import json as _json
    from scripts.grade_us_board import run_v2_lane

    # Write enough v2 boards to have matured rows at h5
    snap_path = tmp_path / "snapshots_v2.jsonl"
    # Board date far enough in the past that h5 has matured
    board = _minimal_v2_board(as_of="2026-07-01")
    snap_path.write_text(_json.dumps(board) + "\n")

    prices = pd.DataFrame(
        {"AAPL": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0],
         "MSFT": [200.0, 201.0, 202.0, 203.0, 204.0, 205.0, 206.0, 207.0, 208.0],
         "GOOG": [150.0, 151.0, 152.0, 153.0, 154.0, 155.0, 156.0, 157.0, 158.0]},
        index=pd.date_range("2026-06-25", periods=9, freq="B"),
    )
    etfs = pd.DataFrame(
        {"SPY": [400.0, 401.0, 402.0, 403.0, 404.0, 405.0, 406.0, 407.0, 408.0]},
        index=pd.date_range("2026-06-25", periods=9, freq="B"),
    )

    v2_track_path = tmp_path / "us_board_track_v2.json"
    with (
        mock.patch("scripts.grade_us_board.V2_SNAPSHOTS_JSONL", snap_path),
        mock.patch("scripts.grade_us_board.V2_RETRO_PARQUET",
                   tmp_path / "retro_grades_v2.parquet"),
        mock.patch("scripts.grade_us_board.V2_TRACK_JSON", v2_track_path),
        mock.patch("scripts.grade_us_board.RETRO_PARQUET",
                   tmp_path / "retro_grades.parquet"),
        mock.patch("scripts.grade_us_board.TRACK_JSON",
                   tmp_path / "us_board_track.json"),
        mock.patch("scripts.grade_us_board.LEDGER_DIR", tmp_path),
    ):
        run_v2_lane(prices, etfs, quiet=True)

    assert v2_track_path.exists(), "run_v2_lane must write us_board_track_v2.json"
    track = _json.loads(v2_track_path.read_text())

    # Verify lane_mapping is stamped
    assert "lane_mapping" in track, "F5 FAIL: lane_mapping key not in v2 track"
    assert track["lane_mapping"].get("v2_entry_open") == "buy", (
        "F5 FAIL: v2_entry_open must be mapped to 'buy' in lane_mapping"
    )

    # If the track has per_horizon data (rows matured at h5), buy_lane must be non-empty
    per_h = track.get("per_horizon") or {}
    if per_h:
        for h_key, h_block in per_h.items():
            if isinstance(h_block, dict) and h_block.get("n", 0) > 0:
                buy_lane = h_block.get("buy_lane") or {}
                vs_spy = buy_lane.get("vs_spy") or {}
                assert vs_spy.get("n", 0) > 0, (
                    f"F5 FAIL: buy_lane.vs_spy.n=0 at {h_key} with matured rows — "
                    "v2_entry_open → buy mapping not applied"
                )
