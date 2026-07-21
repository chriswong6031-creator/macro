"""tests/test_levels_track_record_rebase.py — back-adjustment basis fix (WP-C1).

The ThetaData greeks store is RAW (split- AND dividend-unadjusted); data/stocks bars are
back-adjusted for both. _rebase_to_adjusted anchors the board to the adjusted prior-close and
scales it by k = prior_close_adjusted / spot_raw BEFORE grading — UNCONDITIONALLY, so it fixes
both the big step (splits) and the small drift (dividends). The dividend drift is below the
#3155 split tolerance but deadly for low-vol names (tight band can't absorb a ~6% offset →
0% containment for a year). Hermetic: crafted boards + bars.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.build_levels_track_record import (  # noqa: E402
    _rebase_to_adjusted, _REBASE_K_MIN, _REBASE_K_MAX,
)
from engine.levels_grade import grade_board  # noqa: E402


def _raw_board(spot=1000.0, anchor=1000.0, cw=1100.0, pw=900.0, vlo=1180.0, vhi=1220.0):
    return {
        "schema": "levels.v1", "root": "NVDA", "asof": "2024-06-07", "spot": spot,
        "regime": {"label": "sticky"},
        "nodes": [
            {"role": "anchor", "strike": anchor, "sticky": True},
            {"role": "call_wall", "strike": cw, "sticky": True},
            {"role": "put_wall", "strike": pw, "sticky": False},
            {"role": "void", "strike": None, "strike_lo": vlo, "strike_hi": vhi},
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
        assert b["rebased_k"] == 0.1

    def test_dividend_scale_basis_is_rebased(self):
        # ~6% dividend basis (XOM-like) — BELOW the old 0.10 split tolerance, so #3155 skipped it.
        # Unconditional rebase must now correct it: k = 107.65 / 115.0 = 0.9361.
        b = _rebase_to_adjusted(_raw_board(spot=115.0, anchor=115.0, cw=118.0, pw=112.0,
                                           vlo=119.0, vhi=121.0), prior_close=107.65)
        assert b["rebased_k"] == round(107.65 / 115.0, 6)
        assert b["spot"] == round(115.0 * (107.65 / 115.0), 4) == 107.65
        byrole = {n["role"]: n for n in b["nodes"]}
        assert byrole["anchor"]["strike"] == 107.65
        assert abs(byrole["call_wall"]["strike"] - 118.0 * 0.9361) < 0.01

    def test_reverse_split(self):
        out = _rebase_to_adjusted(_raw_board(spot=10.0, anchor=10.0, cw=11.0, pw=9.0,
                                             vlo=11.8, vhi=12.2), prior_close=100.0)  # k = 10
        assert out["spot"] == 100.0 and out["rebased_k"] == 10.0

    def test_near_clean_name_barely_moves(self):
        # k=0.995 (tiny intraday/dividend basis) IS now rebased (no tolerance), but the shift
        # is sub-percent — spot lands on the adjusted close, strikes barely move.
        out = _rebase_to_adjusted(_raw_board(spot=100.0, anchor=100.0, cw=110.0, pw=90.0,
                                             vlo=118.0, vhi=122.0), prior_close=99.5)
        assert out["spot"] == 99.5 and out["rebased_k"] == 0.995
        assert abs(out["nodes"][1]["strike"] - 110.0 * 0.995) < 1e-6

    def test_absurd_k_not_rebased(self):
        # a bad print (k way outside any real corporate action) must NOT scale the board
        assert "rebased_k" not in _rebase_to_adjusted(_raw_board(spot=1000.0), prior_close=1.0)  # k=0.001
        assert "rebased_k" not in _rebase_to_adjusted(_raw_board(spot=1.0), prior_close=1000.0)  # k=1000
        assert _REBASE_K_MIN < 0.02 and _REBASE_K_MAX > 50  # still allows 50:1 splits

    def test_missing_or_degenerate_inputs_untouched(self):
        assert _rebase_to_adjusted(None, 100.0) is None
        b = _raw_board()
        assert _rebase_to_adjusted(b, None) is b
        b2 = _raw_board(spot=0.0); b2["spot_ref"] = None
        assert _rebase_to_adjusted(b2, 100.0) is b2


class TestSplitGradeFlips:
    """A split board MISSES the band/anchor raw, HITS after rebase."""

    NEXT_BAR = {"date": "2024-06-10", "open": 100.0, "high": 102.0, "low": 98.5, "close": 101.0}
    IV = 0.20

    def test_raw_misses(self):
        g = grade_board(_raw_board(), self.NEXT_BAR, prior_close=100.0, median_iv=self.IV)
        assert g["board"]["band_contained"] is False and g["board"]["anchor_drew"] is False

    def test_rebased_contains(self):
        adj = _rebase_to_adjusted(_raw_board(), prior_close=100.0)
        g = grade_board(adj, self.NEXT_BAR, prior_close=100.0, median_iv=self.IV)
        assert g["board"]["band_contained"] is True and g["board"]["anchor_drew"] is True


class TestDividendGradeFlips:
    """The residual bug: a LOW-VOL dividend board (tight band) misses on a ~6% basis raw,
    contains after the unconditional rebase. This flip is what #3155's tolerance blocked."""

    # XOM-like calm next session in ADJUSTED space (~$107.65 area), low IV → tight band
    NEXT_BAR = {"date": "2024-07-02", "open": 107.6, "high": 108.5, "low": 106.8, "close": 107.9}
    IV = 0.24
    PC = 107.65  # adjusted prior close
    RAW = dict(spot=115.0, anchor=115.0, cw=118.0, pw=112.0, vlo=119.0, vhi=121.0)  # raw $115

    def test_raw_lowvol_misses_every_way(self):
        g = grade_board(_raw_board(**self.RAW), self.NEXT_BAR, prior_close=self.PC, median_iv=self.IV)
        assert g["board"]["band_contained"] is False   # $115 band never reaches the $107 bar
        assert g["board"]["anchor_drew"] is False

    def test_rebased_lowvol_contains(self):
        adj = _rebase_to_adjusted(_raw_board(**self.RAW), prior_close=self.PC)
        g = grade_board(adj, self.NEXT_BAR, prior_close=self.PC, median_iv=self.IV)
        assert g["board"]["band_contained"] is True
        assert g["board"]["anchor_drew"] is True
