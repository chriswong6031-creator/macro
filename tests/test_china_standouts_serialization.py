"""china_standouts.json serialization contract — tuple-key regression guard.

2026-07-13→07-16 outage: SA-W2 F7 (#2419) made china_standout_track.grade() return
``fwd_excess_map_21d`` keyed by (ticker, date) TUPLES; build_china_library.main()
attached grade()'s output wholesale to wide["board_track"], and the final
``json.dumps(wide, ..., default=str)`` crashed every asia run — ``default=`` only
covers VALUES, tuple KEYS are a hard TypeError. build_china.py swallowed the
exception in one line and served the persisted 07-10 artifact, so runs stayed
green while the board sat 5× past its 30h SLA.

Guards:
  • _detach_board_track_plumbing strips the map (tuple keys intact for
    run_attribution) so the artifact-bound dict serializes.
  • _find_bad_json_keys names the offending key path when the final dumps fails,
    so any FUTURE tuple-key regression is locatable from CI logs.

Run: .venv/bin/python -m pytest tests/test_china_standouts_serialization.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_china_library as bcl  # noqa: E402


def _grade_like_bt() -> dict:
    """Minimal shape-faithful grade() output: JSON-clean stats + the tuple-keyed map."""
    return {
        "available": True,
        "by_horizon": {"21d": {"n": 42, "hit_vs_csi300": 0.55}},
        "n_graded": 42,
        "fwd_excess_map_21d": {
            ("600519.SS", "2026-07-10"): 0.0123,
            ("300750.SZ", "2026-07-10"): None,
        },
    }


def test_tuple_keys_break_json_dumps_even_with_default_str():
    # The failure mode itself: default=str never applies to KEYS. If this ever
    # stops raising, the detach guard below is obsolete — revisit both together.
    with pytest.raises(TypeError):
        json.dumps({"board_track": _grade_like_bt()}, default=str)


def test_detach_makes_board_track_serializable_and_preserves_map():
    bt, fwd_map = bcl._detach_board_track_plumbing(_grade_like_bt())
    # artifact side: the wide-shaped dict must now serialize
    payload = json.dumps({"board_track": bt}, separators=(",", ":"), default=str)
    assert "fwd_excess_map_21d" not in payload
    assert bt["available"] and bt["n_graded"] == 42  # stats untouched
    # consumer side: run_attribution's contract is (ticker, date) tuple keys
    assert fwd_map == {("600519.SS", "2026-07-10"): 0.0123,
                       ("300750.SZ", "2026-07-10"): None}


def test_detach_passthrough_on_non_dict_and_missing_map():
    assert bcl._detach_board_track_plumbing(None) == (None, None)
    bt, fwd_map = bcl._detach_board_track_plumbing({"available": False})
    assert bt == {"available": False} and fwd_map is None


def test_find_bad_json_keys_names_the_offending_path():
    wide = {
        "as_of": "2026-07-16",
        "buy": [{"ticker": "600519.SS"}],
        "board_track": _grade_like_bt(),
    }
    bad = bcl._find_bad_json_keys(wide)
    assert len(bad) == 2  # one entry per tuple key
    assert all("board_track" in b and "fwd_excess_map_21d" in b for b in bad)
    assert all("tuple" in b for b in bad)
    assert "600519.SS" in bad[0]


def test_find_bad_json_keys_clean_dict_is_empty():
    bt, _ = bcl._detach_board_track_plumbing(_grade_like_bt())
    wide = {"as_of": "2026-07-16", "buy": [{"ticker": "600519.SS", "mcap": None}],
            "board_track": bt, "cap_composition": {"large": 1, "mid": 0}}
    assert bcl._find_bad_json_keys(wide) == []
    json.dumps(wide, separators=(",", ":"), default=str)  # and it round-trips
