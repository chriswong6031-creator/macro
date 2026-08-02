"""scripts/build_gex_board.py — the OIP W1 site/gex/<T>.json enrichment.

engine/gex_state.compute_gex_state()'s three additive fields (oi_delta_clusters,
wall_persistence, net_gex_pctile, PR #3976) are computed by
_compute_and_write_gex_state() and written to a SEPARATE file,
site/options_structure/gex_state/<KEY>.json — but W1_DESIGN_SPEC.md's own
template code reads them as `gx.wall_persistence` / `gx.oi_delta_clusters`,
`gx` being site/gex.js's name for site/gex/<T>.json, the payload Ticker mode
and gex.html actually fetch. Without folding the fields into THAT payload too,
every wall-check chip and "Where positions built" panel would read undefined
forever, regardless of a name's real coverage. This suite pins the fold.

Run: python -m pytest tests/test_gex_board_state_merge.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_gex_board import (  # noqa: E402
    _compute_and_write_gex_state,
    _merge_gex_state_fields,
)


# A model shaped enough for engine.gex_state.compute_gex_state to succeed —
# mirrors engine/gex_model.build_model's real output shape (summary + walls).
def _model(**overrides):
    base = {
        "summary": {
            "spot": 500.0, "regime": "long", "gamma_flip": 490.0,
            "dist_to_flip_pct": 2.0, "call_wall": 520.0, "put_wall": 480.0,
            "max_pain": 495.0, "net_gex_bn": 1.2, "tier": "full", "n_strikes": 30,
        },
        "walls": {
            "by_strike": [
                {"K": 480.0, "net_mn": -50.0}, {"K": 490.0, "net_mn": -10.0},
                {"K": 495.0, "net_mn": 5.0}, {"K": 520.0, "net_mn": 60.0},
            ],
        },
        "history": [],
    }
    base.update(overrides)
    return base


class TestComputeAndWriteReturnsTheStateItWrites:
    def test_returns_none_and_writes_nothing_for_a_thin_no_options_model(self, tmp_path):
        model = _model(summary={"tier": "no_options", "spot": None})
        out = _compute_and_write_gex_state(model, "ZZZZ", tmp_path)
        assert out is None
        assert not (tmp_path / "ZZZZ.json").exists()

    def test_returns_the_written_dict_for_a_real_model(self, tmp_path):
        state = _compute_and_write_gex_state(_model(), "SPY", tmp_path)
        assert state is not None
        assert state["schema"] == "options_structure.gex_state/v1"
        assert "oi_delta_clusters" in state  # BACK-COMPAT: always present
        written = (tmp_path / "SPY.json").read_text()
        import json
        assert json.loads(written) == state


class TestMergeGexStateFields:
    def test_none_state_leaves_model_completely_unchanged(self):
        model = _model()
        before = dict(model)
        out = _merge_gex_state_fields(model, None)
        assert out is model  # same object, mutated in place (or not, here)
        assert "oi_delta_clusters" not in model
        assert "wall_persistence" not in model
        assert "net_gex_pctile" not in model
        assert model == before

    def test_oi_delta_clusters_always_copied_when_state_exists(self):
        """BACK-COMPAT field on the gex_state side — always present, even as
        empty lists, so it is copied unconditionally whenever state is real."""
        model = _model()
        state = {"oi_delta_clusters": {"new_oi": [], "exit_oi": []}}
        _merge_gex_state_fields(model, state)
        assert model["oi_delta_clusters"] == {"new_oi": [], "exit_oi": []}
        assert "wall_persistence" not in model
        assert "net_gex_pctile" not in model

    def test_state_missing_oi_delta_clusters_does_not_raise(self):
        """Minor fix: the merge used an unconditional state["oi_delta_clusters"]
        outside its own try — a state that (contrary to the back-compat
        assumption one row up) omits the key raised KeyError here, and the
        caller's try/except in work() wraps the board file WRITE too, so the
        whole symbol's site/gex/<KEY>.json silently never got written despite
        the docstring's "never fatal" promise. A state missing the key must
        degrade the merge for that one field, never abort it."""
        model = _model()
        state = {"wall_persistence": {"call_side": {"matches_board_wall": True}}}
        out = _merge_gex_state_fields(model, state)  # must not raise
        assert out is model
        assert "oi_delta_clusters" not in model, "never fake a key with no computed value behind it"
        assert model["wall_persistence"] == {"call_side": {"matches_board_wall": True}}
        assert "net_gex_pctile" not in model

    def test_wall_persistence_and_net_gex_pctile_copied_only_when_present(self):
        """Both are additive/coverage-gated at the source (PR #3976) — omitted,
        never null-filled, when state itself omits them."""
        model = _model()
        state = {
            "oi_delta_clusters": {"new_oi": [{"K": 525.0, "right": "put", "oi_delta": 1000}], "exit_oi": []},
            "wall_persistence": {"call_side": {"matches_board_wall": True}},
            "net_gex_pctile": {"pctile": 62, "note_en": "x", "note_zh": "y"},
        }
        _merge_gex_state_fields(model, state)
        assert model["wall_persistence"] == {"call_side": {"matches_board_wall": True}}
        assert model["net_gex_pctile"]["pctile"] == 62

    def test_end_to_end_compute_then_merge_lands_on_the_board_payload(self, tmp_path):
        """The exact sequence work() runs: compute+write the standalone
        gex_state artifact, then fold its output into the SAME model that
        becomes site/gex/<KEY>.json — one compute_gex_state call, two writes."""
        model = _model()
        state = _compute_and_write_gex_state(model, "SPY", tmp_path)
        _merge_gex_state_fields(model, state)
        # oi_delta_clusters is BACK-COMPAT-always-present on the gex_state side,
        # so it must now also be readable as gx.oi_delta_clusters (the payload
        # Ticker mode fetches) — exactly the shape W1_DESIGN_SPEC.md §0.18's own
        # payload check assumes: `gx.oi_delta_clusters.new_oi.length`.
        assert "new_oi" in model["oi_delta_clusters"]
        assert "exit_oi" in model["oi_delta_clusters"]
        # SPY has real snapshot-store coverage in this checkout (positioning_
        # persistence reads committed data/ parquets, not this test's synthetic
        # `model`) — so wall_persistence legitimately landed on the board
        # payload too. The field-existence contract (present <=> state carried
        # it) is what matters here, not this one root's specific coverage.
        if "wall_persistence" in state:
            assert model["wall_persistence"] == state["wall_persistence"]
        else:
            assert "wall_persistence" not in model
