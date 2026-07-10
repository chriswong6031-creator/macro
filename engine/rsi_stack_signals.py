"""engine/rsi_stack_signals.py — RSI stack (multi-timeframe) chart-grammar signal family.

Display-tier descriptive chart-grammar family. No authority, no buy/sell/stop
commands, no composite scores. Routed per research/DANNYTRADES_INDICATOR_DOCKET_
ADJUDICATION_2026-07-10_BY_FABLE.md ruling DT-R18.

RSI periods 7, 14, 21 are FROZEN per DT-R18 adjudication pre-registration — do
not alter them without a new adjudication ruling. RSI is computed via engine.canon.rsi
(Wilder/SMA-seeded RMA, the canonical cross-engine implementation).

The overbought threshold of 80 is a public descriptive reference band. The
oversold threshold of 30 is a public descriptive reference band.

Signals
-------
  rsi_stack_curl_up     event  +1  all three RSIs (7/14/21) turn upward simultaneously
  rsi_stack_curl_down   event  -1  all three RSIs turn downward simultaneously
  rsi_stack_oversold    state  +1  all three RSIs are at or below 30
  rsi_stack_overbought  state  -1  all three RSIs are at or above 80 (reference band)
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from engine.canon import rsi as _canon_rsi

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Frozen RSI periods (per DT-R18 adjudication pre-registration)
# ---------------------------------------------------------------------------
_RSI_PERIODS: tuple[int, int, int] = (7, 14, 21)

# Public descriptive reference bands (per DT-R18 governance)
_OVERSOLD_BAND: float = 30.0
_OVERBOUGHT_BAND: float = 80.0


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _compute_stack(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (r7, r14, r21) using the canonical Wilder RSI."""
    r7 = _canon_rsi(close, n=7)
    r14 = _canon_rsi(close, n=14)
    r21 = _canon_rsi(close, n=21)
    return r7, r14, r21


# ---------------------------------------------------------------------------
# Public signal functions
# ---------------------------------------------------------------------------

def rsi_stack_curl_up(df: pd.DataFrame, **kwargs) -> pd.Series:
    """Event: all three RSIs (7/14/21) are simultaneously rising (rising edge only).

    Returns {0.0, 1.0} — 1.0 on the first bar where all three diffs are positive
    and on the prior bar at least one diff was not positive (rising edge transition).
    """
    close = df["close"]
    r7, r14, r21 = _compute_stack(close)
    cond = (r7.diff() > 0) & (r14.diff() > 0) & (r21.diff() > 0)
    fired = (cond & ~cond.shift(1, fill_value=False)).astype(float).fillna(0.0)
    fired.name = "rsi_stack_curl_up"
    return fired


def rsi_stack_curl_down(df: pd.DataFrame, **kwargs) -> pd.Series:
    """Event: all three RSIs (7/14/21) are simultaneously falling (rising edge only).

    Returns {0.0, 1.0} — 1.0 on the first bar where all three diffs are negative
    and on the prior bar at least one diff was not negative (rising edge transition).
    """
    close = df["close"]
    r7, r14, r21 = _compute_stack(close)
    cond = (r7.diff() < 0) & (r14.diff() < 0) & (r21.diff() < 0)
    fired = (cond & ~cond.shift(1, fill_value=False)).astype(float).fillna(0.0)
    fired.name = "rsi_stack_curl_down"
    return fired


def rsi_stack_oversold(df: pd.DataFrame, **kwargs) -> pd.Series:
    """State: all three RSIs (7/14/21) are at or below 30 (public reference band).

    Returns {0.0, 1.0}.
    """
    close = df["close"]
    r7, r14, r21 = _compute_stack(close)
    result = ((r7 <= _OVERSOLD_BAND) & (r14 <= _OVERSOLD_BAND) & (r21 <= _OVERSOLD_BAND))
    result = result.astype(float).fillna(0.0)
    result.name = "rsi_stack_oversold"
    return result


def rsi_stack_overbought(df: pd.DataFrame, **kwargs) -> pd.Series:
    """State: all three RSIs (7/14/21) are at or above 80 (public reference band).

    The 80 threshold is a public descriptive reference band per DT-R18; it is
    labeled as such and carries no signal authority.

    Returns {0.0, 1.0}.
    """
    close = df["close"]
    r7, r14, r21 = _compute_stack(close)
    result = ((r7 >= _OVERBOUGHT_BAND) & (r14 >= _OVERBOUGHT_BAND) & (r21 >= _OVERBOUGHT_BAND))
    result = result.astype(float).fillna(0.0)
    result.name = "rsi_stack_overbought"
    return result


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

SIGNALS: dict[str, dict[str, Any]] = {
    "rsi_stack_curl_up": {
        "fn": rsi_stack_curl_up,
        "kind": "event",
        "family": "rsi_stack",
        "direction": +1,
        "default_params": {"periods": list(_RSI_PERIODS)},
        "display": {
            "en": "RSI Stack (7/14/21) — All Three Curling Up",
            "zh": "RSI叠加（7/14/21）— 三条RSI同步上翘",
        },
        "glyph": "arrow_up",
    },
    "rsi_stack_curl_down": {
        "fn": rsi_stack_curl_down,
        "kind": "event",
        "family": "rsi_stack",
        "direction": -1,
        "default_params": {"periods": list(_RSI_PERIODS)},
        "display": {
            "en": "RSI Stack (7/14/21) — All Three Curling Down",
            "zh": "RSI叠加（7/14/21）— 三条RSI同步下翻",
        },
        "glyph": "arrow_down",
    },
    "rsi_stack_oversold": {
        "fn": rsi_stack_oversold,
        "kind": "state",
        "family": "rsi_stack",
        "direction": +1,
        "default_params": {"periods": list(_RSI_PERIODS), "threshold": _OVERSOLD_BAND},
        "display": {
            "en": "RSI Stack (7/14/21) — All Three at or Below 30",
            "zh": "RSI叠加（7/14/21）— 三条RSI均低于30参考带",
        },
        "glyph": "circle_green",
    },
    "rsi_stack_overbought": {
        "fn": rsi_stack_overbought,
        "kind": "state",
        "family": "rsi_stack",
        "direction": -1,
        "default_params": {"periods": list(_RSI_PERIODS), "threshold": _OVERBOUGHT_BAND},
        "display": {
            "en": "RSI Stack (7/14/21) — All Three at or Above 80 (reference band)",
            "zh": "RSI叠加（7/14/21）— 三条RSI均超过80参考带",
        },
        "glyph": "circle_red",
    },
}
