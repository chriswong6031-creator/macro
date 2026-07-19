"""tests/test_levels_grade.py — WP-C1 levels Track Record grader (pure grading logic).

Hermetic: no store, no network, no clock. Crafted boards + next-session bars with known
answers exercise every branch of grade_board + the aggregation.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.levels_grade import (  # noqa: E402
    grade_board, aggregate_track_record, level_id, board_id,
    expected_move_band, learn_band_mult, TR_SCHEMA,
)


def _board(nodes, spot=100.0, regime="sticky", asof="2026-07-16", root="TEST"):
    return {"schema": "levels.v1", "root": root, "asof": asof, "spot": spot,
            "spot_ref": spot, "regime": {"label": regime},
            "nodes": nodes, "stacks": []}


def _node(role, strike, sticky=None):
    return {"role": role, "strike": strike, "weight": 1.0, "sticky": sticky,
            "brightness": 0.5, "note": ""}


class TestIds:
    def test_level_id_deterministic_and_distinct(self):
        a = level_id("AAPL", "2026-07-16", "anchor", 190.0)
        assert a == level_id("AAPL", "2026-07-16", "anchor", 190.0)
        assert a != level_id("AAPL", "2026-07-16", "anchor", 191.0)
        assert a != level_id("AAPL", "2026-07-16", "cluster", 190.0)
        # idx disambiguates two same-role nodes
        assert level_id("AAPL", "2026-07-16", "cluster", 190.0, 0) != \
               level_id("AAPL", "2026-07-16", "cluster", 190.0, 1)

    def test_board_id(self):
        assert board_id("AAPL", "2026-07-16") == board_id("AAPL", "2026-07-16")
        assert board_id("AAPL", "2026-07-16") != board_id("MSFT", "2026-07-16")


class TestExpectedMove:
    def test_band_math(self):
        # spot 100, iv 0.20 (annual), 1 day, mult 1.96 → sigma = 100*0.2*sqrt(1/252)
        band = expected_move_band(100.0, 0.20, 1.96)
        assert band is not None
        half = band[1] - 100.0
        assert 2.0 < half < 3.0  # ~2.47
        assert abs((100.0 - band[0]) - half) < 1e-9

    def test_band_none_on_bad_inputs(self):
        assert expected_move_band(None, 0.2, 1.96) is None
        assert expected_move_band(100.0, None, 1.96) is None
        assert expected_move_band(100.0, 0.0, 1.96) is None


class TestGradeBoard:
    def test_anchor_drew_touched(self):
        b = _board([_node("anchor", 100.0, True)])
        g = grade_board(b, {"date": "2026-07-17", "high": 101, "low": 99, "close": 100.5},
                        prior_close=98.0, median_iv=0.2)
        assert g["reason"] == "ok"
        assert g["board"]["anchor_drew"] is True
        nd = g["nodes"][0]
        assert nd["touched"] is True

    def test_anchor_not_touched(self):
        b = _board([_node("anchor", 100.0, True)])
        g = grade_board(b, {"date": "2026-07-17", "high": 96, "low": 94, "close": 95},
                        prior_close=98.0, median_iv=0.2)
        assert g["board"]["anchor_drew"] is False
        assert g["nodes"][0]["touched"] is False

    def test_sticky_held_vs_broke(self):
        # price approached from below (prior 98), touched 100, closed back below → sticky HELD
        b = _board([_node("cluster", 100.0, True)])
        g = grade_board(b, {"date": "d", "high": 100.5, "low": 99, "close": 99.5},
                        prior_close=98.0, median_iv=0.2)
        nd = g["nodes"][0]
        assert nd["touched"] is True and nd["held"] is True and nd["broke"] is False
        # closed ABOVE the level after approaching from below → sticky broken (a miss)
        g2 = grade_board(b, {"date": "d", "high": 101, "low": 99, "close": 100.7},
                         prior_close=98.0, median_iv=0.2)
        nd2 = g2["nodes"][0]
        assert nd2["held"] is False and nd2["broke"] is True

    def test_slippery_broke_vs_held(self):
        # slippery level (sticky False): approached from above (prior 102), closed below → BROKE (correct)
        b = _board([_node("put_wall", 100.0, False)])
        g = grade_board(b, {"date": "d", "high": 103, "low": 98, "close": 98.5},
                        prior_close=102.0, median_iv=0.2)
        nd = g["nodes"][0]
        assert nd["touched"] is True and nd["broke"] is True and nd["held"] is False
        # slippery level that held (closed back on origin side) → miss for slipperiness
        g2 = grade_board(b, {"date": "d", "high": 103, "low": 99.5, "close": 101.0},
                         prior_close=102.0, median_iv=0.2)
        assert g2["nodes"][0]["broke"] is False and g2["nodes"][0]["held"] is True

    def test_hold_break_none_without_prior_close(self):
        b = _board([_node("cluster", 100.0, True)])
        g = grade_board(b, {"date": "d", "high": 101, "low": 99, "close": 100},
                        prior_close=None, median_iv=0.2)
        nd = g["nodes"][0]
        assert nd["touched"] is True and nd["held"] is None and nd["broke"] is None

    def test_flip_pivot_no_hold_break(self):
        b = _board([_node("flip", 100.0, None)])
        g = grade_board(b, {"date": "d", "high": 101, "low": 99, "close": 100},
                        prior_close=98.0, median_iv=0.2)
        nd = g["nodes"][0]
        assert nd["touched"] is True and nd["held"] is None and nd["broke"] is None
        assert g["board"]["flip_pivot"] is True

    def test_wall_contained(self):
        b = _board([_node("put_wall", 95.0, False), _node("call_wall", 105.0, True)])
        inside = grade_board(b, {"date": "d", "high": 104, "low": 96, "close": 102}, median_iv=0.2)
        assert inside["board"]["wall_contained"] is True
        outside = grade_board(b, {"date": "d", "high": 108, "low": 96, "close": 106}, median_iv=0.2)
        assert outside["board"]["wall_contained"] is False

    def test_band_contained(self):
        b = _board([_node("anchor", 100.0, True)], spot=100.0)
        # tight range well inside a wide band (high iv)
        inside = grade_board(b, {"date": "d", "high": 100.5, "low": 99.5, "close": 100},
                             median_iv=0.5, band_mult=1.96)
        assert inside["board"]["band_contained"] is True
        # wide range pokes outside a narrow band (low iv)
        outside = grade_board(b, {"date": "d", "high": 108, "low": 92, "close": 100},
                              median_iv=0.05, band_mult=1.96)
        assert outside["board"]["band_contained"] is False

    def test_null_and_void_nodes_skipped(self):
        b = _board([
            {"role": "anchor", "strike": None, "sticky": None, "note": "absent"},  # null
            {"role": "void", "strike": None, "strike_lo": 101, "strike_hi": 104, "note": "range"},
            _node("cluster", 100.0, True),
        ])
        g = grade_board(b, {"date": "d", "high": 101, "low": 99, "close": 100},
                        prior_close=98.0, median_iv=0.2)
        assert [n["role"] for n in g["nodes"]] == ["cluster"]  # only the located, touchable node

    def test_degenerate_inputs_no_raise(self):
        assert grade_board(None, {"high": 1, "low": 0, "close": 0.5})["reason"] == "empty_board"
        assert grade_board({"nodes": []}, {"high": 1, "low": 0, "close": 0.5})["reason"] == "empty_board"
        b = _board([_node("anchor", 100.0, True)])
        assert grade_board(b, {"date": "d", "high": None, "low": 1, "close": 1})["reason"] == "no_price_data"
        assert grade_board(b, None)["reason"] == "no_price_data"


class TestAggregate:
    def _fake_wilson(self, k, n):
        return (max(0.0, k / n - 0.1), min(1.0, k / n + 0.1)) if n else None

    def test_per_role_rates_and_misses(self):
        # 3 anchor boards: 2 touched, 1 not
        grades = []
        for close, hi, lo, touch in [(100.5, 101, 99, True), (100.5, 101, 99, True), (95, 96, 94, False)]:
            grades.append(grade_board(_board([_node("anchor", 100.0, True)]),
                                      {"date": "d", "high": hi, "low": lo, "close": close},
                                      prior_close=98.0, median_iv=0.2))
        tr = aggregate_track_record(grades, ci_fn=self._fake_wilson)
        assert tr["schema"] == TR_SCHEMA
        a = tr["per_role"]["anchor"]
        assert a["n"] == 3 and a["hits"] == 2 and a["misses"] == 1
        assert abs(a["rate"] - 0.6667) < 1e-3
        assert a["ci"] is not None

    def test_sticky_slippery_split(self):
        grades = [
            grade_board(_board([_node("cluster", 100.0, True)]),
                        {"date": "d", "high": 101, "low": 99, "close": 99.5},
                        prior_close=98.0, median_iv=0.2),  # sticky, held
            grade_board(_board([_node("cluster", 100.0, False)]),
                        {"date": "d", "high": 101, "low": 99, "close": 100.6},
                        prior_close=98.0, median_iv=0.2),  # slippery, held=False
        ]
        tr = aggregate_track_record(grades, ci_fn=self._fake_wilson)
        c = tr["per_role"]["cluster"]
        assert c["sticky"]["n"] == 1 and c["slippery"]["n"] == 1

    def test_reasons_counted(self):
        grades = [grade_board(None, {"high": 1, "low": 0, "close": 0.5}),
                  grade_board(_board([_node("anchor", 100.0, True)]),
                              {"date": "d", "high": 101, "low": 99, "close": 100},
                              prior_close=98.0, median_iv=0.2)]
        tr = aggregate_track_record(grades)
        assert tr["reasons"]["empty_board"] == 1 and tr["reasons"]["ok"] == 1
        assert tr["n_boards"] == 2 and tr["n_boards_graded"] == 1


class TestLearnBandMult:
    def test_learns_a_multiplier(self):
        # ranges that poke ~1 sigma out; target 2/3 containment → mult near 1
        rows = [{"spot": 100.0, "median_iv": 0.2, "next_high": 101.2, "next_low": 98.8}] * 10
        m = learn_band_mult(rows, target=0.667)
        assert m is not None and 0.5 <= m <= 4.0

    def test_none_on_empty(self):
        assert learn_band_mult([]) is None
