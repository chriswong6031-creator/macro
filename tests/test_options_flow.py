"""engine/options_flow.py — tick-rule signing, flow summary, MEASURED dealer positioning."""
import numpy as np
import pandas as pd
import pytest

from engine import options_flow as of


def _minute(rows):
    """rows: list of (ticker, underlying, expiry, is_call, strike, ts, close, vol)."""
    return pd.DataFrame(rows, columns=["ticker", "underlying", "expiry", "is_call",
                                       "strike", "window_start", "close", "volume"])


def test_sign_volume_tick_rule():
    # one call: closes 1.0,1.1,1.05,1.2 -> ticks 0,+1,-1,+1 ; signed = 0+20-30+40 = 30
    exp = pd.Timestamp("2026-07-17")
    mdf = _minute([
        ("O:X260717C00100000", "X", exp, True, 100.0, 1, 1.00, 10),
        ("O:X260717C00100000", "X", exp, True, 100.0, 2, 1.10, 20),
        ("O:X260717C00100000", "X", exp, True, 100.0, 3, 1.05, 30),
        ("O:X260717C00100000", "X", exp, True, 100.0, 4, 1.20, 40),
    ])
    agg = of.sign_volume(mdf)
    assert len(agg) == 1
    r = agg.iloc[0]
    assert r["vol"] == 100
    assert r["signed_vol"] == pytest.approx(30.0)
    assert r["premium"] == pytest.approx((1.0*10+1.1*20+1.05*30+1.2*40)*100)


def test_flow_summary_metrics():
    exp = pd.Timestamp("2026-06-18")
    asof = pd.Timestamp("2026-06-18")
    mdf = _minute([
        ("O:X260618C00100000", "X", exp, True, 100.0, 1, 1.0, 10),
        ("O:X260618C00100000", "X", exp, True, 100.0, 2, 1.5, 50),   # buy
        ("O:X260618P00090000", "X", exp, False, 90.0, 1, 2.0, 10),
        ("O:X260618P00090000", "X", exp, False, 90.0, 2, 1.0, 80),   # sell
    ])
    s = of.flow_summary(of.sign_volume(mdf), asof, spot=100.0, minute_df=mdf)
    assert s["available"]
    assert s["call_vol"] == 60 and s["put_vol"] == 90
    assert s["zerodte_share"] == 1.0          # all expire on asof
    assert s["pc_ratio"] == pytest.approx(90/60, abs=0.01)
    assert isinstance(s["large_prints"], list) and s["large_prints"]


def test_measured_dealer_sign_and_divergence():
    # customers BUY a call -> dealers SHORT it -> dealer gamma flow NEGATIVE; and the buy
    # DIVERGES from the long-call assumption (which says dealers are long calls).
    agg = pd.DataFrame([{"ticker": "O:X260717C00100000", "underlying": "X",
                         "expiry": pd.Timestamp("2026-07-17"), "is_call": True, "strike": 100.0,
                         "vol": 100000, "signed_vol": 80000.0, "premium": 1e8, "close": 1.2}])
    greeks = pd.DataFrame([{"ticker": "O:X260717C00100000", "gamma": 0.05, "delta": 0.5, "oi": 500000}])
    d = of.measured_dealer(agg, greeks, spot=100.0)
    assert d["gamma_flow_bn"] is not None and d["gamma_flow_bn"] < 0   # dealers got shorter gamma
    assert "SHORT gamma" in d["gamma_flow_dir"]
    assert d["assumed_gex_bn"] > 0                                     # long-call assumption = +GEX
    assert d["divergence"] and d["divergence"][0]["flow"].endswith("bought")


def test_vol_oi_newpos():
    agg = pd.DataFrame([
        {"ticker": "A", "underlying": "X", "expiry": pd.Timestamp("2026-07-17"), "is_call": True,
         "strike": 100.0, "vol": 1000, "signed_vol": 900.0, "premium": 5e5, "close": 1.0},
        {"ticker": "B", "underlying": "X", "expiry": pd.Timestamp("2026-07-17"), "is_call": False,
         "strike": 90.0, "vol": 50, "signed_vol": -40.0, "premium": 1e4, "close": 0.5},
    ])
    greeks = pd.DataFrame([{"ticker": "A", "gamma": 0.0, "delta": 0.0, "oi": 100},   # vol 1000 > OI 100 = fresh
                           {"ticker": "B", "gamma": 0.0, "delta": 0.0, "oi": 5000}]) # vol 50 < OI = not fresh
    r = of.vol_oi_newpos(agg, greeks)
    assert r["fresh_contracts"] == 1
    assert r["top"][0]["dir"] == "buy" and r["top"][0]["x_oi"] == 10.0


def test_build_flow_verdict_and_safety():
    assert of.build_flow("X", pd.DataFrame(), None, 100.0, pd.Timestamp("2026-06-18"))["available"] is False
    exp = pd.Timestamp("2026-06-18")
    mdf = _minute([
        ("O:X260618C00100000", "X", exp, True, 100.0, 1, 1.0, 10),
        ("O:X260618C00100000", "X", exp, True, 100.0, 2, 2.0, 500),  # big call buying
    ])
    p = of.build_flow("X", mdf, None, 100.0, exp)
    assert p["available"] and p["verdict"]["en"]
    assert p["dealer"] == {}          # no greeks -> dealer read absent, but flow still built
