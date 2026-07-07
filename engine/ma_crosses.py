"""engine/ma_crosses.py — Plain moving-average cross signals + price-vs-MA signals.

Reconstructs StockInvest 'Moving Average Cross Signals' (Golden Cross / Death Cross) and
'Moving Averages' buy/sell lists.

IMPORTANT DISTINCTION from tech_stars.py
-----------------------------------------
Golden Cross / Death Cross here are PLAIN MA crosses — short SMA crosses above/below long SMA.
There is NO price-line proximity gate (the "three-entity intersection" price gate is what
distinguishes Golden Star / Death Star in tech_stars.py from these plain crosses).

Registered signal families
---------------------------
Cross signals (golden_cross / death_cross):
  Pairs: (7, 35), (21, 100), (50, 200)  — pre-registered StockInvest pairs.
  - golden_cross_{short}_{long}: short SMA crosses ABOVE long SMA (+1)
  - death_cross_{short}_{long}:  short SMA crosses BELOW long SMA (-1)

Price-vs-MA signals (ma_buy / ma_sell):
  Periods: 7, 21, 35, 100
  - ma_buy_{n}:  close crosses ABOVE SMA(n) (+1)
  - ma_sell_{n}: close crosses BELOW SMA(n) (-1)

All signals are 'event' kind: fire {0.0, 1.0} on the bar the event is knowable.
PIT-clean: rolling windows only, no centered/future-referencing operations.

This is display-only / research. No LLM-originated signals or escalations.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-registered MA pairs and periods
# ---------------------------------------------------------------------------
CROSS_PAIRS: list[tuple[int, int]] = [(7, 35), (21, 100), (50, 200)]
PRICE_MA_PERIODS: list[int] = [7, 21, 35, 100]


# ---------------------------------------------------------------------------
# Golden Cross: plain short-SMA-crosses-above-long-SMA
# ---------------------------------------------------------------------------

def golden_cross(df: pd.DataFrame, short_n: int = 50, long_n: int = 200) -> pd.Series:
    """Short SMA(short_n) crosses ABOVE long SMA(long_n).

    Returns {0.0, 1.0} event Series — 1.0 on the bar the cross fires.
    PIT-clean: rolling only, no forward windows.

    Parameters
    ----------
    df : DataFrame
        OHLCV frame with 'close' column and DatetimeIndex.
    short_n, long_n : int
        SMA periods. Pre-registered pairs: (7, 35), (21, 100), (50, 200).
    """
    from engine.strategy_signals import sma  # noqa: PLC0415
    from engine.canon import crossover       # noqa: PLC0415

    close = df["close"]
    ma_s = sma(close, short_n)
    ma_l = sma(close, long_n)

    fired = crossover(ma_s, ma_l).astype(float)
    fired.name = f"golden_cross_{short_n}_{long_n}"
    return fired


def death_cross(df: pd.DataFrame, short_n: int = 50, long_n: int = 200) -> pd.Series:
    """Short SMA(short_n) crosses BELOW long SMA(long_n).

    Returns {0.0, 1.0} event Series — 1.0 on the bar the cross fires.
    PIT-clean: rolling only, no forward windows.

    Parameters
    ----------
    df : DataFrame
        OHLCV frame with 'close' column and DatetimeIndex.
    short_n, long_n : int
        SMA periods. Pre-registered pairs: (7, 35), (21, 100), (50, 200).
    """
    from engine.strategy_signals import sma  # noqa: PLC0415
    from engine.canon import crossunder      # noqa: PLC0415

    close = df["close"]
    ma_s = sma(close, short_n)
    ma_l = sma(close, long_n)

    fired = crossunder(ma_s, ma_l).astype(float)
    fired.name = f"death_cross_{short_n}_{long_n}"
    return fired


# ---------------------------------------------------------------------------
# Price-vs-MA buy/sell: close crosses above/below SMA(n)
# ---------------------------------------------------------------------------

def ma_buy(df: pd.DataFrame, n: int = 50) -> pd.Series:
    """Close crosses ABOVE SMA(n).

    Returns {0.0, 1.0} event Series — 1.0 on the bar the close crosses above.
    PIT-clean: rolling only.

    Parameters
    ----------
    df : DataFrame
        OHLCV frame with 'close' column and DatetimeIndex.
    n : int
        SMA period. Pre-registered: 7, 21, 35, 100.
    """
    from engine.strategy_signals import sma  # noqa: PLC0415
    from engine.canon import crossover       # noqa: PLC0415

    close = df["close"]
    ma = sma(close, n)

    fired = crossover(close, ma).astype(float)
    fired.name = f"ma_buy_{n}"
    return fired


def ma_sell(df: pd.DataFrame, n: int = 50) -> pd.Series:
    """Close crosses BELOW SMA(n).

    Returns {0.0, 1.0} event Series — 1.0 on the bar the close crosses below.
    PIT-clean: rolling only.

    Parameters
    ----------
    df : DataFrame
        OHLCV frame with 'close' column and DatetimeIndex.
    n : int
        SMA period. Pre-registered: 7, 21, 35, 100.
    """
    from engine.strategy_signals import sma  # noqa: PLC0415
    from engine.canon import crossunder      # noqa: PLC0415

    close = df["close"]
    ma = sma(close, n)

    fired = crossunder(close, ma).astype(float)
    fired.name = f"ma_sell_{n}"
    return fired


# ---------------------------------------------------------------------------
# SIGNALS catalog registration
# ---------------------------------------------------------------------------

def _make_golden_cross(short_n: int, long_n: int):
    """Factory: returns a golden_cross callable with fixed short_n/long_n."""
    def _fn(df: pd.DataFrame, **params) -> pd.Series:
        return golden_cross(df, short_n=short_n, long_n=long_n)
    _fn.__name__ = f"golden_cross_{short_n}_{long_n}"
    return _fn


def _make_death_cross(short_n: int, long_n: int):
    """Factory: returns a death_cross callable with fixed short_n/long_n."""
    def _fn(df: pd.DataFrame, **params) -> pd.Series:
        return death_cross(df, short_n=short_n, long_n=long_n)
    _fn.__name__ = f"death_cross_{short_n}_{long_n}"
    return _fn


def _make_ma_buy(n: int):
    """Factory: returns a ma_buy callable with fixed period n."""
    def _fn(df: pd.DataFrame, **params) -> pd.Series:
        return ma_buy(df, n=n)
    _fn.__name__ = f"ma_buy_{n}"
    return _fn


def _make_ma_sell(n: int):
    """Factory: returns a ma_sell callable with fixed period n."""
    def _fn(df: pd.DataFrame, **params) -> pd.Series:
        return ma_sell(df, n=n)
    _fn.__name__ = f"ma_sell_{n}"
    return _fn


SIGNALS: dict[str, dict[str, Any]] = {}

# Register golden_cross for all three pairs
for _short, _long in CROSS_PAIRS:
    _sid = f"golden_cross_{_short}_{_long}"
    SIGNALS[_sid] = {
        "fn": _make_golden_cross(_short, _long),
        "kind": "event",
        "family": "ma_crosses",
        "direction": +1,
        "default_params": {"short_n": _short, "long_n": _long},
        "display": {
            "en": f"Golden Cross ({_short}/{_long})",
            "zh": f"黄金交叉 ({_short}/{_long})",
        },
        "glyph": "cross_up",
    }

# Register death_cross for all three pairs
for _short, _long in CROSS_PAIRS:
    _sid = f"death_cross_{_short}_{_long}"
    SIGNALS[_sid] = {
        "fn": _make_death_cross(_short, _long),
        "kind": "event",
        "family": "ma_crosses",
        "direction": -1,
        "default_params": {"short_n": _short, "long_n": _long},
        "display": {
            "en": f"Death Cross ({_short}/{_long})",
            "zh": f"死亡交叉 ({_short}/{_long})",
        },
        "glyph": "cross_down",
    }

# Register ma_buy for all pre-registered periods
for _n in PRICE_MA_PERIODS:
    _sid = f"ma_buy_{_n}"
    SIGNALS[_sid] = {
        "fn": _make_ma_buy(_n),
        "kind": "event",
        "family": "ma_price",
        "direction": +1,
        "default_params": {"n": _n},
        "display": {
            "en": f"MA Buy ({_n})",
            "zh": f"均线买入 ({_n})",
        },
        "glyph": "arrow_up",
    }

# Register ma_sell for all pre-registered periods
for _n in PRICE_MA_PERIODS:
    _sid = f"ma_sell_{_n}"
    SIGNALS[_sid] = {
        "fn": _make_ma_sell(_n),
        "kind": "event",
        "family": "ma_price",
        "direction": -1,
        "default_params": {"n": _n},
        "display": {
            "en": f"MA Sell ({_n})",
            "zh": f"均线卖出 ({_n})",
        },
        "glyph": "arrow_down",
    }
