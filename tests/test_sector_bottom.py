"""Tests for engine.sector_bottom — the Sector Bottom Radar.

Covers the categorical verdict logic (the macro Fed-put gate flips a buyable
washout to a knife regime; deep washout reads as a falling knife; a non-bottoming
sector is 'trend'), the live member-breadth shares, and the radar assembly +
sort. The headline stays the VALIDATED bottom_confidence — these tests lock that
the radar never invents a new scored number on top of it.
"""
import numpy as np
import pandas as pd

from engine import sector_bottom as sb


def _read(state="DECLINE", bc=55.0, knife_level="none", pct_below=-3.0):
    return {"state": state, "bottom_confidence": bc, "knife": 0.0,
            "knife_level": knife_level, "pct_below_200d": pct_below,
            "above_200d": pct_below is not None and pct_below > 0}


def test_verdict_buyable_when_put_present_and_decent_bc():
    v = sb._verdict(_read(bc=55.0), put_absent=False)
    assert v["verdict"] == "buyable_washout"
    assert v["label_zh"]  # bilingual


def test_verdict_knife_regime_when_put_absent():
    # same washout, but the index Fed-put is ABSENT -> stand aside, not buyable
    v = sb._verdict(_read(bc=70.0), put_absent=True)
    assert v["verdict"] == "knife_regime"


def test_verdict_falling_knife_overrides_macro():
    # a deep, still-falling washout is a knife regardless of the macro gate
    v = sb._verdict(_read(bc=10.0, knife_level="high"), put_absent=False)
    assert v["verdict"] == "falling_knife"


def test_verdict_washout_forming_when_low_bc():
    v = sb._verdict(_read(bc=15.0), put_absent=False)
    assert v["verdict"] == "washout_forming"


def test_verdict_trend_when_not_bottoming():
    v = sb._verdict(_read(state="ADVANCE", bc=None), put_absent=False)
    assert v["verdict"] == "trend"


def test_member_breadth_shares():
    # 4 below-200d-and-turning, 4 strong-uptrend, 2 thin -> n=8, washed=4
    idx = pd.date_range("2020-01-01", periods=260, freq="B")
    cols = {}
    for i in range(4):  # washed out but reclaiming (last price > 10d mean, < 200d mean)
        s = np.linspace(100, 60, 250).tolist() + np.linspace(60, 64, 10).tolist()
        cols[f"DOWN{i}"] = s
    for i in range(4):  # healthy uptrend, above 200d
        cols[f"UP{i}"] = np.linspace(50, 120, 260).tolist()
    for i in range(2):  # too short -> dropped
        cols[f"THIN{i}"] = [np.nan] * 150 + np.linspace(10, 12, 110).tolist()
    m = pd.DataFrame(cols, index=idx)
    b = sb.member_breadth(m)
    assert b["n"] == 8
    assert b["below_200d_share"] == 0.5            # 4 of 8 below their 200-day
    assert 0.0 < b["turning_share"] <= 1.0         # the washed-out ones are reclaiming


def test_member_breadth_none_when_thin():
    m = pd.DataFrame({"A": [1, 2, 3]}, index=pd.date_range("2020", periods=3))
    assert sb.member_breadth(m) is None


def test_radar_sorts_bottoming_first_then_by_bc():
    reads = {
        "XLK": _read(state="ADVANCE", bc=None),     # trend
        "XLE": _read(state="DECLINE", bc=30.0),     # washout forming
        "XLF": _read(state="FRESH BUY", bc=70.0),   # buyable, highest bc
    }
    out = sb.radar(reads, names={"XLE": "Energy", "XLF": "Financials"},
                   put_absent=False)
    order = [r["ticker"] for r in out["sectors"]]
    assert order[0] == "XLF"           # highest-bc bottoming sector first
    assert order[-1] == "XLK"          # the trend sector last
    assert out["n_washed_out"] == 2
    assert out["macro_gate"] == "put-present"


def test_radar_macro_gate_flips_all_to_knife_regime():
    reads = {"XLF": _read(state="FRESH BUY", bc=70.0)}
    out = sb.radar(reads, put_absent=True)
    assert out["sectors"][0]["verdict"] == "knife_regime"
    assert out["macro_gate"] == "put-absent"


def test_radar_headline_is_validated_bottom_confidence_not_a_new_score():
    # invariant: the row's headline number is bottom_confidence verbatim, the radar
    # adds only a categorical verdict (no invented composite score field).
    reads = {"XLF": _read(state="FRESH BUY", bc=63.0)}
    row = sb.radar(reads, put_absent=False)["sectors"][0]
    assert row["bottom_confidence"] == 63.0
    assert "score" not in row          # no new scored number layered on top
