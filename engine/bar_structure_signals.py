"""engine/bar_structure_signals.py — Inside/outside bar grammar + TheSTRAT scenario signals.

Display-tier chart-grammar family. No authority, no buy/sell/stop commands, no
composite scores.

Bar taxonomy (each bar classified vs the PRIOR completed bar):
  inside  : H < prevH AND L > prevL          — contraction within prior range
  outside : H > prevH AND L < prevL          — expansion engulfs prior range
  two_up  : H > prevH AND L >= prevL         — higher high, non-lower low
  two_dn  : L < prevL AND H <= prevH         — lower low, non-higher high

NOTE: The store carries no 'open' column. Directional bar bodies would require
open vs close; because open is unavailable we classify bars solely by high/low
vs the prior bar's high/low (the public TheSTRAT canon uses the same H/L
taxonomy). Where body direction matters for a scenario, we approximate it using
close vs prior close.

Public methodology: Rob Smith — TheSTRAT / strat.trading. The OBIB ("Holy Grail")
setup and related bar grammars are part of the same widely-taught price-action canon
(TradingWarz Golden et al. share the same public definitions).

Signals
-------
  ib_setup         state   0   current bar is an inside bar
  ob_expansion     state   0   current bar is an outside bar
  obib_coil        event   0   outside bar followed immediately by inside bar (OBIB)
  triple_ib_coil   event   0   three consecutive inside bars — fires on bar 3
  strat_212_bull   event  +1   two_up → inside → break above IB high  (2-1-2 continuation)
  strat_212_bear   event  -1   two_dn → inside → break below IB low   (mirror)
  strat_rev_bull   event  +1   two_dn → inside → break above IB high  (2-1-2 reversal)
  strat_rev_bear   event  -1   two_up → inside → break below IB low   (mirror)
  strat_312_bull   event  +1   outside → inside → break above IB high (3-1-2)
  strat_312_bear   event  -1   outside → inside → break below IB low  (mirror)

All signals are computed from completed bars only (no look-ahead). The output
Series is aligned to df.index; events are 0/1 int (1 only on the bar where the
event becomes known), states are 0/1 int (1 while the condition holds).
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal bar-type helpers
# ---------------------------------------------------------------------------

def _bar_types(df: pd.DataFrame) -> tuple[
    pd.Series, pd.Series, pd.Series, pd.Series
]:
    """Return (is_inside, is_outside, is_two_up, is_two_dn) boolean Series.

    All comparisons use high and low only (no open in store).
    Classifications are mutually exclusive per bar (a bar can be at most one
    of inside/outside/two_up/two_dn; bars that match none are 'one_bar'/doji).
    First bar is always False for every type (no prior bar available).
    """
    high = df["high"]
    low = df["low"]
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    is_inside = (high < prev_high) & (low > prev_low)
    is_outside = (high > prev_high) & (low < prev_low)
    is_two_up = (high > prev_high) & (low >= prev_low) & ~is_outside
    is_two_dn = (low < prev_low) & (high <= prev_high) & ~is_outside

    return (
        is_inside.fillna(False),
        is_outside.fillna(False),
        is_two_up.fillna(False),
        is_two_dn.fillna(False),
    )


# ---------------------------------------------------------------------------
# Public signal functions
# ---------------------------------------------------------------------------

def ib_setup(df: pd.DataFrame, **_params) -> pd.Series:
    """State: current completed bar is an inside bar (H < prevH and L > prevL).

    Returns {0, 1}. PIT-clean: only completed-bar high/low used.
    """
    is_inside, _, _, _ = _bar_types(df)
    result = is_inside.astype(int)
    result.name = "ib_setup"
    return result


def ob_expansion(df: pd.DataFrame, **_params) -> pd.Series:
    """State: current completed bar is an outside bar (H > prevH and L < prevL).

    Returns {0, 1}. PIT-clean.
    """
    _, is_outside, _, _ = _bar_types(df)
    result = is_outside.astype(int)
    result.name = "ob_expansion"
    return result


def obib_coil(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: outside bar immediately followed by an inside bar ('OBIB Holy Grail').

    Fires 1 on the inside-bar close; prior bar must be an outside bar.
    Returns {0, 1}. PIT-clean.
    """
    _, is_outside, _, _ = _bar_types(df)
    is_inside, _, _, _ = _bar_types(df)
    # current bar is inside AND prior bar was outside
    prior_outside = is_outside.shift(1).fillna(False)
    fired = (is_inside & prior_outside).astype(int)
    fired.name = "obib_coil"
    return fired


def triple_ib_coil(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: three consecutive inside bars — fires on the close of the third.

    Returns {0, 1}. PIT-clean: rolling trailing window.
    """
    is_inside, _, _, _ = _bar_types(df)
    ib_int = is_inside.astype(int)
    # rolling sum of 3; count == 3 means all three were inside bars
    count3 = ib_int.rolling(3, min_periods=3).sum()
    fired = (count3 == 3).fillna(False).astype(int)
    fired.name = "triple_ib_coil"
    return fired


def strat_212_bull(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: two_up → inside → break above inside bar's high (2-1-2 bullish continuation).

    Pattern (bar indices relative to current bar i):
      bar i-2: two_up
      bar i-1: inside bar
      bar i  : high > bar[i-1].high  (break above the inside bar's high)

    Fires on the break bar (bar i). Returns {0, 1}. PIT-clean.
    """
    is_inside, _, is_two_up, _ = _bar_types(df)
    high = df["high"]
    prev_high = high.shift(1)           # bar i-1 high (inside bar's high)
    two_up_two_ago = is_two_up.shift(2).fillna(False)
    inside_one_ago = is_inside.shift(1).fillna(False)
    breaks_ib_high = high > prev_high
    fired = (two_up_two_ago & inside_one_ago & breaks_ib_high).astype(int)
    fired.name = "strat_212_bull"
    return fired


def strat_212_bear(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: two_dn → inside → break below inside bar's low (2-1-2 bearish continuation).

    Returns {0, 1}. PIT-clean.
    """
    is_inside, _, _, is_two_dn = _bar_types(df)
    low = df["low"]
    prev_low = low.shift(1)
    two_dn_two_ago = is_two_dn.shift(2).fillna(False)
    inside_one_ago = is_inside.shift(1).fillna(False)
    breaks_ib_low = low < prev_low
    fired = (two_dn_two_ago & inside_one_ago & breaks_ib_low).astype(int)
    fired.name = "strat_212_bear"
    return fired


def strat_rev_bull(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: two_dn → inside → break above inside bar's high (2-1-2 bullish reversal).

    A bearish two-bar is followed by a compression inside bar; then price
    breaks higher — a potential reversal setup. Returns {0, 1}. PIT-clean.
    """
    is_inside, _, _, is_two_dn = _bar_types(df)
    high = df["high"]
    prev_high = high.shift(1)
    two_dn_two_ago = is_two_dn.shift(2).fillna(False)
    inside_one_ago = is_inside.shift(1).fillna(False)
    breaks_ib_high = high > prev_high
    fired = (two_dn_two_ago & inside_one_ago & breaks_ib_high).astype(int)
    fired.name = "strat_rev_bull"
    return fired


def strat_rev_bear(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: two_up → inside → break below inside bar's low (2-1-2 bearish reversal).

    A bullish two-bar is followed by a compression inside bar; then price
    breaks lower — a potential reversal setup. Returns {0, 1}. PIT-clean.
    """
    is_inside, _, is_two_up, _ = _bar_types(df)
    low = df["low"]
    prev_low = low.shift(1)
    two_up_two_ago = is_two_up.shift(2).fillna(False)
    inside_one_ago = is_inside.shift(1).fillna(False)
    breaks_ib_low = low < prev_low
    fired = (two_up_two_ago & inside_one_ago & breaks_ib_low).astype(int)
    fired.name = "strat_rev_bear"
    return fired


def strat_312_bull(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: outside bar → inside bar → break above inside bar's high (3-1-2 bull).

    The outside bar (bar type 3) expands the range; the inside bar (1) coils;
    then the break bar (2) resolves higher. Returns {0, 1}. PIT-clean.
    """
    is_inside, is_outside, _, _ = _bar_types(df)
    high = df["high"]
    prev_high = high.shift(1)
    outside_two_ago = is_outside.shift(2).fillna(False)
    inside_one_ago = is_inside.shift(1).fillna(False)
    breaks_ib_high = high > prev_high
    fired = (outside_two_ago & inside_one_ago & breaks_ib_high).astype(int)
    fired.name = "strat_312_bull"
    return fired


def strat_312_bear(df: pd.DataFrame, **_params) -> pd.Series:
    """Event: outside bar → inside bar → break below inside bar's low (3-1-2 bear).

    Returns {0, 1}. PIT-clean.
    """
    is_inside, is_outside, _, _ = _bar_types(df)
    low = df["low"]
    prev_low = low.shift(1)
    outside_two_ago = is_outside.shift(2).fillna(False)
    inside_one_ago = is_inside.shift(1).fillna(False)
    breaks_ib_low = low < prev_low
    fired = (outside_two_ago & inside_one_ago & breaks_ib_low).astype(int)
    fired.name = "strat_312_bear"
    return fired


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


_COMMON = {
    "family": "bar_structure",
    "dependency_family": "pattern_structure",
    "entry_stack_blocked": False,
    "challenger_only": False,
    "provenance": "Rob Smith — TheSTRAT public methodology; strat.trading",
    "actionable_lag": 0,
}

SIGNALS: dict[str, dict[str, Any]] = {
    "ib_setup": {
        **_COMMON,
        "fn": ib_setup,
        "kind": "state",
        "direction": 0,
        "role": "setup",
        "default_params": {},
        "display": _disp(
            "Inside Bar — price range compressed within prior bar",
            "内包K线 — 当前K线价格范围收缩至前根K线之内",
        ),
        "glyph": "compress",
    },
    "ob_expansion": {
        **_COMMON,
        "fn": ob_expansion,
        "kind": "state",
        "direction": 0,
        "role": "context",
        "default_params": {},
        "display": _disp(
            "Outside Bar — price range expands beyond prior bar on both sides",
            "外包K线 — 当前K线高低点双向超越前根K线",
        ),
        "glyph": "expand",
    },
    "obib_coil": {
        **_COMMON,
        "fn": obib_coil,
        "kind": "event",
        "direction": 0,
        "role": "setup",
        "default_params": {},
        "display": _disp(
            "Outside-Inside Bar Coil — outside bar followed by inside bar compression",
            "外包收缩形态 — 外包K线后紧接内包K线压缩蓄势",
        ),
        "glyph": "coil",
    },
    "triple_ib_coil": {
        **_COMMON,
        "fn": triple_ib_coil,
        "kind": "event",
        "direction": 0,
        "role": "setup",
        "default_params": {},
        "display": _disp(
            "Three Consecutive Inside Bars — prolonged compression coil",
            "三连内包K线 — 连续三根内包K线极度压缩蓄势",
        ),
        "glyph": "coil",
    },
    "strat_212_bull": {
        **_COMMON,
        "fn": strat_212_bull,
        "kind": "event",
        "direction": +1,
        "role": "trigger",
        "default_params": {},
        "display": _disp(
            "Bullish 2-1-2 Continuation — higher high bar, inside bar, upside break",
            "多头2-1-2延续形态 — 高高K线、内包K线后向上突破",
        ),
        "glyph": "arrow_up",
    },
    "strat_212_bear": {
        **_COMMON,
        "fn": strat_212_bear,
        "kind": "event",
        "direction": -1,
        "role": "trigger",
        "default_params": {},
        "display": _disp(
            "Bearish 2-1-2 Continuation — lower low bar, inside bar, downside break",
            "空头2-1-2延续形态 — 低低K线、内包K线后向下突破",
        ),
        "glyph": "arrow_down",
    },
    "strat_rev_bull": {
        **_COMMON,
        "fn": strat_rev_bull,
        "kind": "event",
        "direction": +1,
        "role": "trigger",
        "default_params": {},
        "display": _disp(
            "Bullish 2-1-2 Reversal — lower low bar, inside bar, upside break",
            "多头2-1-2反转形态 — 低低K线、内包K线后向上突破反转",
        ),
        "glyph": "arrow_up",
    },
    "strat_rev_bear": {
        **_COMMON,
        "fn": strat_rev_bear,
        "kind": "event",
        "direction": -1,
        "role": "trigger",
        "default_params": {},
        "display": _disp(
            "Bearish 2-1-2 Reversal — higher high bar, inside bar, downside break",
            "空头2-1-2反转形态 — 高高K线、内包K线后向下突破反转",
        ),
        "glyph": "arrow_down",
    },
    "strat_312_bull": {
        **_COMMON,
        "fn": strat_312_bull,
        "kind": "event",
        "direction": +1,
        "role": "trigger",
        "default_params": {},
        "display": _disp(
            "Bullish 3-1-2 — outside bar, inside bar coil, upside break",
            "多头3-1-2形态 — 外包K线、内包K线蓄势后向上突破",
        ),
        "glyph": "arrow_up",
    },
    "strat_312_bear": {
        **_COMMON,
        "fn": strat_312_bear,
        "kind": "event",
        "direction": -1,
        "role": "trigger",
        "default_params": {},
        "display": _disp(
            "Bearish 3-1-2 — outside bar, inside bar coil, downside break",
            "空头3-1-2形态 — 外包K线、内包K线蓄势后向下突破",
        ),
        "glyph": "arrow_down",
    },
}
