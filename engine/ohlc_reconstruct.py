"""Conservative high/low/open reconstruction for CLOSE-ONLY price series.

Many of the dashboard's non-US series carry no intraday high/low: Tencent
``0700.HK`` (``site/hkstockdata/0700.HK.json`` -> ``chart.c``), the A-share /
Canada / International search caches, and the S&P breadth closes caches are all
**close-only**. The US engine path is close-only too today
(``scripts/build_signal_quality.py`` reads only ``["close"]``). Close-only data
breaks three consumers at once:

  1. candlestick rendering (the chart can only draw a line/area);
  2. the signal engine's swing-high / bearish-divergence logic
     (``engine.signal_quality._swing_highs`` / ``_bear_div``); and
  3. any ATR-based exit / stop.

This module imputes a **conservative** high/low band from close alone so those
consumers can attach. The band is **mean-unbiased** for the true high-low range
and biased *wide* relative to the data-implied estimate, so it does not
*systematically* understate realised volatility (the charter §1 constraint). It is
NOT a per-bar guarantee: on individual volatility-event bars (gaps / earnings) the
synthetic range still falls short of the true range (~18-22% of bars; see the
validation report). That is fine for what it feeds — candle rendering and swing /
divergence detection (validated: zero drawdown impact) — but the reconstructed
high/low should NOT be trusted for tail-risk stop sizing. Deliberately small,
deterministic and self-contained.

Method (the "why", grounded in theory — NOT fitted to any sample)
-----------------------------------------------------------------
The true range (``high-low``) is unobservable without high/low, so we estimate it
from the only thing we have — the close-to-close move ``|Δclose|`` — plus a fixed
prior for how much wider the intrabar range runs than the close-to-close change:

* ``cc_atr`` = Wilder RMA (the canonical ATR smoothing) of ``|Δclose|`` over
  ``ATR_LEN`` bars. This is a *lower-bound-ish* volatility read: the realised
  high-low range is always ≥ ``|Δclose|`` and on average strictly larger.
* For a random walk over one bar, ``E[high-low] = 2·E[|Δclose|]`` — both reduce
  to multiples of ``σ√(2/π)`` (``E[max-min]=2σ√(2/π)``; ``E|B(1)|=σ√(2/π)``).
  So ``RANGE_MULT = 2.0`` is the **unbiased** random-walk estimate of the true
  range from ``|Δclose|`` — a model prior. It is NOT grid-searched against the
  ground-truth OHLC (a decades-deep, ~1.1M-bar US panel; data/stocks/*.parquet):
  the data-implied unbiased multiplier there is ~1.65, and we deliberately keep
  the wider 2.0 as a conservative (never-systematically-understate) margin over
  that data estimate — the opposite of fitting down to the sample. It also makes
  the deterministic recipe below collapse to the textbook ``high = close + ATR/2``
  once ``ATR := RANGE_MULT·cc_atr``.
* A floor of ``FLOOR_PCT`` of close keeps a dead-flat / halted series from
  collapsing to a zero-height candle (and from understating a real but quiet bar).

Variants
--------
``symmetric`` (DEFAULT, what the charter task asked to *prefer*):
    ``high = close + ATR/2``,  ``low = close - ATR/2``,  ``open = prior close``.
    Then clamp so the bar always contains the open->close body:
    ``high = max(high, open, close)``, ``low = min(low, open, close)``.
    Fully reproducible, no randomness. **Trade-off:** it parks the close in the
    middle of the bar, whereas real bars often close near the high (up days) or
    low (down days). We accept that — it is good-enough for candle rendering,
    swing detection and ATR, and on average it does not understate the range
    (mean-unbiased; see the per-bar caveat in the module docstring).

``body_aware``:
    same *total* range (``ATR``), but the wick is split by the open->close
    direction so the close sits nearer the high on up bars / the low on down bars
    (fraction ``BODY_SKEW``). Still deterministic, still clamped, still never
    understating. Offered for charts that want more lifelike candles; the signal
    path uses ``symmetric`` so swing highs stay close-anchored and stable.

No randomness is used anywhere: validation and signals must be reproducible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# --- priors (NOT fitted to the validation sample; see module docstring) --------
ATR_LEN = 14          # Wilder ATR window on the close-to-close move
RANGE_MULT = 2.0      # E[high-low] / E[|Δclose|] under a random walk (unbiased)
FLOOR_PCT = 0.008     # min half-... see below: min reconstructed ATR = 0.8% of close
BODY_SKEW = 0.70      # body_aware: on an up bar the close sits this far UP the range
                      # (near the high); mirror on a down bar (near the low)


def atr_proxy(close: pd.Series, length: int = ATR_LEN,
              range_mult: float = RANGE_MULT, floor_pct: float = FLOOR_PCT) -> pd.Series:
    """Estimate the TRUE-RANGE ATR from a close-only series.

    ``RMA(|Δclose|)`` scaled by ``range_mult`` (the random-walk range/|Δclose|
    ratio), floored at ``floor_pct`` of close so quiet/flat bars keep a visible,
    non-understating band. Returns a strictly-positive Series aligned to ``close``
    (no NaNs — early bars fall back to the floor / expanding mean).
    """
    close = close.astype(float)
    dcc = close.diff().abs()
    # Wilder RMA == ewm(alpha=1/length). adjust=False matches ta.atr / ta.rma.
    rma = dcc.ewm(alpha=1.0 / length, adjust=False, min_periods=1).mean()
    atr = range_mult * rma
    floor = floor_pct * close.abs()
    # max with the floor keeps the band strictly positive on every bar — incl. bar 0
    # (Δclose undefined => rma NaN) and dead-flat/halted stretches — whenever
    # floor_pct > 0 (the production default). With floor_pct == 0 bar 0 is 0.
    atr = pd.concat([atr, floor], axis=1).max(axis=1)
    return atr.fillna(floor)


def reconstruct_ohlc(close: pd.Series, *, mode: str = "symmetric",
                     length: int = ATR_LEN, range_mult: float = RANGE_MULT,
                     floor_pct: float = FLOOR_PCT) -> pd.DataFrame:
    """Reconstruct a conservative OHLC frame from a close-only series.

    Parameters
    ----------
    close : pd.Series   close prices (DatetimeIndex), may contain NaNs (dropped).
    mode  : "symmetric" (default) | "body_aware"

    Returns a DataFrame indexed like the cleaned close with float columns
    ``open, high, low, close`` where, for every bar:
        ``low <= min(open, close) <= max(open, close) <= high``  (contains body)
        ``high - low >= ATR``-ish  and  ``high - low >= |Δclose|``  (never understates)
    ``open`` is the prior close (first bar opens at itself), mirroring the chart's
    existing convention in ``scripts/build_chart_data._bars_ohlc``.
    """
    close = close.astype(float).dropna()
    if not close.index.is_monotonic_increasing:    # open=shift(1) assumes time order
        close = close.sort_index()
    if close.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    atr = atr_proxy(close, length, range_mult, floor_pct)
    open_ = close.shift(1)
    open_.iloc[0] = close.iloc[0]            # first bar opens at itself

    if mode == "body_aware":
        up = (close >= open_)
        # fraction of the range that sits ABOVE the close. On an up bar the close is
        # near the high => little room above => small fraction (1-BODY_SKEW); mirror
        # on a down bar (close near the low => large fraction above).
        above_frac = np.where(up.to_numpy(), 1.0 - BODY_SKEW, BODY_SKEW)
        above_frac = pd.Series(above_frac, index=close.index)
        high = close + atr * above_frac
        low = close - atr * (1.0 - above_frac)
    elif mode == "symmetric":
        half = atr / 2.0
        high = close + half
        low = close - half
    else:
        raise ValueError(f"unknown mode {mode!r} (expected 'symmetric'|'body_aware')")

    # Clamp so the candle always contains the open->close body. This also makes
    # the reconstruction strictly conservative w.r.t. the realised close-to-close
    # move (the body can never poke outside the wick).
    body_hi = pd.concat([open_, close], axis=1).max(axis=1)
    body_lo = pd.concat([open_, close], axis=1).min(axis=1)
    high = pd.concat([high, body_hi], axis=1).max(axis=1)
    low = pd.concat([low, body_lo], axis=1).min(axis=1)

    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})


def has_real_ohlc(df: pd.DataFrame, min_distinct: float = 0.20) -> bool:
    """True iff ``df`` carries genuine intraday high/low (candle-capable).

    Guards against two fakes: (a) missing high/low columns; (b) high/low columns
    that just echo close (some stores pad them) — detected when fewer than
    ``min_distinct`` of bars have ``high>close`` or ``low<close``.
    """
    if df is None or "high" not in df.columns or "low" not in df.columns:
        return False
    if "close" not in df.columns:
        return False
    sub = df[["high", "low", "close"]].dropna()
    if sub.empty:
        return False
    moved = ((sub["high"] > sub["close"]) | (sub["low"] < sub["close"])).mean()
    return bool(moved >= min_distinct)


def is_close_only(df: pd.DataFrame) -> bool:
    """Convenience inverse of :func:`has_real_ohlc` for build-step branching."""
    return not has_real_ohlc(df)
