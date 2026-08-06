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


# ── Prophet board-definition pin ──────────────────────────────────────────────
# Same failure SHAPE as the tuple-key outage above — build_china.py rejects the
# board it was handed and serves a degraded shell instead — but from the opposite
# direction: there the artifact was genuinely unbuildable, here it was perfect.
#
# 2026-08-05→08-06: #4509 moved the board to ``cn_prophet_v3``.  build_china.py
# kept a hand-copied ``_CN_PROPHET_DEFINITION = "cn_prophet_v2"`` from #4029, so
# _is_current_prophet_artifact rejected the LIVE board and the persisted fallback
# alike and china_stocks.html rendered "data coverage degraded — board incomplete
# today" over a complete same-day board (24 featured / 204 eligible).  Nothing tied
# the renderer's pin to the engine's, so the drift was invisible to CI and surfaced
# only when the operator read the banner.

import ast  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
_BUILD_CHINA = ROOT / "scripts" / "build_china.py"


def test_renderer_accepts_the_engines_current_board_definition():
    """The pin the renderer enforces must be the one the engine is emitting.

    Non-vacuous on purpose: BOARD_DEFINITION is read from the PRODUCER and fed to
    the CONSUMER's own predicate, so the assert crosses the module boundary that
    actually drifted.  Re-asserting build_china's own constant would always pass.
    """
    from engine.china_board_rank import BOARD_DEFINITION
    from scripts.build_china import _is_current_prophet_artifact

    doc = {"schema_version": "2.0.0", "board_definition": BOARD_DEFINITION}
    assert _is_current_prophet_artifact(doc), (
        f"build_china rejects the engine's own current board definition "
        f"{BOARD_DEFINITION!r}; every board would render as a data outage"
    )


def test_a_superseded_board_definition_is_still_rejected():
    """The reject is load-bearing — don't 'fix' the drift by accepting everything."""
    from engine.china_board_rank import BOARD_DEFINITION
    from scripts.build_china import _is_current_prophet_artifact

    superseded = "cn_prophet_v2"
    assert superseded != BOARD_DEFINITION, (
        "fixture is stale: cn_prophet_v2 is the CURRENT definition again — pick a "
        "genuinely superseded era or this test proves nothing"
    )
    assert not _is_current_prophet_artifact(
        {"schema_version": "2.0.0", "board_definition": superseded}
    ), "a board from a superseded ranking must never render as the current one"


def test_renderer_keeps_no_private_copy_of_the_board_definition():
    """Structural guard: the drift class returns the moment someone re-copies it.

    AST-based, not grep-based — the module header discusses ``cn_prophet_v2`` in
    prose, and a textual scan would flag that comment while missing a slug built
    by concatenation.  Comments carry no code, so the AST sees only real literals.
    """
    tree = ast.parse(_BUILD_CHINA.read_text())
    literals = sorted({
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("cn_prophet_v")
    })
    assert not literals, (
        f"scripts/build_china.py hardcodes board definition(s) {literals} — import "
        f"BOARD_DEFINITION from engine.china_board_rank instead; a copy went stale "
        f"once (#4509) and blanked the China Prophet board"
    )
