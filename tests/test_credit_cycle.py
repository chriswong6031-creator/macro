"""Pure-function tests for the BIS credit-cycle leaf — no network."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import bis  # noqa: E402
from engine import credit_cycle as cc  # noqa: E402

_Q = pd.period_range("2010Q1", periods=60, freq="Q").to_timestamp(how="end").normalize()
_CFG = {"boom_gap": 10.0, "delever_gap": -2.0, "countries": {
    "us": {"gap": "us_gap", "dsr": "us_dsr", "label_en": "United States", "label_zh": "美国"},
    "cn": {"gap": "cn_gap", "dsr": "cn_dsr", "label_en": "China", "label_zh": "中国"}}}


def test_parse_period():
    assert bis._parse_period("2025-Q3") == pd.Timestamp("2025-09-30")
    assert bis._parse_period("2025") == pd.Timestamp("2025-12-31")
    assert bis._parse_period("junk") is None


def test_state_thresholds():
    assert cc._state(15.0, _CFG) == "elevated risk"
    assert cc._state(5.0, _CFG) == "building"
    assert cc._state(0.0, _CFG) == "neutral"
    assert cc._state(-6.0, _CFG) == "deleveraging"
    assert cc._state(None, _CFG) == "—"


def test_compute_sorts_and_states():
    series = {
        "us_gap": pd.Series(np.full(60, -12.0), index=_Q),
        "us_dsr": pd.Series(np.full(60, 14.0), index=_Q),
        "cn_gap": pd.Series(np.full(60, 12.0), index=_Q),    # China in boom territory
        "cn_dsr": pd.Series(np.full(60, 19.0), index=_Q),
    }
    out = cc.compute(series, _CFG)
    assert out["rows"][0]["id"] == "cn"                      # highest gap first
    assert out["rows"][0]["gap_state"] == "elevated risk"
    assert out["rows"][1]["gap_state"] == "deleveraging"
    assert out["n_elevated"] == 1 and "1 of 2 elevated" in out["headline"]


def test_compute_change_and_none():
    rising = pd.Series(np.linspace(-12.0, -8.0, 60), index=_Q)   # gap rising +4 over 60q
    out = cc.compute({"us_gap": rising, "us_dsr": pd.Series(np.full(60, 14.0), index=_Q)}, _CFG)
    assert out["rows"][0]["gap_chg_1y"] is not None and out["rows"][0]["gap_chg_1y"] > 0
    assert cc.compute({}, _CFG) is None
