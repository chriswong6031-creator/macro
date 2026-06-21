"""Tests for the strategy signal library (engine/strategy_signals.py).

Invariants under test: indicators are bounded/causal, the entry composite is oriented
HIGHER = more oversold, the exit composite HIGHER = more extended, positions are
long/flat in [0,1], and nothing peeks at the future (a value at bar t is unchanged
when later bars are appended)."""
import numpy as np
import pandas as pd
import pytest

from engine import strategy_signals as SS


def _series(vals, start="2015-01-01"):
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series(np.asarray(vals, float), index=idx)


def _frame(close):
    return pd.DataFrame({"close": close, "high": close * 1.01, "low": close * 0.99})


def _uptrend_with_dip(n=400, dip_at=-1):
    # a steady uptrend, then a sharp dip on the last bar
    base = np.linspace(100, 200, n)
    base[dip_at] *= 0.90
    return _series(base)


# --- indicators -------------------------------------------------------------
def test_rsi_bounds_and_oversold():
    up = _series(np.linspace(100, 200, 300))
    r = SS.wilder_rsi(up, 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()
    assert r.iloc[-1] > 55                      # a clean uptrend is not oversold
    # a long decline drives RSI low
    dn = _series(np.linspace(200, 100, 300))
    assert SS.wilder_rsi(dn, 14).dropna().iloc[-1] < 45


def test_bollinger_pctb_orientation():
    c = _uptrend_with_dip()
    pb = SS.bollinger_pctb(c, 20).dropna()
    assert pb.iloc[-1] < pb.median()            # the dip bar sits low in the band


def test_positions_are_long_flat():
    c = _uptrend_with_dip()
    df = _frame(c)
    for s in SS.REGISTRY:
        sig, pos = s.signal(df)
        if pos is None:
            continue
        p = pos.dropna()
        assert ((p >= 0) & (p <= 1)).all(), f"{s.key} position out of [0,1]"


# --- composites -------------------------------------------------------------
def test_entry_score_high_on_dip():
    c = _uptrend_with_dip()
    df = _frame(c)
    score = SS.entry_timing_score(df, gate_uptrend=True).dropna()
    assert score.iloc[-1] > 60                  # oversold-in-uptrend = a good entry


def test_exit_score_high_when_extended():
    # a parabolic blow-off should read as extended
    c = _series(np.concatenate([np.linspace(100, 150, 300), np.linspace(150, 240, 60)]))
    df = _frame(c)
    xs = SS.exit_extension_score(df).dropna()
    assert xs.iloc[-1] > 70


def test_entry_gate_halves_in_downtrend():
    dn = _series(np.linspace(200, 120, 400))
    df = _frame(dn)
    gated = SS.entry_timing_score(df, gate_uptrend=True).dropna()
    ungated = SS.entry_timing_score(df, gate_uptrend=False).dropna()
    # below the 200dma the score is damped
    assert gated.iloc[-1] <= ungated.iloc[-1]


# --- causality (no look-ahead) ---------------------------------------------
def test_entry_z_is_causal():
    c = _uptrend_with_dip(n=400)
    z1 = SS.entry_timing_z(_frame(c))
    # append future bars; the value AT the old last bar must not change
    fut = _series(np.linspace(c.iloc[-1], c.iloc[-1] * 1.3, 50),
                  start=(c.index[-1] + pd.tseries.offsets.BDay(1)).strftime("%Y-%m-%d"))
    c2 = pd.concat([c, fut])
    z2 = SS.entry_timing_z(_frame(c2))
    assert z2.loc[c.index[-1]] == pytest.approx(z1.loc[c.index[-1]], rel=1e-9, abs=1e-9)


def test_hold_for_expires():
    trig = pd.Series([False] * 20, index=pd.bdate_range("2020-01-01", periods=20))
    trig.iloc[5] = True
    pos = SS.hold_for(trig, 3)
    assert pos.iloc[5] == 1 and pos.iloc[6] == 1 and pos.iloc[7] == 1
    assert pos.iloc[8] == 0                      # expired after h bars
