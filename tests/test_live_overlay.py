"""The fast layer (engine.live_overlay) — the bot/website shared recompute.

Pins the doctrine: the live tick refreshes cheap leaves + raises a divergence
flag vs the nightly ONE-SESSION band (horizon-matched, not the multi-day cone),
the merged read keeps the slow-brain conviction/verdict authoritative, surfaces a
FRESH breach as actionable (not suppressed), and defers to baseline only when the
quote is stale. All pure (no network / disk).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from engine import live_overlay as lo


def _close_series(n: int = 400, start: float = 100.0) -> pd.Series:
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.Series(start + np.linspace(0, 40, n), index=idx)


def _baseline(price: float, asof: str = "2026-06-18", vca: float = 0.30) -> dict:
    return {
        "ticker": "TEST", "asof": asof,
        "tech": {"price": price, "rsi14": 55.0, "macd_pos": True,
                 "above50": True, "above200": True},
        "anticipation": {"vol_cone_ann": vca, "horizons": {"short": {
            "ret_q": {"p5": -8.0, "p25": -2.0, "p50": 0.3, "p75": 2.5, "p95": 8.0},
            "dd_tail": -9.0, "p_up": 0.52, "window_td": 5}}},
        "conviction": {"score": 71, "verdict": "Own it", "size": {"pct": 50}},
    }


# ---- splice / fast leaves -------------------------------------------------

def test_splice_overwrites_today_else_appends():
    today = datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc)
    s = pd.Series([10.0, 11.0], index=pd.to_datetime(["2025-12-31", "2026-01-01"]))
    out = lo.splice(s, 12.5, today)
    assert out.iloc[-1] == 12.5 and len(out) == 2
    s2 = pd.Series([10.0], index=pd.to_datetime(["2025-12-31"]))
    out2 = lo.splice(s2, 9.0, today)
    assert len(out2) == 2 and out2.iloc[-1] == 9.0


def test_live_tech_matches_snapshot_shape():
    close = _close_series()
    snap = lo.live_tech(close, float(close.iloc[-1]) * 1.01)
    assert {"price", "rsi14", "macd_pos", "off_52w_high_pct"} <= set(snap)


# ---- expected-move band (the horizon fix) ---------------------------------

def test_expected_move_1d_from_vol_cone_ann():
    lo_b, hi_b, src = lo.expected_move_1d(_baseline(100.0, vca=0.30))
    expect = round(1.645 * (0.30 / math.sqrt(252) * 100), 2)
    assert src == "vol_cone_ann" and hi_b == expect and lo_b == -expect


def test_expected_move_1d_falls_back_to_scaled_cone():
    b = _baseline(100.0)
    b["anticipation"].pop("vol_cone_ann")
    lo_b, hi_b, src = lo.expected_move_1d(b)
    assert src == "scaled_short_cone"
    assert hi_b == round(8.0 / math.sqrt(5), 2)            # p95 de-annualised to 1 day


# ---- divergence -----------------------------------------------------------

def test_divergence_within_band():
    d = lo.divergence(_baseline(100.0), 101.5)             # +1.5% inside ~±3.1% band
    assert d["flag"] == "within_band" and d["severity"] == "none"
    assert d["chg_pct"] == 1.5 and d["horizon"] == "1d"


def test_divergence_breaches_band_and_flags_extreme():
    up = lo.divergence(_baseline(100.0), 110.0)            # +10% >> band, and > 5d p95
    assert up["flag"] == "band_breach_up" and up["severity"] == "alert"
    assert up["extreme"] is True
    dn = lo.divergence(_baseline(100.0), 91.0)             # -9% << band, and < 5d p5
    assert dn["flag"] == "band_breach_down" and dn["extreme"] is True


def test_divergence_breach_not_extreme_when_inside_5d_cone():
    up = lo.divergence(_baseline(100.0), 104.0)            # +4% > ~3.1% band but < 5d p95 (8)
    assert up["flag"] == "band_breach_up" and up["extreme"] is False


def test_divergence_no_dd_tail_flag_anymore():
    assert "dd_tail_breach" not in lo._SEV               # dropped (wrong statistic)


def test_divergence_threshold_crossing_when_inside_band():
    base = _baseline(100.0)
    base["tech"]["rsi14"] = 65.0
    d = lo.divergence(base, 102.0, live_tech_snap={"rsi14": 72.0, "macd_pos": True})
    assert d["flag"] == "rsi_cross" and "RSI crossed 70" in d["detail"]


# ---- staleness + sessions -------------------------------------------------

def test_staleness_distinguishes_closed_vs_feed_broken():
    old = {"price": 1.0, "delay_min": 45.0, "price_basis": "regular"}
    assert lo.staleness(old, 20, session_open=False)["reason"] == "market closed"
    assert lo.staleness(old, 20, session_open=True)["reason"] == "feed stale during RTH"
    fresh = {"price": 1.0, "delay_min": 2.0, "price_basis": "trade"}
    assert lo.staleness(fresh, 20, session_open=True)["stale"] is False


def test_staleness_prev_basis_never_live():
    q = {"price": 1.0, "delay_min": 0.0, "price_basis": "prev"}
    st = lo.staleness(q, 20, session_open=True)
    assert st["stale"] is True and "prior close" in st["reason"]


def test_region_for():
    assert lo.region_for("600519.SS") == "cn" and lo.region_for("830799.BJ") == "cn"
    assert lo.region_for("0700.HK") == "hk" and lo.region_for("SHOP.TO") == "ca"
    assert lo.region_for("AAPL") == "us" and lo.region_for("^VIX") == "us"


def test_region_for_globe_index_pebbles():
    """W2b: caret-index tickers map to their exchange region (mirrors live.js regionOf)."""
    assert lo.region_for("^GSPC") == "us"
    assert lo.region_for("^GSPTSE") == "ca"
    assert lo.region_for("000001.SS") == "cn"
    assert lo.region_for("^HSI") == "hk"
    assert lo.region_for("^N225") == "jp"
    assert lo.region_for("^KS11") == "kr"
    assert lo.region_for("^TWII") == "tw"
    assert lo.region_for("^FTSE") == "gb"
    assert lo.region_for("^STOXX50E") == "eu"


def test_market_session_new_regions_open_and_closed():
    """W2b: jp/kr/tw/gb/eu sessions report a plausible open/closed state and shape."""
    # Thursday 02:00 UTC = 11:00 Tokyo — JP market open (09:00-11:30 morning leg)
    jp_open = datetime(2026, 6, 18, 2, 0, tzinfo=timezone.utc)
    assert lo.market_session("jp", jp_open)["open"] is True
    # Thursday 03:15 UTC = 12:15 Tokyo — JP lunch closed (11:30-12:30, exclusive end)
    jp_lunch = datetime(2026, 6, 18, 3, 15, tzinfo=timezone.utc)
    assert lo.market_session("jp", jp_lunch)["open"] is False
    # Thursday 04:30 UTC = 13:30 Tokyo — JP afternoon open (12:30-15:00)
    jp_afternoon = datetime(2026, 6, 18, 4, 30, tzinfo=timezone.utc)
    assert lo.market_session("jp", jp_afternoon)["open"] is True

    # Thursday 01:00 UTC = 10:00 Seoul — KR open (09:00-15:30 KST = UTC+9)
    kr_open = datetime(2026, 6, 18, 1, 0, tzinfo=timezone.utc)
    assert lo.market_session("kr", kr_open)["open"] is True
    # Thursday 07:00 UTC = 16:00 Seoul — KR closed
    kr_closed = datetime(2026, 6, 18, 7, 0, tzinfo=timezone.utc)
    assert lo.market_session("kr", kr_closed)["open"] is False

    # Thursday 01:30 UTC = 09:30 Taipei — TW open (09:00-13:30 CST = UTC+8)
    tw_open = datetime(2026, 6, 18, 1, 30, tzinfo=timezone.utc)
    assert lo.market_session("tw", tw_open)["open"] is True
    # Thursday 06:00 UTC = 14:00 Taipei — TW closed (after 13:30)
    tw_closed = datetime(2026, 6, 18, 6, 0, tzinfo=timezone.utc)
    assert lo.market_session("tw", tw_closed)["open"] is False

    # Thursday 09:00 UTC = 10:00 London (BST = UTC+1 in June) — GB open
    gb_open = datetime(2026, 6, 18, 9, 0, tzinfo=timezone.utc)
    assert lo.market_session("gb", gb_open)["open"] is True
    # Thursday 15:45 UTC = 16:45 London — GB closed (after 16:30)
    gb_closed = datetime(2026, 6, 18, 15, 45, tzinfo=timezone.utc)
    assert lo.market_session("gb", gb_closed)["open"] is False

    # Thursday 08:30 UTC = 10:30 Berlin (CEST = UTC+2 in June) — EU open
    eu_open = datetime(2026, 6, 18, 8, 30, tzinfo=timezone.utc)
    assert lo.market_session("eu", eu_open)["open"] is True
    # Thursday 16:00 UTC = 18:00 Berlin — EU closed (after 17:30)
    eu_closed = datetime(2026, 6, 18, 16, 0, tzinfo=timezone.utc)
    assert lo.market_session("eu", eu_closed)["open"] is False

    # All new region records have the standard shape
    for region in ("jp", "kr", "tw", "gb", "eu"):
        sess = lo.market_session(region, jp_open)
        assert set(sess) == {"region", "open", "local_time"}
        assert sess["region"] == region


def test_market_session_open_and_closed():
    open_us = datetime(2026, 6, 18, 15, 0, tzinfo=timezone.utc)   # Thu 10:00 ET
    assert lo.market_session("us", open_us)["open"] is True
    sun = datetime(2026, 6, 21, 15, 0, tzinfo=timezone.utc)       # Sunday
    assert lo.market_session("us", sun)["open"] is False
    # CN lunch break (Thu 12:00 Shanghai == 04:00 UTC) -> closed
    lunch = datetime(2026, 6, 18, 4, 0, tzinfo=timezone.utc)
    assert lo.market_session("cn", lunch)["open"] is False


# ---- per-ticker overlay ---------------------------------------------------

def test_build_ticker_overlay_stale_falls_back_to_baseline():
    base = _baseline(100.0)
    rec = lo.build_ticker_overlay("TEST", base, quote=None, close=_close_series(),
                                  stale_after_min=20)
    assert rec["stale"] is True
    assert rec["tech"] == base["tech"]
    assert rec["price"] == 100.0                          # nightly close, not a stale tick


def test_build_ticker_overlay_rejects_outlier_print():
    base = _baseline(100.0)
    now = datetime(2026, 6, 18, 15, 0, tzinfo=timezone.utc)
    q = {"price": 250.0, "source": "polygon", "delay_min": 1.0,
         "price_basis": "trade", "quote_ts": now.isoformat()}
    rec = lo.build_ticker_overlay("TEST", base, q, _close_series(), 20, now, max_chg_pct=35)
    assert rec["stale"] is True and rec["divergence"]["flag"] == "bad_print"


def test_build_ticker_overlay_fresh_recomputes_with_session_and_region():
    base = _baseline(100.0, asof="2026-06-18")
    now = datetime(2026, 6, 18, 15, 0, tzinfo=timezone.utc)      # Thu RTH
    close = _close_series()
    price = float(close.iloc[-1]) * 1.005
    base["tech"]["price"] = float(close.iloc[-1])
    q = {"price": price, "source": "polygon", "price_basis": "trade",
         "delay_min": 2.0, "quote_ts": now.isoformat()}
    rec = lo.build_ticker_overlay("TEST", base, q, close, 20, now)
    assert rec["stale"] is False and rec["region"] == "us" and rec["session_open"] is True
    assert rec["baseline_stale"] is False and "rsi14" in rec["tech"]


def test_build_ticker_overlay_downgrades_breach_on_stale_baseline():
    # baseline 10 business days old -> a "1-session" move is really multi-day
    now = datetime(2026, 6, 18, 15, 0, tzinfo=timezone.utc)
    base = _baseline(0.0, asof="2026-06-04")
    close = _close_series()
    base["tech"]["price"] = float(close.iloc[-1])
    q = {"price": float(close.iloc[-1]) * 1.10, "source": "polygon",
         "price_basis": "trade", "delay_min": 1.0, "quote_ts": now.isoformat()}
    rec = lo.build_ticker_overlay("TEST", base, q, close, 20, now)
    assert rec["baseline_stale"] is True
    assert rec["divergence"]["severity"] == "info"        # alert downgraded
    assert rec["divergence"]["flag"] == "baseline_stale"


# ---- bot-facing reconciliation -------------------------------------------

def test_merge_baseline_keeps_slow_brain_authoritative_and_surfaces_fresh_alert():
    base = _baseline(100.0)
    overlay = {"ticker": "TEST", "price": 110.0, "chg_pct": 10.0, "stale": False,
               "age_min": 1.0, "session_open": True,
               "divergence": {"flag": "band_breach_up", "severity": "alert", "detail": "x"}}
    m = lo.merge_baseline(base, overlay)
    assert m["conviction"] == 71 and m["verdict"] == "Own it"   # untouched
    assert m["act_on_live"] is True                            # fresh quote -> usable
    assert m["invalidated"] is True                            # fresh alert SURFACES (not suppressed)
    assert m["route_hint"] == "review_new_entry"


def test_merge_baseline_stale_defers_to_baseline():
    base = _baseline(100.0)
    stale = {"ticker": "TEST", "price": 100.0, "stale": True, "age_min": 999,
             "divergence": {"flag": "no_quote", "severity": "info"}}
    m = lo.merge_baseline(base, stale)
    assert m["act_on_live"] is False and m["invalidated"] is False
    assert m["route_hint"] is None
