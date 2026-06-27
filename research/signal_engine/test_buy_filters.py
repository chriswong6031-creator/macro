"""Unit tests for the canonical buy-filter math (`buy_filters.py`).

A purely synthetic ~200-bar 3D-style frame with a KNOWN, planted structure:
  * an otherwise strictly-rising ramp (which has NO swing highs by construction), so
  * the ONLY two swing highs are the two peaks we plant at bars 100 and 108, with
  * price making a HIGHER high (60 -> 62) while RSI-MACD makes a LOWER high (3 -> 1)
    == textbook bearish divergence the filter must VETO.

This pins every gate of the keeper (CHARTER §5): swing-high detection, the
bearish-divergence veto, reclaim-and-hold, the 200-MA counter-trend bar-raiser, and
the "pending" (no-look-ahead) tail. No data files, no randomness.

Run:  python3 research/signal_engine/test_buy_filters.py     (or: pytest -q)
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # robust to cwd

from buy_filters import (  # noqa: E402
    swing_highs,
    bearish_divergence,
    reclaim_and_hold,
    buy_filter_verdict,
)

N = 200
PEAK_A, PEAK_B = 100, 108   # adjacent peaks, < `look`(=12) bars apart


def _synthetic_frame(divergent: bool = True) -> pd.DataFrame:
    """~200-bar frame: rising ramp with two planted peaks (A then B).

    `divergent=True`  -> macd lower-high at B  (bearish divergence present).
    `divergent=False` -> macd higher-high at B (no divergence; the control).
    """
    close = 50.0 + 0.05 * np.arange(N)          # strictly rising -> zero swing highs
    # carve two clean local maxima with valleys around them
    planted = {98: 56, 99: 57, 100: 60, 101: 57, 102: 56, 103: 56, 104: 55,
               105: 56, 106: 58, 107: 59, 108: 62, 109: 59, 110: 58, 111: 57, 112: 56}
    for k, v in planted.items():
        close[k] = float(v)
    macd = np.zeros(N)
    macd[PEAK_A] = 3.0
    macd[PEAK_B] = 1.0 if divergent else 5.0    # lower (div) vs higher (no div) high
    return pd.DataFrame({
        "close": close,
        "macd": macd,
        "above200": np.ones(N, dtype=bool),     # confirmed-regime by default
        "w_bull": np.ones(N, dtype=bool),
    })


# ---------------------------------------------------------------- swing highs
def test_swing_highs_finds_only_the_two_planted_peaks() -> None:
    sig = _synthetic_frame()
    hi = swing_highs(sig["close"])
    assert hi == [PEAK_A, PEAK_B], hi          # ramp contributes none; peaks detected
    # confirmed-pivot property: the last `w` bars can never be pivots (no repaint)
    assert max(hi) <= N - 3


# --------------------------------------------------------- bearish divergence
def test_bearish_divergence_on_planted_higher_high_lower_high() -> None:
    div = _synthetic_frame(divergent=True)
    hi = swing_highs(div["close"])
    # price HH (60->62) + macd LH (3->1) within `look` of bar 110 -> veto fires
    assert bearish_divergence(110, div["close"], div["macd"], hi) is True
    # control: identical price path, macd HIGHER-high -> no divergence
    nodiv = _synthetic_frame(divergent=False)
    assert bearish_divergence(110, nodiv["close"], nodiv["macd"], hi) is False
    # need TWO swing highs in the window: just after peak A only one is in range
    assert bearish_divergence(101, div["close"], div["macd"], hi) is False


# ----------------------------------------------------------- reclaim-and-hold
def test_reclaim_and_hold_confirmed_regime() -> None:
    cf = pd.DataFrame({"close": [10.0, 11.0, 10.0],
                       "above200": [True, True, True],
                       "w_bull": [True, True, True]})
    assert reclaim_and_hold(0, cf, len(cf)) == (True, "held confirmation")
    assert reclaim_and_hold(1, cf, len(cf)) == (False, "failed reclaim-and-hold")
    assert reclaim_and_hold(2, cf, len(cf)) == (None, "pending confirmation")  # tail


def test_reclaim_and_hold_counter_trend_bar_raiser() -> None:
    # below 200-MA AND weekly down => must reclaim the 200-MA within 2 bars
    ct = pd.DataFrame({"close": [10.0, 9.0, 9.5, 11.0, 12.0],
                       "above200": [False, False, False, True, True],
                       "w_bull": [False, False, False, False, True]})
    # bar 0: fails the hold AND never reclaims -> blocked
    assert reclaim_and_hold(0, ct, len(ct)) == (False, "counter-trend, no 200-reclaim/hold")
    # bar 2: holds (9.5->11) AND reclaims 200 within 2 bars -> taken
    assert reclaim_and_hold(2, ct, len(ct)) == (True, "reclaimed 200 & held")
    # DISCRIMINATING case (the reason the bar-raiser exists): price HOLDS (rises
    # 10->11->12) but NEVER reclaims the 200-MA -> still BLOCKED. Without this an
    # `ok = held` mutant that drops the reclaim requirement would pass the suite.
    ct_noreclaim = pd.DataFrame({"close": [10.0, 11.0, 12.0, 13.0],
                                 "above200": [False, False, False, False],
                                 "w_bull": [False, False, False, False]})
    assert reclaim_and_hold(0, ct_noreclaim, len(ct_noreclaim)) == (False, "counter-trend, no 200-reclaim/hold")


def test_reclaim_and_hold_held_is_strict_greater() -> None:
    # a FLAT next bar does NOT count as 'held' (strict >, matching the production
    # twin) -> pins the boundary so a `>=` mutant cannot survive.
    flat = pd.DataFrame({"close": [10.0, 10.0, 10.0],
                         "above200": [True, True, True],
                         "w_bull": [True, True, True]})
    assert reclaim_and_hold(0, flat, len(flat)) == (False, "failed reclaim-and-hold")


# ------------------------------------------------------------ verdict (E2E)
def test_buy_filter_verdict_end_to_end() -> None:
    div = _synthetic_frame(divergent=True)
    # at bar 110 the planted divergence vetoes the buy
    assert buy_filter_verdict(110, div) == ("block", "veto: bearish divergence")
    # a clean uptrend bar far from any divergence is taken on the hold
    assert buy_filter_verdict(50, div) == ("take", "held confirmation")
    # the very last bar cannot confirm -> pending (no look-ahead)
    assert buy_filter_verdict(N - 1, div) == ("pending", "pending confirmation")
    # verdict strings ARE the chart-marker quality values (CHARTER §7)
    assert {buy_filter_verdict(110, div)[0], buy_filter_verdict(50, div)[0]} <= {"take", "block", "pending"}


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} buy-filter tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
