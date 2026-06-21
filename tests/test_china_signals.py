"""Tests for engine/china_signals.py — A-share signals + the inverted QVIX vol-regime confirmer."""
import numpy as np
import pandas as pd

from engine import china_signals as cs


def _idx(n):
    return pd.bdate_range("2019-01-01", periods=n)


def test_board_type_limits():
    assert cs.board_type("688981.SS") == ("star", 20.0)
    assert cs.board_type("300750.SZ") == ("chinext", 20.0)
    assert cs.board_type("600519.SS") == ("main", 10.0)
    assert cs.board_type("000001.SZ") == ("main", 10.0)


def test_ashare_tech_reversal_setup_in_uptrend():
    # a strong, long uptrend then a SHARP oversold dip -> reversal setup True (stays above MA120,
    # RSI-10 deeply oversold, price below MA20)
    base = 100 + np.cumsum(np.full(300, 0.7))            # steady strong uptrend -> ~310
    dip = base[-1] * (1 - np.linspace(0, 0.08, 5))       # a fast 8% slide over 5 days
    c = pd.Series(np.concatenate([base, dip]), index=_idx(305))
    out = cs.ashare_tech(c, "600519.SS")
    assert out["above_ma120"] is True
    assert out["rsi10"] is not None and out["rsi10"] < 30
    assert out["reversal_setup"] is True
    assert out["dist_ma20_z"] is not None and out["dist_ma20_z"] < 0


def test_ashare_tech_limit_flag():
    c = pd.Series(np.full(140, 100.0), index=_idx(140))
    c.iloc[-1] = 100.0 * 1.099                  # a +9.9% day = up-limit on the main board
    out = cs.ashare_tech(c, "600000.SS")
    assert out["limit_flag"] == "up"


def test_ashare_tech_too_short_graceful():
    c = pd.Series(np.full(50, 10.0), index=_idx(50))
    out = cs.ashare_tech(c, "600000.SS")
    assert out["rsi10"] is None and out["reversal_setup"] is None


def test_qvix_regime_inverted_uses_z_not_level():
    # a panic SPIKE: long calm then a sharp jump -> high qvix_z -> caution/stress, regardless of level
    calm = 20 + np.random.default_rng(2).standard_normal(120) * 1.0
    spike = np.linspace(calm[-1], calm[-1] + 12, 8)
    q = pd.Series(np.concatenate([calm, spike]), index=_idx(128))
    out = cs.qvix_regime(q)
    assert out["regime"] == "panic" and out["verdict"] == "caution" and out["stress"] >= 0.5
    # a HIGH but STABLE level (high absolute, ~0 z) must NOT read panic (the inversion vs US VIX)
    qhigh = pd.Series(35 + np.random.default_rng(3).standard_normal(128) * 0.5, index=_idx(128))
    out2 = cs.qvix_regime(qhigh)
    assert out2["regime"] in ("normal", "suppressed") and out2["verdict"] != "caution"


def test_qvix_regime_suppressed_confirms():
    base = 25 + np.random.default_rng(4).standard_normal(120) * 1.0
    drop = np.linspace(base[-1], base[-1] - 6, 8)      # vol falling -> suppressed
    q = pd.Series(np.concatenate([base, drop]), index=_idx(128))
    out = cs.qvix_regime(q)
    assert out["regime"] == "suppressed" and out["verdict"] == "confirm"


def test_margin_crowding():
    assert cs.margin_crowding(25.0)["crowded"] is True          # +25% balance build = crowded
    assert cs.margin_crowding(2.0)["band"] == "normal"
    assert cs.margin_crowding(None, 11.0)["crowded"] is True     # high financing/mcap = crowded
    assert cs.margin_crowding(None, None) is None
