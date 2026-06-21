"""Smoke + invariant tests for the display-only yield-curve analytics leaf."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from engine import yield_curve as yc
from engine.bonds import _TAXONOMY


def _curve_frame(n: int = 700, seed: int = 7) -> pd.DataFrame:
    """A synthetic frame carrying the full Treasury curve + real / breakeven / TP nodes."""
    idx = pd.bdate_range("2018-01-01", periods=n)
    rng = np.random.default_rng(seed)
    walk = lambda base, vol: base + np.cumsum(rng.normal(0, vol, n))  # noqa: E731
    f = pd.DataFrame(index=idx)
    # an upward-sloping curve by construction (each tenor a small spread over the last)
    f["us3m"] = walk(4.2, 0.01)
    f["us6m"] = f["us3m"] + 0.05
    f["us1y"] = f["us3m"] + 0.10
    f["us2y"] = f["us3m"] + 0.15
    f["us3y"] = f["us3m"] + 0.22
    f["us5y"] = f["us3m"] + 0.30
    f["us7y"] = f["us3m"] + 0.40
    f["us10y"] = f["us3m"] + 0.55
    f["us30y"] = f["us3m"] + 0.80
    f["spread_2s10s"] = f["us10y"] - f["us2y"]
    f["spread_10y3m"] = f["us10y"] - f["us3m"]
    f["us10y_real"] = f["us10y"] - 2.3
    f["us5y_real"] = f["us5y"] - 2.3
    f["breakeven_10y"] = f["us10y"] - f["us10y_real"]
    f["breakeven_5y"] = walk(2.3, 0.005)
    f["breakeven_5y5y"] = walk(2.35, 0.004)
    f["term_premium_10y"] = walk(0.2, 0.006)
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"]
    return f


def _ramp_last(f: pd.DataFrame, col: str, total: float, days: int = 30) -> None:
    """Add a linear ramp of `total` over the final `days` rows of a column (in place)."""
    ramp = np.linspace(0, total, days)
    f.iloc[-days:, f.columns.get_loc(col)] += ramp


# --------------------------------------------------------------------------- #
def test_metadata_and_maps_bilingual_and_complete():
    # the regime play map must cover every taxonomy key, bilingual, valid tickers
    assert set(yc.REGIME_PLAY) == set(_TAXONOMY)
    for k, p in yc.REGIME_PLAY.items():
        assert p["fed_phase_en"] and p["fed_phase_zh"] and p["note_en"] and p["note_zh"], k
        assert p["favored"] and p["pressured"], k
    for etf, m in yc.SECTOR_RATE.items():
        assert m["mech_en"] and m["mech_zh"], etf
        assert m["slope"] in (-1, 0, 1) and m["dur"] in ("long", "short", "neutral"), etf


def test_snapshot_well_formed_and_serializable():
    f = _curve_frame()
    s = yc.snapshot(f)
    assert s is not None
    for key in ("shape", "slopes", "momentum", "regime", "recession", "forwards",
                "signals", "scored_status", "caveats"):
        assert key in s, key
    for fam in ("core_macro", "sector", "stock_factor", "market_tendency"):
        assert fam in s["signals"], fam
    # bilingual everywhere it claims to be
    assert s["scored_status"]["en"] and s["scored_status"]["zh"]
    assert all(c["en"] and c["zh"] for c in s["caveats"])
    # JSON-serializable (no numpy scalars leaking) — the contract is written to disk
    json.dumps(s)


def test_pca_decomposition_variance_and_orientation():
    f = _curve_frame()
    pca = yc.pca_decomposition(f)
    assert pca is not None
    keys = [fct["key"] for fct in pca["factors"]]
    assert keys == ["level", "slope", "curvature"]
    vars_ = [fct["var_explained"] for fct in pca["factors"]]
    # each fraction in [0,1], descending, and the first three span a high share
    assert all(0.0 <= v <= 1.0 for v in vars_)
    assert vars_ == sorted(vars_, reverse=True)
    assert 0.5 < pca["first3_var"] <= 1.0
    # the level factor's loadings should be all the same sign (a parallel factor)
    lev = pca["factors"][0]["loadings"]
    signs = {np.sign(v) for v in lev.values() if v != 0}
    assert len(signs) == 1


def test_slopes_and_momentum_shapes():
    f = _curve_frame()
    slp = yc.slopes(f)
    for k in ("2s10s", "3m10y", "5s30s", "real_5s10s", "tp_adj"):
        assert k in slp, k
        assert slp[k]["label"]["en"] and slp[k]["label"]["zh"]
        assert isinstance(slp[k]["inverted"], bool)
    mom = yc.momentum(f)
    assert mom["window_d"] == yc.MOM_WINDOW
    assert "real10y_speed_bp" in mom
    # the low-frequency trend-spread (Faria-Verona) read is present
    assert "trend_spread" in mom and "trend_spread_dir" in mom


def test_regime_classification_known_moves():
    # bear steepener: long end rises, curve steepens
    f = _curve_frame(seed=1)
    _ramp_last(f, "us10y", +0.5)
    f["spread_2s10s"] = f["us10y"] - f["us2y"]
    f["spread_10y3m"] = f["us10y"] - f["us3m"]
    assert yc.regime(f)["key"] == "bear_steepener"

    # bull flattener: long end falls, curve flattens
    g = _curve_frame(seed=2)
    _ramp_last(g, "us10y", -0.5)
    g["spread_2s10s"] = g["us10y"] - g["us2y"]
    assert yc.regime(g)["key"] == "bull_flattener"

    # bear flattener: front end rises faster than long → curve flattens, long end up
    h = _curve_frame(seed=3)
    _ramp_last(h, "us10y", +0.1)
    _ramp_last(h, "us2y", +0.5)
    h["spread_2s10s"] = h["us10y"] - h["us2y"]
    assert yc.regime(h)["key"] == "bear_flattener"


def test_recession_dashboard_flags():
    # an inverted NTFS + 10y-3m inversion should raise flags & lift the risk band
    f = _curve_frame(seed=5)
    # invert the front: push 1y/2y/3m well above 10y at the tail
    for col, bump in [("us3m", 1.5), ("us1y", 1.4), ("us2y", 1.3)]:
        _ramp_last(f, col, bump, days=60)
    f["spread_10y3m"] = f["us10y"] - f["us3m"]
    f["spread_2s10s"] = f["us10y"] - f["us2y"]
    rec = yc.recession(f)
    assert rec["ntfs"] is not None and rec["ntfs"] < 0          # NTFS inverted
    assert "ntfs" in rec["flags"]
    assert rec["n_flags"] >= 1 and rec["risk"] in ("watch", "elevated", "high")
    assert rec["lead_time_note"]["en"] and rec["lead_time_note"]["zh"]
    # the Wright policy-stance context is present and bilingual when funds is available
    f["fed_funds"] = 5.0
    rec2 = yc.recession(f)
    assert rec2["policy_stance"]["stance"] == "restrictive"
    assert rec2["policy_stance"]["note"]["en"] and rec2["policy_stance"]["note"]["zh"]


def test_forwards_upward_curve():
    f = _curve_frame()
    fwd = yc.forwards(f)
    # on an upward-sloping curve the implied forwards exist and are above the front yield
    assert fwd["f_1y1y"] is not None and fwd["f_5y5y"] is not None
    assert fwd["carry_10y_pct"] is not None
    # roll-down on an upward curve is a positive return contribution
    assert fwd["rolldown_10y_pct"] is not None and fwd["rolldown_10y_pct"] >= 0


def test_sector_and_factor_signal_structure():
    f = _curve_frame()
    s = yc.snapshot(f)
    sec = s["signals"]["sector"]
    assert sec and all(t["etf"] and t["tilt"] in ("tailwind", "headwind", "neutral")
                       and t["basis"] in ("measured", "theory") for t in sec)
    fac = s["signals"]["stock_factor"]
    assert fac["value_vs_growth"] in ("value", "growth", "neutral")
    assert fac["size"] in ("small", "large", "neutral")
    assert fac["duration_factor"] in ("headwind", "tailwind", "neutral")
    mt = s["signals"]["market_tendency"]
    assert mt["drawdown_risk"] in ("calm", "watch", "elevated")


def test_graceful_degradation_missing_nodes():
    # drop the long end + a real leg — the snapshot must still return (degraded), not crash
    f = _curve_frame()
    f = f.drop(columns=["us30y", "us7y", "us5y_real"])
    s = yc.snapshot(f)
    assert s is not None and "slopes" in s
    # missing the whole curve front/back anchor → None, never an exception
    g = f.drop(columns=["us10y"])
    assert yc.snapshot(g) is None
