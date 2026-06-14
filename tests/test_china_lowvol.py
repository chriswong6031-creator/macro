"""China defensive low-vol sleeve engine tests (engine/china_lowvol.py).

Synthetic checks: the lowest-volatility name ranks #1; a flat/halted (sub-floor σ)
name and ST + sub-floor market caps are screened OUT. The low-vol anomaly is a
DEFENSIVE tilt (research/CHINA_HK_STOCK_SIGNALS.md / reports/china-lowvol-phase0.md)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_lowvol as cl  # noqa: E402


def _panel(seed: int = 0):
    """14 names, 2 sectors, 400 bdays. Per-name daily σ is controlled so annualized vol
    is known; 'DEF' is the lowest-vol real name, 'FLAT' is a halted near-zero-σ artifact."""
    rng = np.random.default_rng(seed)
    n = 400
    dates = pd.bdate_range("2024-01-01", periods=n)
    sigs = {"DEF": 0.008, "A1": 0.02, "A2": 0.025, "A3": 0.03, "A4": 0.028, "A5": 0.026, "A6": 0.024,
            "FLAT": 0.0005, "ST_LOWV": 0.009,
            "B1": 0.02, "B2": 0.022, "B3": 0.03, "B4": 0.035, "B5": 0.028, "B6": 0.024, "B7": 0.027}
    closes = pd.DataFrame({t: pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, s, n)), index=dates)
                           for t, s in sigs.items()})
    sec = {t: ("Health" if t in ("DEF", "FLAT", "ST_LOWV") or t.startswith("A") else "Tech") for t in sigs}
    name = {t: t for t in sigs}
    name_zh = {t: ("*ST测试" if t == "ST_LOWV" else t) for t in sigs}
    mcap = {t: 200.0 for t in sigs}
    return closes, sec, name, name_zh, mcap


def test_lowest_vol_ranks_first_and_screens():
    closes, sec, name, name_zh, mcap = _panel()
    out = cl.lowvol_sleeve(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap,
                           win=252, top_n=14, min_sector=6, mcap_floor_yi=30.0, vol_floor=0.06)
    assert out is not None
    sleeve = [r["ticker"] for r in out["sleeve"]]
    assert sleeve[0] == "DEF"                          # lowest real vol surfaces first
    assert "FLAT" not in sleeve                        # halted/near-zero-σ artifact screened
    assert "ST_LOWV" not in sleeve                     # ST screened even though it's low-vol
    assert out["screened"]["flat"] >= 1 and out["screened"]["st"] >= 1
    d = out["sleeve"][0]
    assert d["vol_pct_ann"] > 6.0 and d["vol_rank_pct"] <= 30   # annualized σ, low rank


def test_mcap_floor():
    closes, sec, name, name_zh, mcap = _panel()
    mcap["DEF"] = 5.0                                  # below floor → drop the would-be #1
    out = cl.lowvol_sleeve(closes, sec, name, tkr_name_zh=name_zh, tkr_mktcap=mcap,
                           win=252, min_sector=6, mcap_floor_yi=30.0, vol_floor=0.06)
    assert "DEF" not in [r["ticker"] for r in out["sleeve"]]
    assert out["screened"]["illiquid"] >= 1


def test_guards():
    closes, sec, name, *_ = _panel()
    assert cl.lowvol_sleeve(pd.DataFrame(), sec, name) is None
    assert cl.lowvol_sleeve(closes.head(40), sec, name, win=252) is None
