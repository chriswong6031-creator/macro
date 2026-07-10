"""engine/trend_ribbon_signals.py — Trend ribbon chart-grammar signal family.

Display-tier descriptive chart-grammar family. No authority, no buy/sell/stop
commands, no composite scores. Routed per research/DANNYTRADES_INDICATOR_DOCKET_
ADJUDICATION_2026-07-10_BY_FABLE.md ruling DT-R18.

Ribbon state is sourced from engine.dannytrades.ribbon_trend(), which is imported
and reused — math is NOT duplicated here. The ribbon returns {+1, 0, -1}.

Signals
-------
  ribbon_up         state  +1  ribbon == +1
  ribbon_down       state  -1  ribbon == -1
  ribbon_flip_up    event  +1  ribbon transitions to +1
  ribbon_flip_down  event  -1  ribbon transitions to -1
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public signal functions
# ---------------------------------------------------------------------------

def ribbon_up(df: pd.DataFrame, **kwargs) -> pd.Series:
    """State: EMA ribbon is in uptrend mode (ribbon == +1). Returns {0.0, 1.0}."""
    from engine.dannytrades import ribbon_trend  # noqa: PLC0415

    close = df["close"]
    ribbon = ribbon_trend(close)
    result = (ribbon == 1).astype(float).fillna(0.0)
    result.name = "ribbon_up"
    return result


def ribbon_down(df: pd.DataFrame, **kwargs) -> pd.Series:
    """State: EMA ribbon is in downtrend mode (ribbon == -1). Returns {0.0, 1.0}."""
    from engine.dannytrades import ribbon_trend  # noqa: PLC0415

    close = df["close"]
    ribbon = ribbon_trend(close)
    result = (ribbon == -1).astype(float).fillna(0.0)
    result.name = "ribbon_down"
    return result


def ribbon_flip_up(df: pd.DataFrame, **kwargs) -> pd.Series:
    """Event: ribbon flips to +1 (any prior state → +1). Returns {0.0, 1.0}."""
    from engine.dannytrades import ribbon_trend  # noqa: PLC0415

    close = df["close"]
    ribbon = ribbon_trend(close)
    fired = ((ribbon == 1) & (ribbon.shift(1) != 1)).astype(float).fillna(0.0)
    fired.name = "ribbon_flip_up"
    return fired


def ribbon_flip_down(df: pd.DataFrame, **kwargs) -> pd.Series:
    """Event: ribbon flips to -1 (any prior state → -1). Returns {0.0, 1.0}."""
    from engine.dannytrades import ribbon_trend  # noqa: PLC0415

    close = df["close"]
    ribbon = ribbon_trend(close)
    fired = ((ribbon == -1) & (ribbon.shift(1) != -1)).astype(float).fillna(0.0)
    fired.name = "ribbon_flip_down"
    return fired


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

SIGNALS: dict[str, dict[str, Any]] = {
    "ribbon_up": {
        "fn": ribbon_up,
        "kind": "state",
        "family": "trend_ribbon",
        "direction": +1,
        "default_params": {},
        "display": {
            "en": "Trend Ribbon — Uptrend State",
            "zh": "趋势带 — 上升趋势状态",
        },
        "glyph": "arrow_up",
    },
    "ribbon_down": {
        "fn": ribbon_down,
        "kind": "state",
        "family": "trend_ribbon",
        "direction": -1,
        "default_params": {},
        "display": {
            "en": "Trend Ribbon — Downtrend State",
            "zh": "趋势带 — 下降趋势状态",
        },
        "glyph": "arrow_down",
    },
    "ribbon_flip_up": {
        "fn": ribbon_flip_up,
        "kind": "event",
        "family": "trend_ribbon",
        "direction": +1,
        "default_params": {},
        "display": {
            "en": "Trend Ribbon — Flip to Uptrend",
            "zh": "趋势带 — 翻转为上升趋势",
        },
        "glyph": "cross_up",
    },
    "ribbon_flip_down": {
        "fn": ribbon_flip_down,
        "kind": "event",
        "family": "trend_ribbon",
        "direction": -1,
        "default_params": {},
        "display": {
            "en": "Trend Ribbon — Flip to Downtrend",
            "zh": "趋势带 — 翻转为下降趋势",
        },
        "glyph": "cross_down",
    },
}
