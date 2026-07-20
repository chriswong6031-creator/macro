"""tests/test_levels_track_record_rebase.py — split-adjustment basis fix (WP-C1).

The ThetaData greeks store is RAW (split-unadjusted); data/stocks bars are back-adjusted.
_rebase_to_adjusted scales the reconstructed board onto the adjusted basis before grading so
split names don't grade a $1000 board against a $100 bar. Hermetic: crafted boards + bars.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.build_levels_track_record import _rebase_to_adjusted, _SPLIT_REBASE_TOL  # noqa: E402
from engine.levels_grade import grade_board  # noqa: E402


def _raw_board():
    """A pre-split NVDA-like RAW board: spot ~$1000, strikes $900-1220."""
    return {
        "schema": "levels.v1", "root": "NVDA", "asof": "2024-06-07", "spot": 1000.0,
        "regime": {"label": "sticky"},
        "nodes": [
            {"role": "anchor", "strike": 1000.0, "sticky": True},
            {"role": "call_wall", "strike": 1100.0, "sticky": True},
            {"role": "put_wall", "strike": 900.0, "sticky": False},
            {"role": "void", "strike": None, "strike_lo": 1180.0, "strike_hi": 1220.0},
        ],
    }


class TestRebaseHelper:
    def test_split_scales_all_price_fields(self):
        b = _rebase_to_adjusted(_raw_board(), prior_close=100.0)  # k = 0.1 (10:1 split)
        assert b["spot"] == 100.0
        byrole = {n["role"]: n for n in b["nodes"]}
        assert byrole["anchor"]["strike"] == 100.0
        assert byrole["call_wall"]["strike"] == 110.0
        assert byrole["put_wall"]["strike"] == 90.0
        assert byrole["void"]["strike_lo"] == 118.0 and byrole["void"]["strike_hi"] == 122.0
        assert b["rebased_split_k"] == 0.1

    def test_clean_name_is_byte_identical(self):
        # a genuine ~$100 clean board; greeks-vs-close basis 0.5% is within tolerance
        board = _raw_board()
        board["spot"] = 100.0
        for n in board["nodes"]:
            for f in ("strike", "strike_lo", "strike_hi"):
                if n.get(f) is not None:
                    n[f] = n[f] / 10.0
        before = copy.deepcopy(board)
        out = _rebase_to_adjusted(board, prior_close=99.5)  # k = 0.995, within tol → no-op
        assert abs(0.995 - 1.0) <= _SPLIT_REBASE_TOL
        assert out == before and "rebased_split_k" not in out

    def test_reverse_split(self):
        board = _raw_board()
        board["spot"] = 10.0
        for n in board["nodes"]:
            for f in ("strike", "strike_lo", "strike_hi"):
                if n.get(f) is not None:
                    n[f] = n[f] / 100.0
        out = _rebase_to_adjusted(board, prior_close=100.0)  # k = 10 (1:10 reverse split)
        assert out["spot"] == 100.0 and out["rebased_split_k"] == 10.0

    def test_missing_or_degenerate_inputs_untouched(self):
        assert _rebase_to_adjusted(None, 100.0) is None
        b = _raw_board()
        assert _rebase_to_adjusted(b, None) is b            # no prior_close
        b2 = _raw_board(); b2["spot"] = 0.0; b2["spot_ref"] = None
        assert _rebase_to_adjusted(b2, 100.0) is b2         # spot<=0 → can't establish basis


class TestGradeFlipsWithRebase:
    """The whole point: a split board MISSES the band/anchor raw, and HITS after rebase."""

    NEXT_BAR = {"date": "2024-06-10", "open": 100.0, "high": 102.0, "low": 98.5, "close": 101.0}
    IV = 0.20

    def test_raw_board_misses_band_and_anchor(self):
        g = grade_board(_raw_board(), self.NEXT_BAR, prior_close=100.0, median_iv=self.IV)
        # $1000 board graded against the $100 adjusted bar — the bug
        assert g["board"]["band_contained"] is False
        assert g["board"]["anchor_drew"] is False

    def test_rebased_board_contains_band_and_draws_anchor(self):
        adj = _rebase_to_adjusted(_raw_board(), prior_close=100.0)
        g = grade_board(adj, self.NEXT_BAR, prior_close=100.0, median_iv=self.IV)
        assert g["board"]["band_contained"] is True
        assert g["board"]["anchor_drew"] is True
