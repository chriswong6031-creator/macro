"""China mean-reversion watch engine tests (engine/china_reversal.py).

Synthetic checks (no disk): the deepest within-sector 3-month dip ranks #1; ST /
delisting names and sub-floor market caps are screened OUT (responsibility filters,
NOT momentum/quality filters — those hurt the validated edge, see
research/CHINA_HK_STOCK_SIGNALS.md / reports/china-reversal-phase0.md)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_reversal as cr  # noqa: E402


def test_is_st():
    assert cr.is_st("*ST华业")
    assert cr.is_st("ST康美")
    assert cr.is_st(None, "Foo Co / *ST福")     # falls back to the combined display name
    assert cr.is_st("某某退")                    # 退市 (delisting) flag
    assert not cr.is_st("贵州茅台")
    assert not cr.is_st("Kweichow Moutai", "Kweichow Moutai")


def _panel():
    """16 names, 2 sectors. Each is flat at 100 for 57d then ramps to a target over the
    last 63d, so ret_3m = target/100 − 1 is controlled. 'A_DIP' (−30%) is the deepest
    real dip in Health; 'A_ST' (−40%) and 'A_MICRO' (−50%) are deeper but must be SCREENED."""
    dates = pd.bdate_range("2024-01-01", periods=120)

    def series(target):
        return pd.Series(list(np.full(57, 100.0)) + list(np.linspace(100.0, target, 63)), index=dates)

    targets = {
        "A_DIP": 70, "A1": 95, "A2": 100, "A3": 105, "A4": 100, "A5": 100, "A6": 98,
        "A_ST": 60, "A_MICRO": 50,                       # deeper, but screened out
        "B_DIP": 80, "B1": 100, "B2": 100, "B3": 110, "B4": 100, "B5": 100,
    }
    closes = pd.DataFrame({t: series(v) for t, v in targets.items()})
    sec = {t: ("Health" if t.startswith("A") else "Tech") for t in targets}
    name = {t: t for t in targets}
    name_zh = {t: ("*ST测试" if t == "A_ST" else t) for t in targets}
    mcap = {t: (10.0 if t == "A_MICRO" else 200.0) for t in targets}
    return closes, sec, name, name_zh, mcap


def test_deepest_dip_ranks_first_and_screens():
    closes, sec, name, name_zh, mcap = _panel()
    out = cr.reversal_watch(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap,
                            win=63, top_n=16, min_sector=6, mcap_floor_yi=30.0)
    assert out is not None
    tickers = [r["ticker"] for r in out["watch"]]
    # the deepest REAL dip in each sector surfaces; the screened names do not
    assert out["watch"][0]["ticker"] == "A_DIP"          # −30% Health, deepest survivor
    assert "B_DIP" in tickers                            # −20% Tech
    assert "A_ST" not in tickers and "A_MICRO" not in tickers
    assert out["screened"]["st"] >= 1 and out["screened"]["illiquid"] >= 1
    # ret_3m and within-sector rank are sane
    a = next(r for r in out["watch"] if r["ticker"] == "A_DIP")
    assert a["ret_3m"] == -30.0 and a["sector_rank"] == 1 and a["rev_z"] > 0


def test_guards():
    closes, sec, name, name_zh, mcap = _panel()
    assert cr.reversal_watch(pd.DataFrame(), sec, name) is None          # empty
    assert cr.reversal_watch(closes.head(40), sec, name, win=63) is None  # too short
