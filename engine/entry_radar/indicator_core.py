"""engine/entry_radar/indicator_core.py — Radar's ONE pinned indicator family.

BOUNDARY (contract §2), stated before anything else
---------------------------------------------------
``engine/washout_turn.py`` is the existing per-name **WEEKLY** washout-turn watch
organ; ``engine/mtf_upturn.py`` is the TS-R3 per-stock multi-timeframe upturn
organ (K-of-N legs, registered expected-NULL).  Both are ADJACENT display organs
at a different GRAIN (weekly / multi-week position and motion) inside a different
PRODUCT (watch vocabulary, not an episode ledger).  Radar's C1–C4 live at
1D-live / intraday motion grain and produce episodes, candidates and provenance.
Name similarity is not identity.  Neither module is imported here, neither is
modified by this lane, and the house precedent for stating the distinction in the
docstring is ``engine/washout_turn.py:1-5``.

WHY THIS MODULE EXISTS (contract §4, indicator-core law)
--------------------------------------------------------
The repo carries **two incompatible RSI families**: ``engine/canon.py``'s
SMA-seeded RMA (== Pine ``ta.rsi``, the cross-repo golden oracle) and
``engine/technicals.py``'s bare ``ewm`` variant.  They differ exactly in the
early warm-up — which is where crosses flip.  Nine StochRSI sites and five
RSI-MACD sites exist in this repo with divergent NaN policies and ``adjust``
flags.  So Radar pins **one named family, in one module**: everything a Radar
detector computes comes through here, and this module's only oscillator source is
``engine.canon`` (family R-A).

``engine.technicals`` is never imported (guard: the AST fence in
``tests/test_entry_radar_w2_guards.py`` and ``tests/test_entry_radar_w3_guards.py``).

TRANSITIVE-IMPORT NOTE, recorded rather than hidden: ``engine.stock_technicals``
— whose ``true_range``/``atr`` the §4(c) ATR law names — itself imports
``engine.technicals`` at module scope for an unrelated helper.  Importing the ATR
pair therefore LOADS that module into ``sys.modules``; it does not make Radar
compute with it.  No Radar detector calls ``engine.technicals.rsi``, the direct
import fence is intact, and ``tests/test_entry_radar_w3_guards.py`` pins both
halves (no direct import anywhere; Radar's ATR is byte-equal to
``stock_technicals.atr``, so nothing here is a second ATR implementation).

WHAT IS PINNED (and what a change to it costs)
-----------------------------------------------
``INDICATOR_CORE`` below is the constants block every detector spec embeds by
value, so changing a constant here moves every dependent ``spec_hash`` —
which is the point: a detector whose math moved silently is a detector whose
past results are no longer attributable to it.

ATR LAW (contract §18 A5.0, §4(c))
-----------------------------------
True-range Wilder ATR(14) on ACTUAL daily OHLC — ``engine/entry_signal.py``'s
``_atr_pct`` is never used anywhere in Radar (it is a close-only mean-absolute
-return misnomer, not ATR).  The value a Radar detector may use during session D
is ``atr14_prior_confirmed``, which EXCLUDES session D's own bar: a live detector
normalising by an ATR that already contains today's eventual high and low is
reading its own future.  The shift is the discipline
``engine/personality_relief_hazard.py:210-220`` already applies.

NO STATE, NO IO.  Pure functions over passed-in series.  Nothing here opens a
file, reads an env var, touches the network, or holds a cache.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from engine import canon
from engine.stock_technicals import atr as _wilder_atr
from engine.stock_technicals import true_range as _true_range

#: Wilder ATR window.  Named here (not inlined) because it rides every spec hash.
ATR_LEN = 14

#: The PIT shift, in confirmed daily bars.  ONE — the ATR available while session
#: D is still open is the one that closed at D−1.
ATR_PIT_SHIFT = 1

#: Oversold threshold shared by C1's arm condition and C4's ``recent_os`` context.
#: Radar reads canon's own constant rather than restating 20, so a canon-side
#: change cannot leave Radar quietly disagreeing with the family it pinned.
OVERSOLD = canon.OS

#: FROZEN, and embedded BY VALUE in every detector spec block.  A dict rather than
#: loose constants so a spec can carry the whole family in one key and a reviewer
#: can see at a glance which family produced a result.
INDICATOR_CORE: dict[str, Any] = {
    "family": "R-A canon (SMA-seeded RMA == Pine ta.rsi)",
    "module": "engine.canon",
    "rsi_len": canon.RSI_LEN,
    "stoch_len": canon.STOCH_LEN,
    "smooth_k": canon.SMOOTH_K,
    "smooth_d": canon.SMOOTH_D,
    "oversold": canon.OS,
    "macd_fast": canon.FAST_LEN,
    "macd_slow": canon.BASE_LEN,
    "macd_signal": canon.SIG_LEN,
    "macd_input": "RSI, never price (EMA(RSI,14) - EMA(RSI,60); signal EMA(.,5))",
    "ema_adjust": "adjust=False",
    "rma_seed": "sma_seeded",
    "atr": "true-range Wilder ATR(14) on daily OHLC (engine.stock_technicals form)",
    "atr_pit_shift_bars": ATR_PIT_SHIFT,
    "atr_forbidden": "engine.entry_signal._atr_pct is not ATR and is never used",
}


def _series(values: Any) -> pd.Series:
    """Coerce to a float Series without inventing an index."""
    if isinstance(values, pd.Series):
        return pd.to_numeric(values, errors="coerce").astype(float)
    return pd.Series(pd.to_numeric(pd.Series(list(values)), errors="coerce")).astype(float)


def rsi(close: Any) -> pd.Series:
    """Canonical Wilder RSI(14) — ``canon.rsi``, no second implementation."""
    return canon.rsi(_series(close), canon.RSI_LEN)


def stoch_rsi_kd(close: Any) -> tuple[pd.Series, pd.Series]:
    """Canonical StochRSI ``(%K, %D)`` — ``canon.stoch_rsi_kd`` (14/14/3/3)."""
    return canon.stoch_rsi_kd(_series(close))


def rsi_macd(close: Any) -> tuple[pd.Series, pd.Series]:
    """Canonical RSI-MACD ``(line, signal)`` — ``canon.rsi_macd`` (14/60/5)."""
    return canon.rsi_macd(_series(close))


def rsi_macd_hist(close: Any) -> pd.Series:
    """The RSI-MACD HISTOGRAM: ``line − signal``.

    Spelled out here because "hist" is ambiguous across this repo's five RSI-MACD
    sites.  Radar's histogram is always ``line − signal`` on the RSI-MACD (never
    a price MACD, never the raw line), which is the same object Terminal's
    ``rising2`` leg reads (contract §3.1).
    """
    line, signal = rsi_macd(close)
    return line - signal


def crossover(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """Canonical strict bullish cross — ``canon.crossover`` (``>`` now, ``<=`` prior)."""
    return canon.crossover(fast, slow)


def true_range(high: Any, low: Any, close: Any) -> pd.Series:
    """True range on daily OHLC — ``engine.stock_technicals.true_range``."""
    return _true_range(_series(high), _series(low), _series(close))


def atr14(high: Any, low: Any, close: Any) -> pd.Series:
    """Wilder ATR(14) on TRUE RANGE — ``engine.stock_technicals.atr``.

    Includes the bar it is indexed on.  A LIVE detector must not use this value
    for the session it is observing; see :func:`atr14_prior_confirmed`.
    """
    return _wilder_atr(_series(high), _series(low), _series(close), ATR_LEN)


def atr14_prior_confirmed(high: Any, low: Any, close: Any) -> pd.Series:
    """ATR(14) as of the PRIOR confirmed session — ``atr14`` shifted by one bar.

    The value at index D is the ATR that closed at D−1, so a detector evaluating
    session D while it is still open cannot normalise by today's eventual range.
    """
    return atr14(high, low, close).shift(ATR_PIT_SHIFT)


def last_finite(series: pd.Series | None) -> float | None:
    """Latest finite value, or None.  ``None`` means *unavailable*, never zero."""
    if series is None or len(series) == 0:
        return None
    value = series.iloc[-1]
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(value) or np.isinf(value)) else value


def finite_tail(series: pd.Series | None, n: int) -> tuple[float, ...] | None:
    """The last ``n`` values, or None if any of them is missing/non-finite.

    A predicate needing three points must be UNAVAILABLE — not False — while the
    indicator is still inside its own mathematical warm-up (contract §18 A5.0
    null law).  Returning None rather than a padded tuple is what makes that
    distinction survive into the reading.
    """
    if series is None or len(series) < n:
        return None
    tail = series.iloc[-n:].to_numpy(dtype=float)
    if not np.isfinite(tail).all():
        return None
    return tuple(float(v) for v in tail)
