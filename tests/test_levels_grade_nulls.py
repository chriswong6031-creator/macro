"""tests/test_levels_grade_nulls.py — R2.4b: stronger nulls, intraday containment,
and the index grading lane's driver plumbing.

The properties that fail silently: a mirror null graded with flipped approach-side
logic (making the real level look like it beats a null it doesn't), a prevday null
that scores an untouched extreme, pierce depth measured on the wrong side of the
level, the SPXW→SPX bar alias silently missing (index chunk grades zero boards with
exit 0), and old-schema grade dicts crashing the aggregator instead of degrading.
"""
from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.levels_grade import aggregate_track_record, grade_board  # noqa: E402
import scripts.build_levels_track_record as tr  # noqa: E402


def _board(nodes, spot=100.0, regime="sticky", asof="2026-07-16", root="TEST"):
    return {"schema": "levels.v1", "root": root, "asof": asof, "spot": spot,
            "spot_ref": spot, "regime": {"label": regime},
            "nodes": nodes, "stacks": []}


def _node(role, strike, sticky=None):
    return {"role": role, "strike": strike, "weight": 1.0, "sticky": sticky,
            "brightness": 0.5, "note": ""}


def _bar(high, low, close, date="2026-07-17"):
    return {"date": date, "high": high, "low": low, "close": close}


# ─── equidistant-mirror null ──────────────────────────────────────────────────


class TestMirrorNull:
    def test_real_holds_while_mirror_breaks(self):
        # call_wall 102 on spot 100 → mirror 98. prior 99.5, close 97.8:
        # real level held (approach and close both below 102); the mirror was
        # crossed (99.5 above 98, close below) → null_held False.
        b = _board([_node("call_wall", 102.0, True)])
        g = grade_board(b, _bar(103.0, 97.5, 97.8), prior_close=99.5, median_iv=0.2)
        nd = g["nodes"][0]
        assert nd["touched"] is True and nd["held"] is True
        assert nd["null_touched"] is True
        assert nd["null_held"] is False

    def test_mirror_strike_is_2spot_minus_strike(self):
        # strike 105 on spot 100 → mirror 95: bar low 96 never reaches it
        b = _board([_node("call_wall", 105.0, True)])
        g = grade_board(b, _bar(106.0, 96.0, 100.0), prior_close=100.0, median_iv=0.2)
        assert g["nodes"][0]["null_touched"] is False
        assert g["nodes"][0]["null_held"] is None

    def test_null_absent_without_spot(self):
        b = _board([_node("call_wall", 102.0, True)], spot=None)
        g = grade_board(b, _bar(103.0, 97.5, 99.0), prior_close=99.5, median_iv=0.2)
        assert g["nodes"][0]["null_touched"] is None
        assert g["nodes"][0]["null_held"] is None

    def test_flip_mirror_touch_scored_but_never_held(self):
        b = _board([_node("flip", 101.0, None)])
        g = grade_board(b, _bar(102.0, 98.0, 100.0), prior_close=100.0, median_iv=0.2)
        nd = g["nodes"][0]
        assert nd["null_touched"] is True   # mirror 99 inside [98, 102]
        assert nd["null_held"] is None      # flip is touch-scored, so is its null


# ─── pierce depth (intraday trade-through) ────────────────────────────────────


class TestPierce:
    def test_approach_from_below_measures_the_high_side(self):
        # prior 99 below wall 100; high 101.5 on spot 100 → 1.5% through
        b = _board([_node("call_wall", 100.0, True)])
        g = grade_board(b, _bar(101.5, 98.5, 99.5), prior_close=99.0, median_iv=0.2)
        assert g["nodes"][0]["pierce_pct"] == pytest.approx(1.5)

    def test_approach_from_above_measures_the_low_side(self):
        b = _board([_node("put_wall", 100.0, True)])
        g = grade_board(b, _bar(101.0, 99.0, 100.5), prior_close=101.0, median_iv=0.2)
        assert g["nodes"][0]["pierce_pct"] == pytest.approx(1.0)

    def test_untouched_has_no_pierce(self):
        b = _board([_node("call_wall", 110.0, True)])
        g = grade_board(b, _bar(102.0, 98.0, 100.0), prior_close=99.0, median_iv=0.2)
        assert g["nodes"][0]["pierce_pct"] is None


# ─── intraday containment variants ────────────────────────────────────────────


class TestIntradayContainment:
    def test_close_inside_but_range_pierced(self):
        b = _board([_node("put_wall", 95.0, True), _node("call_wall", 105.0, True)])
        g = grade_board(b, _bar(106.0, 96.0, 104.0), prior_close=100.0, median_iv=0.2)
        assert g["board"]["wall_contained"] is True          # close 104 in [95,105]
        assert g["board"]["wall_range_contained"] is False   # high 106 pierced
    def test_band_close_looser_than_band_range(self):
        # spot 100, iv 0.2, mult 1.96 → band ≈ [97.53, 102.47]; low 96 breaks the
        # range test but the close sits comfortably inside
        b = _board([_node("call_wall", 105.0, True)])
        g = grade_board(b, _bar(101.0, 96.0, 101.0), prior_close=100.0, median_iv=0.2)
        assert g["board"]["band_contained"] is False
        assert g["board"]["band_close_contained"] is True


# ─── prior-day-extreme null ───────────────────────────────────────────────────


class TestPrevdayNull:
    def test_prevday_levels_graded_like_walls(self):
        b = _board([_node("call_wall", 105.0, True)])
        g = grade_board(b, _bar(102.0, 100.0, 100.5), prior_close=100.0,
                        median_iv=0.2, prior_bar={"high": 101.0, "low": 98.0})
        p = g["board"]["prevday"]
        assert p["high_touched"] is True and p["high_held"] is True   # poked, closed back
        assert p["low_touched"] is False and p["low_held"] is None    # never reached
        assert p["range_contained_close"] is True                     # 98 ≤ 100.5 ≤ 101
        assert p["range_contained_range"] is False                    # high 102 > 101

    def test_prevday_absent_without_prior_bar(self):
        b = _board([_node("call_wall", 105.0, True)])
        g = grade_board(b, _bar(102.0, 100.0, 100.5), prior_close=100.0, median_iv=0.2)
        assert g["board"]["prevday"] is None

    def test_degenerate_prior_bar_rejected(self):
        b = _board([_node("call_wall", 105.0, True)])
        g = grade_board(b, _bar(102.0, 100.0, 100.5), prior_close=100.0,
                        median_iv=0.2, prior_bar={"high": 98.0, "low": 101.0})
        assert g["board"]["prevday"] is None


# ─── aggregation ──────────────────────────────────────────────────────────────


class TestAggregate:
    def _grades(self):
        out = []
        for close, pb in ((97.8, {"high": 101.0, "low": 98.0}),
                          (100.5, {"high": 102.0, "low": 99.0})):
            b = _board([_node("call_wall", 102.0, True), _node("put_wall", 96.0, True)])
            out.append(grade_board(b, _bar(103.0, 97.5, close), prior_close=99.5,
                                   median_iv=0.2, prior_bar=pb))
        return out

    def test_null_and_intraday_ride_the_track_record(self):
        agg = aggregate_track_record(self._grades())
        cw = agg["per_role"]["walls"]
        assert cw["n"] == 2
        nm = agg["per_role"]["cluster"]["null_equidistant"]
        assert nm["n"] == 0  # no cluster nodes → absent, not invented
        board = agg["board"]
        assert board["wall_range_contained"]["n"] == 2
        assert board["band_close_contained"]["n"] == 2
        assert board["prevday"]["range_contained_close"]["n"] == 2

    def test_old_schema_grades_degrade_not_crash(self):
        # a pre-R2.4b grade dict: no null/pierce node keys, no prevday board block
        old = {"reason": "ok",
               "nodes": [{"role": "cluster", "touched": True, "held": True,
                          "broke": False, "sticky": True, "post_touch_move_pct": 0.5}],
               "board": {"wall_contained": True, "band_contained": True}}
        agg = aggregate_track_record([old])
        assert agg["per_role"]["cluster"]["n"] == 1
        assert agg["per_role"]["cluster"]["null_equidistant"]["n"] == 0
        assert agg["board"]["wall_range_contained"]["n"] == 0
        assert agg["board"]["prevday"]["high_held"]["n"] == 0


# ─── driver: index lane plumbing ──────────────────────────────────────────────


class TestIndexLane:
    def test_universe_index_resolves_the_anchor_roots(self):
        roots = tr._resolve_roots(Namespace(roots="", universe="index"))
        assert roots == list(tr.INDEX_ROOTS)
        assert "SPY" in roots and "SPX" in roots and "SPXW" in roots

    def test_spxw_grades_against_the_spx_bars(self, tmp_path, monkeypatch):
        ix = tmp_path / "index_bars"
        ix.mkdir()
        df = pd.DataFrame(
            {"open": [1.0], "close": [2.0], "high": [3.0], "low": [0.5], "volume": [9.0]},
            index=pd.DatetimeIndex([pd.Timestamp("2026-07-16")], name="Date"))
        df.to_parquet(ix / "SPX.parquet")
        monkeypatch.setattr(tr, "_STOCKS_DIR", tmp_path / "stocks")
        monkeypatch.setattr(tr, "_INDEX_BARS_DIR", ix)
        for root in ("SPX", "SPXW"):
            bars = tr._load_stock_bars(root)
            assert bars is not None and float(bars.iloc[0]["high"]) == 3.0
        assert tr._load_stock_bars("SPY") is None  # absent stays absent — coverage-honest

    def test_stocks_dir_still_wins_over_index_bars(self, tmp_path, monkeypatch):
        st = tmp_path / "stocks"; ix = tmp_path / "index_bars"
        st.mkdir(); ix.mkdir()
        idx = pd.DatetimeIndex([pd.Timestamp("2026-07-16")], name="Date")
        pd.DataFrame({"close": [1.0]}, index=idx).to_parquet(st / "AAPL.parquet")
        pd.DataFrame({"close": [99.0]}, index=idx).to_parquet(ix / "AAPL.parquet")
        monkeypatch.setattr(tr, "_STOCKS_DIR", st)
        monkeypatch.setattr(tr, "_INDEX_BARS_DIR", ix)
        assert float(tr._load_stock_bars("AAPL").iloc[0]["close"]) == 1.0

    def test_prior_bar_is_the_board_sessions_extremes(self):
        bars = pd.DataFrame(
            {"high": [10.0, 20.0], "low": [5.0, 15.0], "close": [8.0, 18.0]},
            index=pd.DatetimeIndex([pd.Timestamp("2026-07-15"), pd.Timestamp("2026-07-16")],
                                   name="Date"))
        assert tr._prior_bar(bars, "2026-07-16") == {"high": 20.0, "low": 15.0}
        assert tr._prior_bar(bars, "2026-07-15") == {"high": 10.0, "low": 5.0}
        assert tr._prior_bar(bars, "2026-07-01") is None
