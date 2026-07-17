"""Advanced theme textures (engine.basket_score) — display-only, honest.

Verify bull-market age, overbought, clean-entry and roll-over read the level/texture inputs
correctly, every texture carries directional:False, and market_concentration degrades to {}
without the breadth file. Pure functions on synthetic series; no network.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import basket_score as bs


def _ramp(n=300, slope=0.0015, start=1.0):
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(start * np.cumprod(1 + np.full(n, slope)), index=idx)


def test_bull_age_uptrend_vs_downtrend():
    up = bs.bull_age(_ramp(slope=0.002))
    assert up["in_bull"] is True and up["days"] > 0
    assert up["stage"] in ("young", "building", "mature", "aging")
    assert up["directional"] is False
    dn = bs.bull_age(_ramp(slope=-0.002))
    assert dn["in_bull"] is False and dn["stage"] == "downtrend"


def test_bull_age_needs_history():
    assert bs.bull_age(_ramp(n=40)) is None


def test_overbought_band_scales_with_rsi_and_rs():
    hot = bs.overbought(_ramp(slope=0.004), 0.95, None)
    cool = bs.overbought(_ramp(slope=0.0001), 0.4, None)
    assert hot["value"] >= cool["value"]
    assert hot["band"] in ("overbought", "extreme", "elevated")
    assert hot["directional"] is False


def test_clean_entry_flag_requires_not_extended():
    lvl = _ramp(slope=0.0015)
    # accelerating, not extended, RSI room, broad → flag on
    on = bs.clean_entry(lvl, {"accel_z": 0.8, "rs_pctile": 0.5}, {"pct50": 0.6}, 55)
    assert on["flag"] is True and on["quality"] >= 0.6
    # same but extended (rs_pctile high) → flag off
    off = bs.clean_entry(lvl, {"accel_z": 0.8, "rs_pctile": 0.95}, {"pct50": 0.6}, 55)
    assert off["flag"] is False
    assert on["directional"] is False


def test_clean_entry_vetoed_on_breaking_backdrop():
    # REGRESSION (cn_banks etc.): accel + not-extended + RSI room alone must NOT advertise a
    # "clean entry" when the tape is BREAKING — collapsed breadth, net new lows, or hard decel.
    lvl = _ramp(slope=0.0015)
    fp = {"accel_z": 0.8, "rs_pctile": 0.3}        # accelerating + not extended
    # collapsed breadth (pct50 < 0.4) → no clean entry
    assert bs.clean_entry(lvl, fp, {"pct50": 0.0, "nh": 0, "nl": 7}, 55)["flag"] is False
    # net new lows → no clean entry even with ok pct50
    assert bs.clean_entry(lvl, fp, {"pct50": 0.55, "nh": 0, "nl": 3}, 55)["flag"] is False
    # hard down-acceleration → no clean entry
    assert bs.clean_entry(lvl, {"accel_z": -0.8, "rs_pctile": 0.3},
                          {"pct50": 0.6, "nh": 2, "nl": 0}, 55)["flag"] is False
    # healthy, broad, turning up → still a clean entry (cn_brokers-style early entry)
    assert bs.clean_entry(lvl, fp, {"pct50": 0.6, "nh": 3, "nl": 0}, 55)["flag"] is True


def test_rollover_risk_rises_with_extension_and_decel():
    lvl = _ramp(slope=0.0015)
    hi = bs.rollover_risk(lvl, {"rs_pctile": 0.92, "accel_z": -0.6},
                          {"accel_z": 0.4}, {"pct50": 0.4, "nh": 0, "nl": 5},
                          {"5d": {"rel": -0.03}})
    lo = bs.rollover_risk(lvl, {"rs_pctile": 0.5, "accel_z": 0.5},
                          {"accel_z": 0.3}, {"pct50": 0.7, "nh": 4, "nl": 0},
                          {"5d": {"rel": 0.02}})
    assert hi["risk"] > lo["risk"]
    assert hi["band"] in ("elevated", "high")
    assert lo["band"] == "low"
    assert hi["directional"] is False


def test_theme_textures_bundles_all_four():
    tx = bs.theme_textures(_ramp(), {"rs_pctile": 0.6, "accel_z": 0.4},
                           {"accel_z": 0.3}, None, {"pct50": 0.55, "nh": 2, "nl": 1},
                           {"5d": {"rel": 0.01}})
    assert set(tx) == {"bull_age", "overbought", "clean_entry", "rollover_risk"}


def test_act_now_stocks_gated_by_theme_health():
    members = [
        {"symbol": "AAA", "conviction": {"score": 72, "verdict": "Buy — pullback", "cycle_blocked": False, "entry_pct": 0.7}},
        {"symbol": "BBB", "conviction": {"score": 80, "verdict": "Add — strong", "cycle_blocked": False, "entry_pct": 0.6}},
        {"symbol": "CCC", "conviction": {"score": 30, "verdict": "Avoid — downtrend", "cycle_blocked": True, "entry_pct": 0.2}},
        {"symbol": "DDD", "conviction": {"score": 90, "verdict": "Strong name, wrong tape", "cycle_blocked": True, "entry_pct": 0.1}},
    ]
    # healthy theme → returns the buys (AAA/BBB), excludes avoid + cycle-blocked
    good = bs.act_now_stocks(members, {"label": "emerging", "reco": "enter",
                                       "textures": {"bull_age": {"in_bull": True}}})
    assert good["status"] == "ok"
    syms = [x["symbol"] for x in good["buys"]]
    assert "AAA" in syms and "BBB" in syms and "CCC" not in syms and "DDD" not in syms
    # out-of-favour theme → NOTHING recommended, with a reason
    for bad in ({"label": "deteriorating", "reco": "avoid", "textures": {"bull_age": {"in_bull": True}}},
                {"label": "fading", "reco": "trim", "textures": {"bull_age": {"in_bull": True}}},
                {"label": "neutral", "reco": "hold", "textures": {"bull_age": {"in_bull": False}}}):
        r = bs.act_now_stocks(members, bad)
        assert r["status"] == "theme_out_of_favour" and r["buys"] == [] and r["note_en"]


def test_act_now_constructive_label_below_200d_not_vetoed():
    # REGRESSION (cn_brokers): an EMERGING / DOMINANT theme freshly turning up off a base is
    # still below its slow 200d SMA (in_bull False). The engine's own constructive label must
    # NOT be overridden into a self-contradicting "out of favour (emerging)" — it proceeds to
    # per-member gating and surfaces members with an open entry.
    members = [
        {"symbol": "AAA", "conviction": {"score": 83, "verdict": "Neutral", "cycle_blocked": False,
                                         "entry_pct": 0.5, "entry": {"status": "buy_now", "act_level": 3}}},
    ]
    for lbl in ("emerging", "dominant"):
        r = bs.act_now_stocks(members, {"label": lbl, "reco": "hold",
                                        "textures": {"bull_age": {"in_bull": False}}})
        assert r["status"] == "ok", lbl
        assert [x["symbol"] for x in r["buys"]] == ["AAA"], lbl
    # a NEUTRAL theme below its 200d still reads as a downtrend, and the reason never echoes a
    # constructive lifecycle label (no more "out of favour (emerging)").
    nr = bs.act_now_stocks(members, {"label": "neutral", "reco": "hold",
                                     "textures": {"bull_age": {"in_bull": False}}})
    assert nr["status"] == "theme_out_of_favour"
    assert "downtrend" in nr["note_en"] and "emerging" not in nr["note_en"]


def test_act_now_no_clean_entries():
    # healthy theme but no member is a buy → honest 'no clean entry', not a forced pick
    members = [{"symbol": "X", "conviction": {"score": 40, "verdict": "Neutral — no edge", "cycle_blocked": False, "entry_pct": 0.5}}]
    r = bs.act_now_stocks(members, {"label": "dominant", "reco": "hold", "textures": {"bull_age": {"in_bull": True}}})
    assert r["status"] == "no_clean_entries" and r["buys"] == []
    assert r["uncovered"] == []


def test_act_now_uncovered_disclosed_on_every_path():
    # REGRESSION (hk_banks audit 2026-07-16): members without a conviction read (no stockdata
    # record, or a thin record without a score) were silently dropped from the ranking. Every
    # payload now carries the `uncovered` list so the page prints the gap explicitly.
    members = [
        {"symbol": "AAA", "conviction": {"score": 83, "verdict": "Buy", "cycle_blocked": False,
                                         "entry_pct": 0.7, "entry": {"status": "buy_now", "act_level": 3}}},
        {"symbol": "BBB", "conviction": None},                                    # no record at all
        {"symbol": "CCC", "conviction": {"score": None, "signal": {"tier": "T2"}}},  # thin: no score
    ]
    ok = bs.act_now_stocks(members, {"label": "dominant", "reco": "hold",
                                     "textures": {"bull_age": {"in_bull": True}}})
    assert ok["status"] == "ok" and ok["uncovered"] == ["BBB", "CCC"]
    out = bs.act_now_stocks(members, {"label": "fading", "reco": "avoid",
                                      "textures": {"bull_age": {"in_bull": True}}})
    assert out["status"] == "theme_out_of_favour" and out["uncovered"] == ["BBB", "CCC"]
    # an ALL-uncovered basket (hk_industrials was 9/9) reads as a coverage gap, not a verdict
    bare = bs.act_now_stocks([{"symbol": "ZZZ", "conviction": None}],
                             {"label": "dominant", "reco": "hold",
                              "textures": {"bull_age": {"in_bull": True}}})
    assert bare["status"] == "no_clean_entries" and bare["uncovered"] == ["ZZZ"]


def test_market_concentration_graceful(monkeypatch, tmp_path):
    # point data_dir at an empty tmp → no breadth file → {} (never raises)
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    assert bs.market_concentration() == {}
