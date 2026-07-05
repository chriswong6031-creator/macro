"""Tests for the SRSS Phase 2 production shadow-tier pipeline:

  * engine.spine.adapt_subsector_sponsorship / write_subsector_sponsorship
  * engine.subsector_sponsorship (shared join/classification, factored out of
    research/entry_stack/sponsorship_phase0.py)
  * engine.neuralweb.confluence sponsorship nodes/edges

Covers: adapter output shape matches other spine adapters' conventions,
display_only is always set, direction is inherited (never invented), the
stream never leaks into graded_rows()/measured_ic() (the one shared
aggregate the spine module exposes), and confluence edges are all
display_only=True.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine import spine
from engine.neuralweb import confluence


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture()
def root(tmp_path) -> Path:
    (tmp_path / "data").mkdir()
    return tmp_path


def _write_rotation_snapshot(root: Path, rows: list[dict]) -> None:
    p = root / "data" / "subsector_rotation" / "snapshots.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


_TAILWIND_SNAP = {
    "date": "2026-07-01", "key": "widgets", "name": "Widgets", "theme": "Industrials",
    "score": 2.0, "rs_mom": 1.5, "accel": 0.5, "quadrant": "leading", "stage": "leading",
    "lean": 1, "members": ["AAA", "BBB", "FFF"],
}
_HEADWIND_SNAP = {
    "date": "2026-07-01", "key": "gadgets", "name": "Gadgets", "theme": "Tech",
    "score": -1.0, "rs_mom": -2.0, "accel": -1.0, "quadrant": "lagging", "stage": "lagging",
    "lean": -1, "members": ["CCC", "DDD", "EEE"],
}


# --------------------------------------------------------------------------- #
# adapter shape / display_only / direction inheritance
# --------------------------------------------------------------------------- #
def test_adapter_output_matches_spine_prediction_shape(root):
    _write_rotation_snapshot(root, [_TAILWIND_SNAP])
    fires = [{"ticker": "AAA", "as_of": "2026-07-02", "direction": "long", "lane": "buy"}]
    rows = spine.adapt_subsector_sponsorship(root=root, fires=fires)
    assert len(rows) == 1
    r = rows[0]
    assert isinstance(r, spine.SpinePrediction)
    row_dict = r.as_row()
    # same canonical keys every other adapter's SpinePrediction emits
    for col in spine.COLUMNS:
        assert col in row_dict


def test_display_only_always_set(root):
    _write_rotation_snapshot(root, [_TAILWIND_SNAP, _HEADWIND_SNAP])
    fires = [
        {"ticker": "AAA", "as_of": "2026-07-02", "direction": "long"},
        {"ticker": "CCC", "as_of": "2026-07-02", "direction": "short"},
    ]
    rows = spine.adapt_subsector_sponsorship(root=root, fires=fires)
    assert len(rows) == 2
    for r in rows:
        assert r.meta["display_only"] is True
        # never an originating score/size — Article-1
        assert r.score == 0.0
        assert r.size_binding is False


def test_direction_inherited_not_invented(root):
    _write_rotation_snapshot(root, [_TAILWIND_SNAP])
    # source event explicitly says direction="long" -> must carry through as +1
    fires = [{"ticker": "AAA", "as_of": "2026-07-02", "direction": "long"}]
    rows = spine.adapt_subsector_sponsorship(root=root, fires=fires)
    assert rows[0].direction == 1

    # source event with no direction info at all (no "direction", no "lane")
    # must NOT fabricate a lean -> direction=0 (context), never +/-1
    fires_no_dir = [{"ticker": "AAA", "as_of": "2026-07-02"}]
    rows2 = spine.adapt_subsector_sponsorship(root=root, fires=fires_no_dir)
    assert rows2[0].direction == 0

    # short lane inherits -1
    fires_short = [{"ticker": "AAA", "as_of": "2026-07-02", "direction": "short"}]
    rows3 = spine.adapt_subsector_sponsorship(root=root, fires=fires_short)
    assert rows3[0].direction == -1


def test_no_match_emits_no_row(root):
    _write_rotation_snapshot(root, [_TAILWIND_SNAP])
    # ZZZ is not a member of any subsector snapshot -> no-match, no fabricated row
    fires = [{"ticker": "ZZZ", "as_of": "2026-07-02", "direction": "long"}]
    rows = spine.adapt_subsector_sponsorship(root=root, fires=fires)
    assert rows == []


def test_bare_root_fails_open(root):
    assert spine.adapt_subsector_sponsorship(root=root) == []


def test_sponsorship_state_and_score_travel_in_meta_only(root):
    _write_rotation_snapshot(root, [_HEADWIND_SNAP])
    fires = [{"ticker": "CCC", "as_of": "2026-07-02", "direction": "short"}]
    rows = spine.adapt_subsector_sponsorship(root=root, fires=fires)
    r = rows[0]
    assert r.meta["sponsorship_state"] == "HEADWIND"
    assert r.meta["sponsorship_score"] == -1.0
    assert r.meta["confidence_tier"] == "low"  # n_members=3


# --------------------------------------------------------------------------- #
# no leakage into the shared graded ledger / measured_ic
# --------------------------------------------------------------------------- #
def test_write_subsector_sponsorship_does_not_touch_predictions_parquet(root):
    _write_rotation_snapshot(root, [_TAILWIND_SNAP])
    fires = [{"ticker": "AAA", "as_of": "2026-07-02", "direction": "long"}]
    report = spine.write_subsector_sponsorship(root=root, fires=fires)
    assert report["rows_in"] == 1
    # the shared predictions.parquet must remain untouched (no adapter wired
    # this stream into rebuild_from_adapters — see adapter docstring)
    assert not (root / "data" / "spine" / "predictions.parquet").exists()
    assert (root / "data" / "spine" / "subsector_sponsorship.parquet").exists()


def test_sponsorship_rows_never_enter_measured_ic(root):
    """Sponsorship rows are never graded, so they must be invisible to the ONE
    shared aggregate the spine module exposes (measured_ic/graded_rows) —
    this is the concrete 'no leakage into any master/aggregate score' check."""
    # Seed the shared predictions.parquet with an unrelated graded row so the
    # ledger is non-empty and measured_ic has something to compute over.
    other = spine.SpinePrediction(
        "other:1", "us_board", "us_board:buy", "2026-07-01", "AAA", 21,
        score=1.0, direction=1, size_binding=True,
        outcome_excess=0.05, outcome_graded=True,
    )
    spine.emit([other], root=root)
    ic_before = spine.measured_ic(root=root)

    _write_rotation_snapshot(root, [_TAILWIND_SNAP])
    fires = [{"ticker": "AAA", "as_of": "2026-07-02", "direction": "long"}]
    sponsorship_rows = spine.adapt_subsector_sponsorship(root=root, fires=fires)
    assert sponsorship_rows  # sanity: the fixture actually produced a row
    assert sponsorship_rows[0].outcome_graded is False
    assert sponsorship_rows[0].outcome_excess is None

    # write to its OWN artifact (not emit() into predictions.parquet)
    spine.write_subsector_sponsorship(root=root, fires=fires)

    ic_after = spine.measured_ic(root=root)
    assert ic_after == ic_before

    # even if a caller mistakenly emit()'d these rows into the shared ledger,
    # graded_rows() would still exclude them (outcome_graded=False)
    spine.emit(sponsorship_rows, root=root)
    graded = spine.graded_rows(root=root)
    assert "subsector_sponsorship" not in set(graded["engine"])


# --------------------------------------------------------------------------- #
# confluence edges — display_only=True, correct edge_type mapping
# --------------------------------------------------------------------------- #
def _write_sponsorship_parquet(root: Path, rows: list[spine.SpinePrediction]) -> None:
    out = root / "data" / "spine" / "subsector_sponsorship.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([r.as_row() for r in rows])
    for c in spine.COLUMNS:
        if c not in df.columns:
            df[c] = None
    df[spine.COLUMNS].to_parquet(out, index=False)


def test_confluence_sponsorship_edges_display_only(root):
    _write_rotation_snapshot(root, [_TAILWIND_SNAP, _HEADWIND_SNAP])
    fires = [
        {"ticker": "AAA", "as_of": "2026-07-02", "direction": "long"},
        {"ticker": "CCC", "as_of": "2026-07-02", "direction": "short"},
    ]
    rows = spine.adapt_subsector_sponsorship(root=root, fires=fires)
    assert len(rows) == 2
    _write_sponsorship_parquet(root, rows)

    g = confluence.build_graph(root=root)
    sp_edges = [e for e in g["edges"] if e["edge_type"].startswith("sponsorship")]
    assert len(sp_edges) == 2
    for e in sp_edges:
        assert e["display_only"] is True

    types = {e["edge_type"] for e in sp_edges}
    assert "sponsorship_support" in types           # AAA -> TAILWIND (widgets)
    assert "sponsorship_contradicts" in types        # CCC -> HEADWIND (gadgets)

    # direction on the edge is copied through, never invented
    aaa_edge = next(e for e in sp_edges if e["src"] == "entity:AAA")
    assert aaa_edge["direction"] == 1
    ccc_edge = next(e for e in sp_edges if e["src"] == "entity:CCC")
    assert ccc_edge["direction"] == -1

    # sponsorship_score rides the edge for display only
    assert aaa_edge["sponsorship_score"] == 2.0


def test_confluence_neutral_state_emits_no_edge(root):
    neutral_snap = {
        "date": "2026-07-01", "key": "flat", "name": "Flat", "theme": "X",
        "score": 0.0, "rs_mom": 0.0, "accel": 0.0, "quadrant": "improving",
        "stage": "x", "lean": 0, "members": ["DDD"],
    }
    _write_rotation_snapshot(root, [neutral_snap])
    fires = [{"ticker": "DDD", "as_of": "2026-07-02", "direction": "long"}]
    rows = spine.adapt_subsector_sponsorship(root=root, fires=fires)
    assert rows[0].meta["sponsorship_state"] == "NEUTRAL"
    _write_sponsorship_parquet(root, rows)

    g = confluence.build_graph(root=root)
    sp_edges = [e for e in g["edges"] if e["edge_type"].startswith("sponsorship")]
    assert sp_edges == []
    assert any("NEUTRAL" in gap or "0 non-NEUTRAL" in gap for gap in g["gaps"])


def test_confluence_absent_sponsorship_artifact_failopen(root):
    g = confluence.build_graph(root=root)
    sp_edges = [e for e in g["edges"] if e["edge_type"].startswith("sponsorship")]
    assert sp_edges == []
    assert any("subsector_sponsorship" in gap for gap in g["gaps"])
