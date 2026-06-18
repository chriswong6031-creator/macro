"""International rates desk tests (engine/intl_rates.py): curve-shape thresholds,
sparkline downsampling, carry sign, and store-backed smoke tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import intl_rates as R  # noqa: E402


def test_curve_shape_thresholds():
    assert R._curve_shape(None)[0] == "na"
    assert R._curve_shape(-0.3)[0] == "inverted"
    assert R._curve_shape(0.2)[0] == "flat"
    assert R._curve_shape(1.0)[0] == "normal"
    assert R._curve_shape(2.5)[0] == "steep"


def test_spark_downsample():
    s = pd.Series(range(500), index=pd.bdate_range("2020-01-01", periods=500))
    out = R._spark(s, n=48, years=6)
    assert 0 < len(out) <= 60
    assert all(isinstance(v, float) for v in out)
    assert R._spark(None) == []
    assert R._spark(pd.Series(dtype=float)) == []


def _records():
    return [
        {"cc": "JP", "name": "Japan", "name_zh": "日本", "flag": "🇯🇵", "region": "Asia",
         "liquidity": "neutral",
         "macro": {"yield_10y": 2.6, "short_3m": 1.2, "policy_rate": 0.5, "curve": 1.4,
                   "real_yield": 0.5, "cpi_yoy": 2.1, "yield_10y_chg3m": 0.3},
         "macro_asof": {"yield_10y": "2026-05", "cpi_yoy": "2021-06"}},
        {"cc": "TW", "name": "Taiwan", "name_zh": "台湾", "flag": "🇹🇼", "region": "Asia",
         "liquidity": "unknown",
         "macro": {"yield_10y": None, "short_3m": None, "policy_rate": None, "curve": None,
                   "real_yield": None, "cpi_yoy": None, "yield_10y_chg3m": None},
         "macro_asof": {"yield_10y": None, "cpi_yoy": "2026-04"}},
    ]


def test_rates_desk_structure_and_carry_sign():
    desk = R.rates_desk(_records())
    assert "anchor" in desk and "rows" in desk
    rows = {r["cc"]: r for r in desk["rows"]}
    assert set(rows) == {"JP", "TW"}
    jp = rows["JP"]
    assert jp["shape"] == "normal"          # curve 1.4 -> normal
    us10 = desk["anchor"].get("y10")
    if us10 is not None:                     # committed store carries DGS10
        assert jp["carry_vs_us"] is not None
        assert abs(jp["carry_vs_us"] - (jp["y10"] - us10)) < 1e-6
    # Taiwan degrades to a no-curve card, never raises
    assert rows["TW"]["y10"] is None and rows["TW"]["shape"] == "na"


def test_us_anchor_present_from_store():
    """The US anchor must resolve even though intl_macro lacks us_10y (fred fallback)."""
    an = R.us_anchor()
    assert "y10" in an and "spark" in an
    if an["y10"] is not None:
        assert 0 < an["y10"] < 20


def test_ecb_liquidity_smoke():
    liq = R.ecb_liquidity_impulse()
    # may be None if the series is absent, but must not raise and must be well-formed
    if liq is not None:
        assert "level_eur_tn" in liq and "draining" in liq
        assert isinstance(liq["draining"], bool)
        assert liq["read_en"] and liq["read_zh"]
