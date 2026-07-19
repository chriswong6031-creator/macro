"""tests/test_moves_engine.py — the learned expected-move ("Moves") engine.

Hermetic: crafted spot/IV + graded-board rows with hand-computed answers. No store, no clock.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.moves_engine import (  # noqa: E402
    expected_move, per_ticker_calibration, pick_learned_mult, moves_payload,
    SCHEMA, DEFAULT_BAND_MULT, MIN_CALIB_SESSIONS,
)

TRADING_DAYS = 252.0


def _fake_ci(k, n):
    # deterministic stand-in for wilson_ci — just a symmetric ±0.1 clamp, enough to test wiring
    p = k / n
    return (max(0.0, p - 0.1), min(1.0, p + 0.1))


class TestExpectedMove:
    def test_pct_formula_and_symmetry(self):
        spot, iv, mult = 100.0, 0.20, 1.96
        em = expected_move(spot, iv, band_mult=mult)
        expected_pct = iv * math.sqrt(1.0 / TRADING_DAYS) * mult * 100.0
        assert em["pct"] == round(expected_pct, 4)
        assert em["band_mult"] == 1.96 and em["horizon_days"] == 1.0
        # band symmetric around spot
        assert abs((spot - em["lo"]) - (em["hi"] - spot)) < 1e-6
        assert em["lo"] < spot < em["hi"]

    def test_horizon_scales_with_sqrt_time(self):
        one = expected_move(100.0, 0.20)["pct"]
        four = expected_move(100.0, 0.20, horizon_days=4.0)["pct"]
        assert abs(four - one * 2.0) < 1e-3  # sqrt(4) = 2

    def test_none_on_bad_input(self):
        assert expected_move(None, 0.2) is None
        assert expected_move(100.0, None) is None
        assert expected_move(100.0, 0.0) is None
        assert expected_move(0.0, 0.2) is None
        assert expected_move(-5.0, 0.2) is None


class TestPerTickerCalibration:
    def _rows(self, n_hits, n_miss, band_mult=1.96, start_day=1):
        rows = []
        d = start_day
        for _ in range(n_hits):
            rows.append({"band_contained": True, "band_mult": band_mult,
                         "session_date": f"2024-06-{d:02d}"}); d += 1
        for _ in range(n_miss):
            rows.append({"band_contained": False, "band_mult": band_mult,
                         "session_date": f"2024-06-{d:02d}"}); d += 1
        return rows

    def test_null_below_min_sessions(self):
        rows = self._rows(MIN_CALIB_SESSIONS - 1, 0)
        assert per_ticker_calibration(rows) is None
        assert per_ticker_calibration([]) is None
        assert per_ticker_calibration(None) is None

    def test_rate_hits_misses(self):
        rows = self._rows(8, 2)  # 10 sessions, 8 contained
        c = per_ticker_calibration(rows)
        assert c["n_sessions"] == 10 and c["hits"] == 8 and c["misses"] == 2
        assert c["contained_rate"] == 0.8
        assert c["band_mult"] == 1.96
        assert c["since"] == "2024-06-01" and c["through"] == "2024-06-10"

    def test_none_band_contained_rows_skipped(self):
        rows = self._rows(8, 1)
        # add 3 ungraded rows (band_contained None) — must NOT count toward n
        rows += [{"band_contained": None, "band_mult": 1.96, "session_date": "2024-07-01"}] * 3
        c = per_ticker_calibration(rows)
        assert c["n_sessions"] == 9  # only the 9 graded rows

    def test_ci_attached_when_fn_given(self):
        rows = self._rows(9, 1)
        c = per_ticker_calibration(rows, ci_fn=_fake_ci)
        assert "ci" in c and c["ci"][0] <= c["contained_rate"] <= c["ci"][1]

    def test_min_sessions_boundary(self):
        assert per_ticker_calibration(self._rows(MIN_CALIB_SESSIONS, 0)) is not None


class TestPickLearnedMult:
    def test_regime_preferred_then_all(self):
        lbm = {"all": 1.5, "sticky": 1.2, "slippery": 2.4}
        assert pick_learned_mult(lbm, "sticky") == 1.2
        assert pick_learned_mult(lbm, "slippery") == 2.4
        assert pick_learned_mult(lbm, None) == 1.5      # falls back to all
        assert pick_learned_mult(lbm, "weird") == 1.5   # unknown regime → all

    def test_falls_back_to_all_when_cohort_missing(self):
        lbm = {"all": 1.7, "sticky": None}
        assert pick_learned_mult(lbm, "sticky") == 1.7

    def test_none_when_absent_or_not_dict(self):
        assert pick_learned_mult(None, "sticky") is None
        assert pick_learned_mult({}, "sticky") is None
        assert pick_learned_mult({"sticky": None, "all": None}, "sticky") is None
        assert pick_learned_mult("nope", "sticky") is None


class TestMovesPayload:
    def test_shape_and_matched_band_mult(self):
        cal = per_ticker_calibration(
            [{"band_contained": True, "band_mult": 1.96, "session_date": "2024-06-01"}] * 9,
            ci_fn=_fake_ci)
        # atm_iv is PERCENT (15.0 = 15%), matching options_hub.vol/v1
        p = moves_payload("SPY", "2024-06-14", 500.0, 15.0,
                          calibration=cal, learned_band_mult={"all": 1.3, "sticky": 1.1},
                          regime="sticky")
        assert p["schema"] == SCHEMA and p["root"] == "SPY" and p["asof"] == "2024-06-14"
        assert p["spot_ref"] == 500.0 and p["atm_iv"] == 15.0 and p["regime"] == "sticky"
        # the drawn band and the calibration are at the SAME multiplier
        assert p["expected_move"]["band_mult"] == DEFAULT_BAND_MULT
        assert p["calibration"]["band_mult"] == DEFAULT_BAND_MULT
        # learned mult note is the regime cohort (sticky=1.1), with the 2/3 target
        assert p["learned_band_mult"]["value"] == 1.1
        assert p["learned_band_mult"]["target_containment"] == 0.667

    def test_atm_iv_percent_converted_to_decimal_for_band(self):
        """Regression: the payload takes ATM IV in PERCENT; the band must use the decimal.

        Would have caught the 100× unit blowup (13.71% read as 1371 vol → pct ~169%).
        """
        p = moves_payload("SPY", "2024-06-14", 750.72, 13.7057)  # 13.71%, like real SPY
        em = p["expected_move"]
        # identical to feeding the decimal directly to the low-level fn
        assert em["pct"] == expected_move(750.72, 0.137057)["pct"]
        assert em["pct"] < 5.0                 # a sane 1-day move, not 169%
        assert 700.0 < em["lo"] < em["hi"] < 800.0   # band hugs spot, never negative

    def test_honest_nulls(self):
        # no spot → no expected move, but schema + calibration null still present
        p = moves_payload("X", "2024-06-14", None, 15.0)
        assert p["schema"] == SCHEMA
        assert p["expected_move"] is None
        assert p["calibration"] is None
        assert p["learned_band_mult"] is None  # no learned_band_mult passed
        # no atm_iv → no expected move either
        assert moves_payload("X", "2024-06-14", 500.0, None)["expected_move"] is None

    def test_convention_is_display_tier(self):
        p = moves_payload("X", "2024-06-14", 100.0, 20.0)
        conv = p["convention"].lower()
        assert "not a buy" in conv and "prophecy" in conv
