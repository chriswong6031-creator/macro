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
        assert meta[0] in ("buy", "neutral", "avoid", "tactical")


# -------------------------------------------------- oversold-bounce carve-out ----

def test_oversold_bounce_fires_for_eligible_shallow_turning_dip():
    d = _row(stoch_up=True, rsi=35, stoch=22)
    t3 = _row(stoch_up=True, rsi=38, stoch=22)
    v = ss._verdict(d, t3, above200=False, above50=False,
                    depth200=-0.05, slope200_up=True, osb_eligible=True)
    assert v["state"] == "OVERSOLD_BOUNCE"
    assert ss._STATE_META["OVERSOLD_BOUNCE"][0] == "tactical"


def test_oversold_bounce_requires_caller_eligibility():
    # same dip but caller did not assert eligibility (not a cohort name / put absent)
    d = _row(stoch_up=True); t3 = _row(stoch_up=True)
    v = ss._verdict(d, t3, above200=False, above50=False,
                    depth200=-0.05, slope200_up=True, osb_eligible=False)
    assert v["state"] == "BELOW_TREND"


def test_oversold_bounce_blocked_when_deep_knife():
    d = _row(stoch_up=True); t3 = _row(stoch_up=True)
    v = ss._verdict(d, t3, above200=False, above50=False,
                    depth200=-0.20, slope200_up=True, osb_eligible=True)
    assert v["state"] == "BELOW_TREND"     # >12% below the 200d = knife


def test_oversold_bounce_blocked_when_200d_falling():
    d = _row(stoch_up=True); t3 = _row(stoch_up=True)
    v = ss._verdict(d, t3, above200=False, above50=False,
                    depth200=-0.05, slope200_up=False, osb_eligible=True)
    assert v["state"] == "BELOW_TREND"     # still-collapsing trend = knife


def test_bare_below200_call_is_a_knife_by_default():
    # a bare _verdict() (no osb kwargs) must never emit the tactical state
    d = _row(stoch_up=True); t3 = _row(stoch_up=True)
    assert ss._verdict(d, t3, above200=False, above50=False)["state"] == "BELOW_TREND"


def _defensive_dip() -> pd.Series:
    """A long uptrend (rising 200d) then a shallow multi-week selloff + small uptick
    — a buyable oversold dip ~8% below a still-rising 200d (not a deep knife)."""
    base = np.concatenate([np.full(470, 0.0010), np.full(30, -0.006), np.full(3, 0.004)])
    idx = pd.bdate_range("2015-01-01", periods=len(base))
    return pd.Series(100 * np.cumprod(1 + base), index=idx)


def test_sector_signal_oversold_bounce_cohort_and_put_gate():
    px = _defensive_dip()
    # cohort name, Fed put present -> tactical oversold bounce
    a = ss.sector_signal(px, "Utilities", ticker="XLU", put_absent=False)
    assert a["state"] == "OVERSOLD_BOUNCE" and a["side"] == "tactical"
    assert a["above200"] is False
    # same dip, Fed put ABSENT -> demoted to a knife
    b = ss.sector_signal(px, "Utilities", ticker="XLU", put_absent=True)
    assert b["state"] == "BELOW_TREND"
    # same dip, NON-cohort (cyclical) name -> knife, never the carve-out
    c = ss.sector_signal(px, "Technology", ticker="XLK", put_absent=False)
    assert c["state"] == "BELOW_TREND"


def test_board_tactical_lane_excluded_from_buy_count():
    px = _defensive_dip()
    spy = pd.Series(100 * np.cumprod(np.full(len(px), 1.0004)), index=px.index)
    closes = pd.DataFrame({"XLU": px, "SPY": spy})
    bd = ss.board(closes, {"XLU": "Utilities"}, ["XLU"], spy=closes["SPY"], put_absent=False)
    assert bd["tactical_tickers"] == ["XLU"]
    assert "XLU" not in bd["buy_tickers"] and "XLU" not in bd["avoid_tickers"]
    assert bd["n_buy"] == 0 and bd["n_tactical"] == 1
    # put-absent turns the carve-out off entirely
    bd2 = ss.board(closes, {"XLU": "Utilities"}, ["XLU"], spy=closes["SPY"], put_absent=True)
    assert bd2["tactical_tickers"] == []


def test_calibrate_emits_dual_absolute_and_excess():
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2005-01-01", periods=1500)
    closes = pd.DataFrame({t: pd.Series(50 * np.cumprod(1 + rng.normal(0.0004, 0.012, len(idx))), index=idx)
                           for t in ["XLU", "XLP", "XLK"]})
    spy = pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, len(idx))), index=idx)
    cal = ss.calibrate(closes, ["XLU", "XLP", "XLK"], spy)
    for rec in cal.values():
        assert {"exc63", "hit", "abs63", "abs_hit", "n"} <= set(rec)
        assert isinstance(rec["abs63"], float)


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
        assert {"exc63", "hit", "abs63", "abs_hit", "n"} <= set(rec)
        assert isinstance(rec["exc63"], float)       # JSON-clean (not np.float64)
        assert rec["n"] >= 50


def test_signal_line_describes_fired_crosses():
    s = _trend(600, 0.0008)
    out = ss.sector_signal(s, "X")
    line = ss.signal_line(out)
    assert isinstance(line, str) and len(line) > 0
    line_zh = ss.signal_line(out, zh=True)
    assert isinstance(line_zh, str) and len(line_zh) > 0


def test_weekly_riding_override_only_rescues_extended_on_a_fresh_weekly_cross():
    """An EXTENDED (overbought-still-rising) read is relabeled RIDING ONLY when the weekly just
    crossed up and the weekly isn't itself overbought — so the confluence panel agrees with the
    cycles-ladder RALLY ON instead of crying 'don't chase' (the XLV 2026-06 fix). Keeps the state
    KEY EXTENDED (caller's job) so the measured base rate is unchanged."""
    ov = ss._weekly_riding_override("EXTENDED", weekly_fresh_up=True, weekly_not_hot=True)
    assert ov and ov["label_en"] == "RIDING" and ov["side"] == "neutral"
    # no fresh weekly cross → a genuine extended top stands
    assert ss._weekly_riding_override("EXTENDED", weekly_fresh_up=False, weekly_not_hot=True) is None
    # weekly already overbought → not early, no rescue
    assert ss._weekly_riding_override("EXTENDED", weekly_fresh_up=True, weekly_not_hot=False) is None
    # only EXTENDED is carved out — a confirmed TOPPING/SELL (real down-cross) is never rescued
    for st in ("TOPPING", "SELL", "BUY", "NEUTRAL", "BELOW_TREND"):
        assert ss._weekly_riding_override(st, weekly_fresh_up=True, weekly_not_hot=True) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
