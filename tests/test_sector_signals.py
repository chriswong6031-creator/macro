"""Tests for the Sector Confluence engine (engine/sector_signals).

Two layers: the state machine (`_verdict`) is tested deterministically with
hand-built flag rows; the public surface (`sector_signal`, `board`, `calibrate`)
is tested on synthetic price series for integration, purity, and graceful
degradation on thin data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import sector_signals as ss


# ----------------------------------------------------------- state machine ----

def _row(**kw) -> pd.Series:
    """A flag row with neutral defaults; override the flags you care about."""
    base = {"macd_up": False, "macd_dn": False, "stoch_up": False, "stoch_dn": False,
            "setup_up": False, "setup_dn": False, "stoch_roll": False, "rsi_roll": False,
            "rsi": 50.0, "stoch": 50.0, "hist": 0.0}
    base.update(kw)
    return pd.Series(base)


def test_buy_full_needs_both_timeframes():
    d = _row(macd_up=True, stoch_up=True, rsi=55)
    t3 = _row(macd_up=True, stoch_up=True, rsi=55)
    v = ss._verdict(d, t3, above200=True, above50=True)
    assert v["state"] == "BUY"
    assert v["conviction"] == 3


def test_buy_partial_one_timeframe():
    d = _row(rsi=55)                       # daily quiet
    t3 = _row(macd_up=True, rsi=55)        # only 3D macd crossed up
    v = ss._verdict(d, t3, above200=True, above50=True)
    assert v["state"] == "BUY_PARTIAL"


def test_setup_buy_approaching():
    d = _row(setup_up=True, rsi=52)
    t3 = _row(setup_up=True, rsi=52)
    v = ss._verdict(d, t3, above200=True, above50=True)
    assert v["state"] == "SETUP_BUY"


def test_extended_blocks_buy_even_with_fresh_up():
    # overbought + a stray up-cross must NOT read as a buy — it's late
    d = _row(macd_up=True, stoch_up=True, rsi=78, stoch=95)
    t3 = _row(macd_up=True, rsi=78, stoch=95)
    v = ss._verdict(d, t3, above200=True, above50=True)
    assert v["state"] == "EXTENDED"
    assert ss._STATE_META[v["state"]][0] == "avoid"


def test_topping_extended_and_rolling():
    d = _row(rsi=72, stoch=85, stoch_roll=True)
    t3 = _row(rsi=72, stoch=85, setup_dn=True)
    v = ss._verdict(d, t3, above200=True, above50=True)
    assert v["state"] == "TOPPING"


def test_sell_extended_with_confirmed_downcross():
    d = _row(rsi=71, stoch=82)
    t3 = _row(rsi=71, stoch=82, macd_dn=True, stoch_dn=True)
    v = ss._verdict(d, t3, above200=True, above50=True)
    assert v["state"] == "SELL"


def test_downcross_from_neutral_is_not_a_sell():
    # the validated bounce-trap: a down-cross from a NON-extended state is neutral
    d = _row(rsi=48, stoch=40)
    t3 = _row(rsi=48, stoch=40, macd_dn=True, stoch_dn=True)
    v = ss._verdict(d, t3, above200=True, above50=True)
    assert v["state"] == "NEUTRAL"


def test_below_trend_overrides_everything():
    d = _row(macd_up=True, stoch_up=True, rsi=40)
    t3 = _row(macd_up=True, stoch_up=True, rsi=40)
    v = ss._verdict(d, t3, above200=False, above50=False)
    assert v["state"] == "BELOW_TREND"


def test_buy_gate_blocks_hot_3d_rsi():
    # not "extended" (<70) but 3D RSI above the buy gate (65) -> no fresh buy
    d = _row(macd_up=True, rsi=67)
    t3 = _row(macd_up=True, rsi=67, stoch=60)
    v = ss._verdict(d, t3, above200=True, above50=True)
    assert v["state"] == "NEUTRAL"


def test_every_state_has_display_metadata_and_base_rate():
    for st in ss._STATE_META:
        assert st in ss.STATE_BASE_RATES or st == "NEUTRAL"
    for st, meta in ss._STATE_META.items():
        assert meta[0] in ("buy", "neutral", "avoid")


# -------------------------------------------------------------- price layer ----

def _trend(n: int, drift: float, start: float = 50.0) -> pd.Series:
    idx = pd.bdate_range("2008-01-01", periods=n)
    vals = start * np.cumprod(1 + np.full(n, drift))
    return pd.Series(vals, index=idx)


def test_thin_history_degrades_to_stub():
    s = _trend(100, 0.001)
    out = ss.sector_signal(s, "TEST")
    assert out["ok"] is False
    assert out["state"] == "NEUTRAL"


def test_long_uptrend_is_ok_and_above_trend():
    s = _trend(600, 0.0008)
    out = ss.sector_signal(s, "UP")
    assert out["ok"] is True
    assert out["above200"] is True
    assert out["state"] in ss._STATE_META
    assert out["base_rate"] is not None


def test_downtrend_reads_below_trend():
    # a long rise then a sustained decline that ends well under the 200-day
    up = _trend(400, 0.001)
    down = pd.Series(up.iloc[-1] * np.cumprod(1 + np.full(220, -0.004)),
                     index=pd.bdate_range(up.index[-1] + pd.Timedelta(days=1), periods=220))
    s = pd.concat([up, down])
    out = ss.sector_signal(s, "DN")
    assert out["above200"] is False
    assert out["state"] == "BELOW_TREND"
    assert out["side"] == "avoid"


def test_sector_signal_is_pure():
    s = _trend(500, 0.0007)
    snapshot = s.copy()
    a = ss.sector_signal(s, "X")
    b = ss.sector_signal(s, "X")
    pd.testing.assert_series_equal(s, snapshot)      # input untouched
    assert a["state"] == b["state"] and a["conviction"] == b["conviction"]


def test_board_sorts_and_summarises():
    sectors = ["AAA", "BBB", "CCC"]
    closes = pd.DataFrame({
        "AAA": _trend(600, 0.0009),                  # uptrend
        "BBB": _trend(600, -0.0005, start=120),      # downtrend -> below trend
        "CCC": _trend(600, 0.0006),
        "SPY": _trend(600, 0.0005),
    })
    b = ss.board(closes, {t: t for t in sectors}, sectors, spy=closes["SPY"])
    states = [r["state"] for r in b["sectors"]]
    prios = [r["priority"] for r in b["sectors"]]
    assert prios == sorted(prios)                    # actionable-first ordering
    assert b["n_buy"] + b["n_avoid"] <= len(b["sectors"])
    assert "BBB" in b["avoid_tickers"]               # downtrend is an avoid


def test_board_skips_missing_columns():
    closes = pd.DataFrame({"AAA": _trend(600, 0.0008), "SPY": _trend(600, 0.0005)})
    b = ss.board(closes, {"AAA": "AAA", "ZZZ": "ZZZ"}, ["AAA", "ZZZ"], spy=closes["SPY"])
    assert [r["ticker"] for r in b["sectors"]] == ["AAA"]


def test_put_absent_hardens_below_trend_caveat():
    up = _trend(400, 0.001)
    down = pd.Series(up.iloc[-1] * np.cumprod(1 + np.full(220, -0.004)),
                     index=pd.bdate_range(up.index[-1] + pd.Timedelta(days=1), periods=220))
    closes = pd.DataFrame({"AAA": pd.concat([up, down])})
    closes["SPY"] = _trend(620, 0.0003)
    b = ss.board(closes, {"AAA": "AAA"}, ["AAA"], spy=closes["SPY"], put_absent=True)
    row = b["sectors"][0]
    assert row["state"] == "BELOW_TREND"
    assert "put" in row["action"].lower()


def test_calibrate_returns_measured_rates():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2005-01-01", periods=1500)
    closes = {}
    for t in ["AAA", "BBB", "CCC"]:
        steps = rng.normal(0.0004, 0.012, len(idx))
        closes[t] = pd.Series(50 * np.cumprod(1 + steps), index=idx)
    spy = pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, len(idx))), index=idx)
    closes_df = pd.DataFrame(closes)
    cal = ss.calibrate(closes_df, ["AAA", "BBB", "CCC"], spy)
    assert isinstance(cal, dict)
    for st, rec in cal.items():
        assert set(rec) == {"exc63", "hit", "n"}
        assert isinstance(rec["exc63"], float)       # JSON-clean (not np.float64)
        assert rec["n"] >= 50


def test_signal_line_describes_fired_crosses():
    s = _trend(600, 0.0008)
    out = ss.sector_signal(s, "X")
    line = ss.signal_line(out)
    assert isinstance(line, str) and len(line) > 0
    line_zh = ss.signal_line(out, zh=True)
    assert isinstance(line_zh, str) and len(line_zh) > 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
