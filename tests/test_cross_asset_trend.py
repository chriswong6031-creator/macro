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


# CA-W3-R5: new legs in _DEFAULT_UNIVERSE and _NAME_LABEL ─────────────────────

def test_default_universe_contains_w3_legs():
    """CA-W3-R5: equity_intl/equity_em/duration must be in _DEFAULT_UNIVERSE."""
    assert "equity_intl" in cat._DEFAULT_UNIVERSE
    assert "equity_em" in cat._DEFAULT_UNIVERSE
    assert "duration" in cat._DEFAULT_UNIVERSE


def test_default_universe_w3_leg_tickers():
    """CA-W3-R5: new legs must map to EFA/EEM/TLT."""
    assert cat._DEFAULT_UNIVERSE["equity_intl"][1] == "EFA"
    assert cat._DEFAULT_UNIVERSE["equity_em"][1] == "EEM"
    assert cat._DEFAULT_UNIVERSE["duration"][1] == "TLT"


def test_default_universe_w3_legs_are_equity_and_rates_class():
    """CA-W3-R5: equity_intl/em are 'equity'; duration is 'rates'."""
    assert cat._DEFAULT_UNIVERSE["equity_intl"][3] == "equity"
    assert cat._DEFAULT_UNIVERSE["equity_em"][3] == "equity"
    assert cat._DEFAULT_UNIVERSE["duration"][3] == "rates"


def test_name_label_contains_w3_legs():
    """CA-W3-R5: _NAME_LABEL must have bilingual entries for new legs."""
    for key in ("equity_intl", "equity_em", "duration"):
        assert key in cat._NAME_LABEL, f"_NAME_LABEL missing {key!r}"
        en, zh = cat._NAME_LABEL[key]
        assert isinstance(en, str) and en, f"empty EN label for {key!r}"
        assert isinstance(zh, str) and zh, f"empty ZH label for {key!r}"


def test_name_label_w3_exact_values():
    """CA-W3-R5: bilingual labels must match the spec exactly."""
    assert cat._NAME_LABEL["equity_intl"] == ("Intl stocks (DM)", "国际发达股市")
    assert cat._NAME_LABEL["equity_em"] == ("EM stocks", "新兴市场股市")
    assert cat._NAME_LABEL["duration"] == ("Long Treasuries", "长期美债")


def test_concentration_universe_not_touched():
    """CA-W3-R5: DEFAULT_MARKETS (concentration) in cross_asset.py must NOT include EFA/EEM/TLT."""
    from engine.cross_asset import DEFAULT_MARKETS
    tickers = {v[1] for v in DEFAULT_MARKETS.values()}
    assert "EFA" not in tickers
    assert "EEM" not in tickers
    assert "TLT" not in tickers
