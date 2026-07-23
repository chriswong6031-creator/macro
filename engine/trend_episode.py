"""Frozen trend-episode detector — display-tier context infrastructure.

Reimplements, verbatim, the regime-episode definition frozen in
`research/C1_COMMODITY_SECTOR_PREREG.md` and `scripts/c1_commodity_sector_phase0.py`
(SLOPE_WIN=63, Z_WIN=252, Z_MINP=200, HYST=0.5, MIN_DUR=20):

  slope_z of log(close) over a 63d OLS window, standardized over 252d, run through a
  +/-0.5 hysteresis dead-band state machine, with a >=20 trading-day min-duration
  debounce. A *confirmed* BULL episode = the current state is +1 and has held >= 20d.

Kept side-effect-free and independent of the research script (which instantiates a
`TrialLedger` at import time, so it is NOT build-safe) so the live site build can
import it. This is DETECTION / TAGGING infrastructure and ships **display-tier only**
(house epistemics: context/detection ships freely; it is NOT a scored signal, a gate,
or a size input, and an LLM may not escalate it). Any change to these constants must
stay in lockstep with the C1 pre-registration, or the displayed context stops matching
the study it cites.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Frozen — must match scripts/c1_commodity_sector_phase0.py
SLOPE_WIN = 63    # trend slope window (~13wk)
Z_WIN = 252       # standardization window
Z_MINP = 200      # min periods for the z-window
HYST = 0.5        # +/- dead-band
MIN_DUR = 20      # min-duration debounce (trading days, ~4wk)


def slope_z(logp: pd.Series, slope_win: int = SLOPE_WIN, z_win: int = Z_WIN,
            z_minp: int = Z_MINP) -> pd.Series:
    """Rolling OLS slope of ``logp`` on a 0..W-1 index, then a rolling z over ``z_win``."""
    x = np.arange(slope_win, dtype=float)
    x -= x.mean()
    denom = float((x * x).sum())

    def _slope(win):
        y = win - win.mean()
        return float((x * y).sum() / denom)

    slope = logp.rolling(slope_win).apply(_slope, raw=True)
    mu = slope.rolling(z_win, min_periods=z_minp).mean()
    sd = slope.rolling(z_win, min_periods=z_minp).std(ddof=0)
    return (slope - mu) / sd.replace(0.0, np.nan)


def regime_state(sz: pd.Series, hyst: float = HYST) -> pd.Series:
    """Hysteresis dead-band state machine: +1 bull / -1 bear / 0 neutral.

    Enter bull when sz>+hyst; leave bull only when sz<-hyst (then enter bear); symmetric.
    """
    state = pd.Series(0, index=sz.index, dtype=int)
    cur = 0
    for i, v in enumerate(sz.values):
        if np.isnan(v):
            state.iloc[i] = cur
            continue
        if cur == 1:
            cur = -1 if v < -hyst else 1
        elif cur == -1:
            cur = 1 if v > hyst else -1
        else:  # neutral (only before the first threshold cross)
            if v > hyst:
                cur = 1
            elif v < -hyst:
                cur = -1
        state.iloc[i] = cur
    return state


def current_episode(close, min_dur: int = MIN_DUR) -> dict | None:
    """Current trend-episode state for a daily close series.

    Returns ``{state, run_len, confirmed, sz_now, as_of}`` where ``state`` is one of
    'bull'/'bear'/'neutral', ``run_len`` is the number of consecutive days in the
    current state, and ``confirmed`` is ``run_len >= min_dur`` (i.e. the run has held
    long enough to count as a confirmed episode under the C1 debounce). Returns ``None``
    if there is insufficient history to standardize the slope.
    """
    close = pd.Series(close).dropna().astype(float)
    close = close[close > 0]  # guard log of stale zero/negative marks
    if len(close) < Z_WIN + SLOPE_WIN:
        return None
    sz = slope_z(np.log(close))
    st = regime_state(sz)
    vals = st.values
    last = int(vals[-1])
    run = 1
    for k in range(len(vals) - 2, -1, -1):
        if int(vals[k]) == last:
            run += 1
        else:
            break
    sz_last = sz.iloc[-1]
    return {
        "state": {1: "bull", -1: "bear", 0: "neutral"}[last],
        "run_len": int(run),
        "confirmed": bool(run >= min_dur),
        "sz_now": None if pd.isna(sz_last) else round(float(sz_last), 2),
        "as_of": str(close.index[-1])[:10],
    }
