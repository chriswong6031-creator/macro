"""W8 ignition-state constructions — the two surviving stand-in sensors, ported once.

WHAT THIS IS
------------
`research/prophet_us_audit/ignition_standins.py` measured four ignition stand-ins on the
2014-2026 OHLCV panel (charter: `research/PROPHET_US_IGNITION_LAYER_W8_BY_FABLE.md`, PR
#4564). Two survived with signal:

* **S-COIL** — range compression released through the prior 21d high, in an uptrend. NULL at
  H=10/21; **+0.98pp [+0.42, +1.55] at H=63** (matched-set delta vs gate-matched controls,
  n=24,989).
* **S-THRUST-LAG**, one arm only — a coiled member of a **thrusting** theme against coiled
  names in **non-thrusting** themes: **+1.31 / +2.04 / +4.67pp** at H=10/21/63 (n=228, all
  three CIs exclude zero). The other arm (laggard vs already-moved *within* the thrusting
  theme) was null at every horizon: theme context pays, the laggard-vs-leader choice does not.

This module holds those detectors so a consumer can record the same STATE the study measured
without re-deriving it. `engine/prophet_doors.py` is the first consumer (prereg §10 addendum).

THE RESEARCH INSTRUMENT IS FROZEN
---------------------------------
`ignition_standins.py` is a published, frozen artifact; it is NOT edited to import this module,
so the two are independent implementations of one construction. That is a fork risk, and it is
answered by a test rather than by a promise: `tests/test_ignition_features.py::TestPortFidelity`
imports the frozen instrument read-only and asserts these functions are **elementwise identical**
to it on synthetic panels. If either side drifts, that test reds.

Every constant below is copied from the frozen instrument at the values it measured on. They
are MEASUREMENT constants, not tunables — changing one makes a recorded feature incomparable
with the #4564 numbers above, which is a prereg amendment, not a refactor.

NO AUTHORITY
------------
Detectors only: no score, no rank, no gate, no size, no ordering, no surface. Nothing here
originates a signal (Neural Web A7). The S-COIL compressed/"armed" state in particular may
never be surfaced or graded standalone — that is the arming variant banned by ESX §9 / DT-R5,
and the charter's licence for S-COIL is that it grades the RELEASE bar only. A consumer that
records the armed state (as the doors do) keeps it in a no-authority shadow ledger.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# S-COIL constants — frozen at ignition_standins.py's values
# --------------------------------------------------------------------------- #
ATR_WIN = 21          # trailing ATR window
PCT_WIN = 252         # own-history window for the ATR percentile
PCT_MAX = 0.25        # compression := ATR percentile < p25
MA_WIN = 50           # uptrend reference
MA_SLOPE = 10         # 50dMA "rising" lookback
COMP_LOOKBACK = 21    # window in which compressed sessions are counted
COMP_MIN = 10         # >= 10 compressed sessions = the S-COIL "armed" run

# --------------------------------------------------------------------------- #
# S-THRUST-LAG constants — frozen at ignition_standins.py's values
# --------------------------------------------------------------------------- #
HIGH20 = 20                 # member "above its own 20d high"
THRUST_LO = 0.30            # thrust := member fraction crosses from < 0.30 ...
THRUST_HI = 0.50            # ... to > 0.50 ...
THRUST_WIN = 5              # ... within 5 sessions
THRUST_MIN_MEMBERS = 6      # a theme needs this many covered members to be readable

#: Sessions of high/low/close a *complete* coil read needs, ending on the read bar.
#: Derivation: 1 row is eaten by ``close.shift(1)`` inside the true range, ``ATR_WIN - 1`` by
#: the ATR mean, ``PCT_WIN - 1`` by the percentile rank, and ``COMP_LOOKBACK - 1`` by the
#: trailing compressed-bar count -> ``1 + 20 + 251 + 20 + 1 = 293``. The 50dMA legs
#: (``MA_WIN + MA_SLOPE = 60``) are strictly shorter and never bind.
COIL_MIN_SESSIONS = ATR_WIN + PCT_WIN + COMP_LOOKBACK - 1

#: Sessions of close/high a thrust read needs, ending on the read bar.
#: Rule used: EVERY bar any leg touches must be warm. ``above_20d_high`` is first valid at row
#: ``HIGH20`` (rolling max plus ``shift(1)``). The read bar ``L`` needs its ``lo_recent`` over
#: ``[L-THRUST_WIN, L-1]``, and the de-bounce additionally consults ``fired`` at ``L-1``, whose
#: own ``lo_recent`` reaches ``L-1-THRUST_WIN``. Warm-everything gives
#: ``L >= HIGH20 + THRUST_WIN + 1`` -> 27 rows.
#: Why the rule rather than a tightest bound: ``above_20d_high`` returns BOOLEANS, so a
#: pre-warmup bar reads ``False``, the fraction there is a fabricated ``0.0``, and that zero is
#: below ``THRUST_LO`` — i.e. cold bars do not announce themselves as NaN, they impersonate a
#: quiet theme. A tighter floor would be defensible only after a case analysis of which
#: fabricated bar can flip which leg; a floor that needs no such analysis is the safer artifact,
#: and at a 3,163-session panel it costs nothing. (Measured: truncation changes the fraction at
#: or below 26 rows in 258 of 400 random panels; the de-bounce leg could not be exercised
#: randomly — thrust fired on the read bar in 0 of 400 — so the tighter bound stays unverified
#: rather than assumed.)
THRUST_MIN_SESSIONS = HIGH20 + THRUST_WIN + 2


def true_range(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """Wilder true range. Port of ``ignition_standins.true_range``."""
    pc = close.shift(1)
    a = (high - low).to_numpy()
    b = (high - pc).abs().to_numpy()
    c = (low - pc).abs().to_numpy()
    return pd.DataFrame(np.maximum(np.maximum(a, b), c), index=close.index, columns=close.columns)


def coil_compression(close: pd.DataFrame, high: pd.DataFrame,
                     low: pd.DataFrame) -> pd.DataFrame:
    """UPTREND coil: low ATR percentile AND price above a RISING 50dMA.

    Port of ``ignition_standins.coil_compression``, argument order included.

    Deliberately NOT a bottoming state. The bottom-radar PRIMED tier was killed as a
    directional durable-bottom gate (DO_NOT_REBUILD §2) and DURABLE_BOTTOM H2 falsified
    "calm base" arming after a washout; requiring price ABOVE a RISING 50dMA puts this state
    in the continuation regime neither verdict tested. That distinction is the sensor's whole
    licence to exist, so it is restated here rather than assumed.
    """
    atr = true_range(high, low, close).rolling(ATR_WIN).mean()
    atr_pct = atr.rolling(PCT_WIN).rank(pct=True)
    ma = close.rolling(MA_WIN).mean()
    rising = ma > ma.shift(MA_SLOPE)
    return (atr_pct < PCT_MAX) & (close > ma) & rising


def compressed_bars(compressed: pd.DataFrame) -> pd.DataFrame:
    """Compressed sessions inside the trailing ``COMP_LOOKBACK``.

    This is the left half of the frozen instrument's arming test, kept as a COUNT rather than
    reduced to its boolean: ``coil_events`` arms on ``compressed.rolling(21).sum() >= 10``, so
    a recorded count reconstructs that state (``count >= COMP_MIN``) while also carrying how
    far from the threshold the name sat. A recorded boolean could not be un-thresholded later.
    """
    return compressed.rolling(COMP_LOOKBACK).sum()


def above_20d_high(close: pd.DataFrame, high: pd.DataFrame) -> pd.DataFrame:
    """Port of ``ignition_standins.above_20d_high``."""
    return close > high.rolling(HIGH20).max().shift(1)


def thrust_fired(frac: pd.Series) -> pd.Series:
    """Thrust EVENT bars for one theme's above-20d-high member fraction.

    Port of the ``thrust_lag_events`` inner block: the fraction is above ``THRUST_HI`` now and
    was below ``THRUST_LO`` at some point within the prior ``THRUST_WIN`` sessions, de-bounced
    to the FIRST bar of a run.

    The de-bounce is kept deliberately. It makes "thrusting" an event-day reading rather than
    a standing condition — which is exactly the population the #4564 numbers were measured on
    (candidates were the theme's coiled members ON the thrust bar). Dropping it would record a
    superset the study never graded, and the forward comparison would not be a comparison.
    """
    lo_recent = (frac < THRUST_LO).rolling(THRUST_WIN).max().shift(1)
    fired = (frac > THRUST_HI) & (lo_recent == 1.0)
    return fired & ~(fired.shift(1).fillna(False).astype(bool))
