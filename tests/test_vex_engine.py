"""tests/test_vex_engine.py — Phase B VEX (vega exposure) engine.

Hermetic: crafted greeks + OI frames with known vega-weighted answers. No store, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.vex_engine import compute_vex, VEX_PM, SCHEMA  # noqa: E402
from engine.options_hub import MULT  # noqa: E402

ASOF = "2024-06-14"
EXP = "2024-07-19"


def _greeks(rows, spot=100.0):
    """rows = list of (strike, right 'C'/'P', vega)."""
    return pd.DataFrame([
        {"date": ASOF, "expiration": EXP, "strike": k, "right": r,
         "vega": v, "underlying_price": spot}
        for (k, r, v) in rows
    ])


def _oi(rows):
    """rows = list of (strike, right, open_interest)."""
    return pd.DataFrame([
        {"expiration": EXP, "strike": k, "right": r, "open_interest": oi}
        for (k, r, oi) in rows
    ])


class TestComputeVex:
    def test_net_vex_formula_and_sign(self):
        # one call: net_vex = +1 * vega * oi * MULT * VEX_PM
        g = _greeks([(105.0, "C", 0.20)])
        oi = _oi([(105.0, "C", 50000)])
        out = compute_vex(g, oi, ASOF, "TEST")
        assert out["schema"] == SCHEMA
        assert out["spot_ref"] == 100.0
        expected_mm = (0.20 * 50000 * MULT * VEX_PM) / 1e6
        assert abs(out["net_vex_mm"] - round(expected_mm, 4)) < 1e-6
        # a put contributes with negative sign
        g2 = _greeks([(95.0, "P", 0.20)])
        oi2 = _oi([(95.0, "P", 50000)])
        assert compute_vex(g2, oi2, ASOF, "TEST")["net_vex_mm"] < 0

    def test_walls_and_flip(self):
        # big positive VEX at 105 (call), big negative at 95 (put), small noise at spot
        g = _greeks([(105.0, "C", 0.30), (95.0, "P", 0.30), (100.0, "C", 0.02)])
        oi = _oi([(105.0, "C", 80000), (95.0, "P", 80000), (100.0, "C", 1000)])
        out = compute_vex(g, oi, ASOF, "TEST")
        assert out["pos_vex_wall"] == 105.0   # heaviest positive above spot
        assert out["neg_vex_wall"] == 95.0    # heaviest negative below spot
        # cumulative net VEX crosses zero somewhere between 95 (neg) and 105 (pos)
        assert out["vex_flip"] is not None and 95.0 <= out["vex_flip"] <= 105.0

    def test_only_positive_oi_used(self):
        g = _greeks([(105.0, "C", 0.20), (110.0, "C", 0.20)])
        oi = _oi([(105.0, "C", 50000), (110.0, "C", 0)])  # 110 has zero OI → excluded
        out = compute_vex(g, oi, ASOF, "TEST")
        strikes = [r["strike"] for r in out["by_strike"]]
        assert 110.0 not in strikes and 105.0 in strikes

    def test_by_strike_window(self):
        # a strike 40% away is outside the ±20% window
        g = _greeks([(105.0, "C", 0.2), (140.0, "C", 0.2)])
        oi = _oi([(105.0, "C", 1000), (140.0, "C", 1000)])
        out = compute_vex(g, oi, ASOF, "TEST")
        strikes = [r["strike"] for r in out["by_strike"]]
        assert 105.0 in strikes and 140.0 not in strikes
        assert out["by_strike_full_n"] == 2  # full count preserved pre-window

    def test_vega_nan_treated_as_zero(self):
        g = _greeks([(105.0, "C", float("nan"))])
        oi = _oi([(105.0, "C", 50000)])
        out = compute_vex(g, oi, ASOF, "TEST")
        assert out["net_vex_mm"] == 0.0  # nan vega → 0 contribution, no crash

    def test_empty_and_degenerate(self):
        assert compute_vex(None, None, ASOF, "X")["schema"] == SCHEMA
        assert compute_vex(pd.DataFrame(), None, ASOF, "X")["spot_ref"] is None
        # no matching-date rows
        g = _greeks([(105.0, "C", 0.2)])
        assert compute_vex(g, _oi([(105.0, "C", 1)]), "2099-01-01", "X")["spot_ref"] is None
        # no positive OI
        g2 = _greeks([(105.0, "C", 0.2)])
        assert compute_vex(g2, _oi([(105.0, "C", 0)]), ASOF, "X")["by_strike"] == []
