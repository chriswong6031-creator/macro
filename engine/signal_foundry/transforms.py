"""engine.signal_foundry.transforms — causal-only transform vocabulary.

All transforms are PAST-ONLY (no center=True, ema adjust=False).  Rolling windows
are right-aligned so signal known at close t uses only data up to t.

TRANSFORMS registry: {name: (fn, arity, param_schema)}
  arity: 1 = univariate (Series → Series)
         2 = bivariate (Series, Series → Series)

apply_pipeline(series_or_pair, pipeline) executes a sequence of transform steps
defined as [[name, {params}], ...].  For binary transforms (ratio, spread,
rolling_corr), series_or_pair must be a 2-tuple.

Property tested for NO-LOOKAHEAD: mutating future values of the input must
not change past output values.  Each rolling call uses:
  - rolling(window, min_periods=...).xxx()   — never center=True
  - ema(span=..., adjust=False)
  - NaN-safe: min_periods floor propagates NaN correctly
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Primitive transforms (all Series → Series, past-only)
# ---------------------------------------------------------------------------

def _zscore(s: pd.Series, window: int = 252) -> pd.Series:
    """Rolling z-score over `window` periods.  NaN if std is zero or < min_periods."""
    mn = s.rolling(window, min_periods=max(2, window // 4)).mean()
    sd = s.rolling(window, min_periods=max(2, window // 4)).std(ddof=1)
    z = (s - mn) / sd
    return z.where(sd > 0, other=np.nan)


def _pctile_rank(s: pd.Series, window: int = 252) -> pd.Series:
    """Rolling percentile rank [0,1] over `window` periods."""
    def _rank_pct(x: np.ndarray) -> float:
        v = x[-1]
        if np.isnan(v):
            return np.nan
        valid = x[~np.isnan(x)]
        if len(valid) < 2:
            return np.nan
        return float(np.sum(valid <= v) / len(valid))

    return s.rolling(window, min_periods=max(2, window // 4)).apply(
        _rank_pct, raw=True
    )


def _diff(s: pd.Series, n: int = 1) -> pd.Series:
    """Period difference s_t - s_{t-n}."""
    return s.diff(n)


def _pct_change(s: pd.Series, n: int = 1) -> pd.Series:
    """Percentage change over n periods."""
    return s.pct_change(n)


def _sma(s: pd.Series, window: int = 20) -> pd.Series:
    """Simple moving average over `window` periods."""
    return s.rolling(window, min_periods=max(1, window // 4)).mean()


def _ema(s: pd.Series, span: int = 20) -> pd.Series:
    """Exponential moving average, adjust=False (past-only, no future weights)."""
    return s.ewm(span=span, adjust=False).mean()


def _lag(s: pd.Series, n: int = 1) -> pd.Series:
    """Shift series back by n periods (n >= 0; n=0 is identity)."""
    if n < 0:
        raise ValueError(f"lag(n={n}) must be >= 0 (future lag is not causal)")
    return s.shift(n)


def _sign(s: pd.Series) -> pd.Series:
    """Element-wise sign: +1 / 0 / -1."""
    return np.sign(s)


def _clip(s: pd.Series, lo: float = -3.0, hi: float = 3.0) -> pd.Series:
    """Clip values to [lo, hi]."""
    return s.clip(lower=lo, upper=hi)


def _rolling_vol(s: pd.Series, window: int = 21) -> pd.Series:
    """Rolling standard deviation (realized vol proxy)."""
    return s.rolling(window, min_periods=max(2, window // 4)).std(ddof=1)


# ---------------------------------------------------------------------------
# Binary transforms (Series, Series → Series)
# ---------------------------------------------------------------------------

def _rolling_corr(s1: pd.Series, s2: pd.Series, window: int = 63) -> pd.Series:
    """Rolling Pearson correlation over `window` periods."""
    return s1.rolling(window, min_periods=max(2, window // 4)).corr(s2)


def _ratio(s1: pd.Series, s2: pd.Series) -> pd.Series:
    """Element-wise ratio s1 / s2.  NaN where s2 == 0."""
    return s1 / s2.replace(0, np.nan)


def _spread(s1: pd.Series, s2: pd.Series) -> pd.Series:
    """Element-wise spread s1 - s2."""
    return s1 - s2


def _drawdown(s: pd.Series, window: int = 126) -> pd.Series:
    """Rolling drawdown from rolling peak: (s - rolling_max) / rolling_max.

    Negative values indicate drawdown depth.  Uses right-aligned window
    (no future information).
    """
    rolling_max = s.rolling(window, min_periods=max(1, window // 4)).max()
    # Protect against zero-price inputs
    safe_max = rolling_max.replace(0, np.nan)
    return (s - rolling_max) / safe_max.abs()


# ---------------------------------------------------------------------------
# TRANSFORMS registry
# ---------------------------------------------------------------------------
# Each entry: (function, arity, {param: default_or_None})
# arity 1 = univariate; 2 = bivariate

TRANSFORMS: dict[str, tuple] = {
    "zscore":        (_zscore,       1, {"window": 252}),
    "pctile_rank":   (_pctile_rank,  1, {"window": 252}),
    "diff":          (_diff,         1, {"n": 1}),
    "pct_change":    (_pct_change,   1, {"n": 1}),
    "sma":           (_sma,          1, {"window": 20}),
    "ema":           (_ema,          1, {"span": 20}),
    "lag":           (_lag,          1, {"n": 1}),
    "sign":          (_sign,         1, {}),
    "clip":          (_clip,         1, {"lo": -3.0, "hi": 3.0}),
    "rolling_vol":   (_rolling_vol,  1, {"window": 21}),
    "rolling_corr":  (_rolling_corr, 2, {"window": 63}),
    "ratio":         (_ratio,        2, {}),
    "spread":        (_spread,       2, {}),
    "drawdown":      (_drawdown,     1, {"window": 126}),
}


def _call_transform(name: str, inputs: Any, params: dict) -> pd.Series:
    """Dispatch one transform step by name."""
    if name not in TRANSFORMS:
        raise ValueError(
            f"Unknown transform '{name}'. Allowed: {sorted(TRANSFORMS)}"
        )
    fn, arity, defaults = TRANSFORMS[name]
    merged = {**defaults, **params}
    if arity == 1:
        if isinstance(inputs, (tuple, list)):
            s = inputs[0]
        else:
            s = inputs
        if not isinstance(s, pd.Series):
            s = pd.Series(s)
        return fn(s, **merged)
    elif arity == 2:
        if not isinstance(inputs, (tuple, list)) or len(inputs) < 2:
            raise ValueError(
                f"Transform '{name}' is binary (arity=2) but received a "
                "single series.  Pass a 2-tuple (s1, s2)."
            )
        s1, s2 = inputs[0], inputs[1]
        if not isinstance(s1, pd.Series):
            s1 = pd.Series(s1)
        if not isinstance(s2, pd.Series):
            s2 = pd.Series(s2)
        return fn(s1, s2, **merged)
    else:
        raise ValueError(f"Unsupported arity {arity} for transform '{name}'")


def apply_pipeline(
    series_or_pair: "pd.Series | tuple[pd.Series, pd.Series]",
    pipeline: list,
) -> pd.Series:
    """Execute a sequence of transform steps from a pipeline spec.

    pipeline is a list of [name, {params}] steps.

    For binary transforms (ratio, spread, rolling_corr), the current value
    of series_or_pair must be a 2-tuple; the output of that step becomes a
    scalar Series and subsequent steps are univariate.

    Returns the final Series after all steps.
    """
    current = series_or_pair
    for i, step in enumerate(pipeline):
        if isinstance(step, (list, tuple)):
            name = step[0]
            params = step[1] if len(step) > 1 else {}
        else:
            raise ValueError(
                f"pipeline[{i}] must be a list [name, params_dict], got {type(step)}"
            )
        if not isinstance(params, dict):
            raise ValueError(
                f"pipeline[{i}] params must be a dict, got {type(params)}"
            )
        current = _call_transform(name, current, params)
    # Ensure output is a pd.Series
    if not isinstance(current, pd.Series):
        current = pd.Series(current)
    return current
