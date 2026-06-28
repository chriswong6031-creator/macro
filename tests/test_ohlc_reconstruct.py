"""Conservative OHLC reconstruction (engine/ohlc_reconstruct.py) + its wiring.

Pins the load-bearing invariants for imputing a high/low band from a CLOSE-ONLY
series (Tencent / A-shares / search & breadth caches), per the charter task:

  * the candle always CONTAINS the open->close body (never renders inverted);
  * it never UNDERSTATES the realised close-to-close move (range >= |open-close|);
  * a flat series still gets a visible floor band (>= FLOOR_PCT of price);
  * close-only vs real-OHLC detection is correct (incl. high==low==close fakes);
  * signal_quality's high/low fallback is EXACTLY the old close-only behaviour;
  * build_chart_data's recon emit is a 6-tuple candle record (o:1 + recon:1).
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from engine import ohlc_reconstruct as orc
from engine.signal_quality import signal_frame, _swing_highs, analyze


def _close(vals, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(vals), freq="B", name="Date")
    return pd.Series([float(v) for v in vals], index=idx)


def test_contains_body_and_high_ge_low():
    np.random.seed(0)
    close = _close(100 + np.cumsum(np.random.randn(400)))
    rec = orc.reconstruct_ohlc(close)
    assert rec[["open", "high", "low", "close"]].notna().all().all()        # no NaN
    body_hi = rec[["open", "close"]].max(axis=1)
    body_lo = rec[["open", "close"]].min(axis=1)
    assert (rec["high"] >= body_hi - 1e-9).all()                            # contains body
    assert (rec["low"] <= body_lo + 1e-9).all()
    assert (rec["high"] >= rec["low"]).all()


def test_open_is_prior_close():
    close = _close([10, 11, 12, 13])
    rec = orc.reconstruct_ohlc(close)
    assert rec["open"].iloc[0] == rec["close"].iloc[0]                      # first opens at itself
    for i in range(1, len(rec)):
        assert rec["open"].iloc[i] == rec["close"].iloc[i - 1]


def test_never_understates_close_to_close_move():
    np.random.seed(1)
    close = _close(50 + np.cumsum(np.random.randn(300)))
    rec = orc.reconstruct_ohlc(close)
    rng = rec["high"] - rec["low"]
    move = (rec["close"] - rec["open"]).abs()
    assert (rng >= move - 1e-9).all()      # range can never be tighter than the body


def test_flat_series_gets_floor_band():
    close = _close([100.0] * 60)
    rec = orc.reconstruct_ohlc(close)
    rng = (rec["high"] - rec["low"]).iloc[-1]
    assert rng >= orc.FLOOR_PCT * 100.0 - 1e-9          # >= 0.8% of price, not zero-height


def test_atr_proxy_scales_with_volatility_and_no_nan():
    quiet = _close(100 + np.cumsum(np.full(200, 0.01)))
    loud = _close(100 + np.cumsum(np.tile([5.0, -5.0], 100)))
    aq, al = orc.atr_proxy(quiet), orc.atr_proxy(loud)
    assert aq.notna().all() and al.notna().all()
    assert (aq > 0).all() and (al > 0).all()
    assert al.iloc[-1] > aq.iloc[-1]


def test_real_ohlc_detection():
    idx = pd.date_range("2026-01-01", periods=5, freq="B")
    real = pd.DataFrame({"close": [10, 11, 12, 11, 13], "high": [11, 12, 13, 12, 14],
                         "low": [9, 10, 11, 10, 12]}, index=idx)
    closeonly = pd.DataFrame({"close": [10, 11, 12, 11, 13]}, index=idx)
    fake = pd.DataFrame({"close": [10, 11, 12, 11, 13], "high": [10, 11, 12, 11, 13],
                         "low": [10, 11, 12, 11, 13]}, index=idx)   # h==l==c padding
    assert orc.has_real_ohlc(real) is True
    assert orc.is_close_only(closeonly) is True
    assert orc.has_real_ohlc(fake) is False                         # echo of close, not real


def test_body_aware_puts_close_near_the_extreme():
    rec_up = orc.reconstruct_ohlc(_close(range(100, 130)), mode="body_aware")   # steady up
    r = rec_up.iloc[-1]
    assert (r["high"] - r["close"]) <= (r["close"] - r["low"]) + 1e-9            # close near high
    rec_dn = orc.reconstruct_ohlc(_close(range(130, 100, -1)), mode="body_aware")  # steady down
    r = rec_dn.iloc[-1]
    assert (r["close"] - r["low"]) <= (r["high"] - r["close"]) + 1e-9            # close near low


def test_signal_frame_fallback_equals_close_only():
    np.random.seed(2)
    close = _close(100 + np.cumsum(np.random.randn(500)))
    sf = signal_frame(close)                          # no high/low => fallback
    assert (sf["high"] == sf["close"]).all()          # fallback is exact
    assert (sf["low"] == sf["close"]).all()
    # swing highs on the fallback 'high' == swing highs on 'close' (unchanged logic)
    assert _swing_highs(sf["high"]) == _swing_highs(sf["close"])


def test_signal_frame_with_highlow_brackets_close():
    np.random.seed(3)
    close = _close(100 + np.cumsum(np.random.randn(500)))
    rec = orc.reconstruct_ohlc(close)
    sf = signal_frame(close, rec["high"], rec["low"])
    assert (sf["high"] >= sf["close"] - 1e-9).all()   # 3D high never below its close
    assert (sf["low"] <= sf["close"] + 1e-9).all()


def test_bars_recon_is_six_tuple_candle():
    from scripts import build_chart_data as bcd
    close = _close(100 + np.cumsum(np.random.RandomState(4).randn(60)))
    bars = bcd._bars_recon(close)
    assert bars and all(len(b) == 6 for b in bars)     # [date, o, h, l, c, v]
    for _d, o, h, lo, c, _v in bars:
        assert h >= max(o, c) - 1e-9 and lo <= min(o, c) + 1e-9


def test_bars_recon_survives_duplicate_index():
    from scripts import build_chart_data as bcd
    idx = pd.DatetimeIndex(["2026-01-01", "2026-01-01", "2026-01-02"], name="Date")
    close = pd.Series([10.0, 10.5, 11.0], index=idx)
    vol = pd.Series([1, 2, 3], index=idx)
    bars = bcd._bars_recon(close, vol)                 # must not raise on dup date
    assert bars and all(len(b) == 6 for b in bars)


def test_constants_are_the_documented_priors():
    # the load-bearing charter constants — a silent change must fail CI loudly
    assert orc.RANGE_MULT == 2.0
    assert orc.ATR_LEN == 14
    assert orc.FLOOR_PCT == 0.008
    assert orc.BODY_SKEW == 0.70


def test_symmetric_band_width_equals_range_mult_times_mean_move():
    # a constant-step ramp: |Δclose| == step, so once the Wilder RMA warms,
    # high-low must equal RANGE_MULT * step (the textbook high=close±ATR/2).
    step = 2.0
    rec = orc.reconstruct_ohlc(_close(np.arange(100, 100 + 200 * step, step)))
    rng = (rec["high"] - rec["low"]).iloc[-1]
    assert abs(rng - orc.RANGE_MULT * step) < 0.02 * step


def test_reconstruction_is_causal_no_repaint():
    # reconstructing on a prefix must equal reconstructing on the full series and
    # truncating — i.e. no future bar can repaint an earlier candle.
    np.random.seed(7)
    close = _close(100 + np.cumsum(np.random.randn(400)))
    full = orc.reconstruct_ohlc(close)
    prefix = orc.reconstruct_ohlc(close.iloc[:200])
    for col in ("open", "high", "low", "close"):
        assert np.allclose(prefix[col].to_numpy(), full[col].iloc[:200].to_numpy())


# Golden snapshot of the CLOSE-ONLY analyze() markers on a fixed pseudo-random series.
# This pins the validated buy-filter's close-only output bit-for-bit: any future edit
# that perturbs the close-only path (the safety contract that lets us feed high/low
# without re-validating it) flips the fingerprint and fails loudly.
_GOLD_FP, _GOLD_N = "f88f005c2386793a", 15


def _gold_close():
    idx = pd.date_range("2018-01-01", periods=800, freq="B", name="Date")
    rng = np.random.RandomState(42)
    return pd.Series(100 * np.exp(np.cumsum(rng.randn(800) * 0.015)), index=idx)


def test_close_only_markers_match_golden():
    res = analyze("GOLD", _gold_close())                 # no high/low => fallback path
    ms = [(m["date"], m["type"], m.get("quality")) for m in res["markers"]]
    fp = hashlib.sha256(json.dumps(ms, sort_keys=True).encode()).hexdigest()[:16]
    assert len(ms) == _GOLD_N
    assert fp == _GOLD_FP
