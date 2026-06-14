"""Pure-function tests for the cross-asset TREND / ratios / carry leaf — no network."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import cross_asset_trend as cat  # noqa: E402

_IDX = pd.date_range("2015-01-01", periods=400, freq="B")


def _price(slope: float, start: float = 100.0) -> pd.Series:
    return pd.Series(np.linspace(start, start * (1 + slope), len(_IDX)), index=_IDX)


def test_tsmom_alloc_direction_and_bounds():
    up = cat.tsmom_alloc(_price(1.0))      # +100% over the window -> uptrend
    dn = cat.tsmom_alloc(_price(-0.5))     # -50% -> downtrend
    flat = cat.tsmom_alloc(pd.Series(100.0, index=_IDX))
    assert up.iloc[-1] > 0.6 and dn.iloc[-1] < -0.6
    assert abs(flat.iloc[-1]) < 0.5
    for a in (up, dn, flat):
        assert a.min() >= -1.0 and a.max() <= 1.0      # leverage-free


def test_bond_price_index_inverse_to_yield():
    rising_yield = pd.Series(np.linspace(2.0, 5.0, len(_IDX)), index=_IDX)   # yields UP
    px = cat._bond_price_index(rising_yield)
    assert px.iloc[-1] < px.iloc[0]                    # rising yields -> falling bond price


def test_ratio_panel_bounds():
    uni = {"copper": _price(0.5), "gold": _price(0.1), "silver": _price(0.2),
           "oil": _price(0.3), "equity_us": _price(0.4)}
    out = cat.ratio_panel(uni, {"ratios": {"pctile_lookback_d": 252}})
    assert any(r["key"] == "copper_gold" for r in out)
    for r in out:
        assert r["value"] > 0
        assert r["pctile"] is None or 0 <= r["pctile"] <= 100
        assert r["state"] in ("elevated", "depressed", "mid")


def test_tsmom_panel_breadth_sign():
    uni = {"a": _price(1.0), "b": _price(0.8), "c": _price(0.6),   # 3 up
           "d": _price(-0.5), "e": _price(-0.4)}                    # 2 down
    cfg = {"universe": {k: ["yahoo", k, "close",
                            ("equity" if k in ("a", "b") else "commodity")] for k in uni},
           "tsmom": {"lookbacks_d": [63, 126, 252], "skip_d": 5}}
    p = cat.tsmom_panel(cfg, uni)
    assert p["n"] == 5 and p["n_up"] >= 3 and p["n_down"] >= 2
    assert p["breadth"] > 0                            # net uptrend
    assert "trend" in p["rows"][0] and p["rows"][0]["score"] >= p["rows"][-1]["score"]


def test_snapshot_degrades_with_too_few_legs(monkeypatch):
    monkeypatch.setattr(cat, "_load_universe", lambda cfg=None: {"a": _price(1.0)})
    assert cat.snapshot() is None                      # <4 legs -> graceful None
