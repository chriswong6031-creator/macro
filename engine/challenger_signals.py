"""engine/challenger_signals.py — Challenger family signal sandbox.

All signals here are challenger_only=True: they participate in a tournament
evaluation and are excluded from the main combination search. None carry
authority; all are display-tier / research only.

Implemented signals
-------------------
  A) KST daily         — kst_cross_up, kst_cross_dn
  B) TSI (Blau)        — tsi_cross_up, tsi_cross_dn
  C) Coppock daily     — coppock_turn_up
  D) Ultimate Osc 7/14/28 — uo_os_exit, uo_ob_exit
  E) Fisher Transform  — fisher_cross_up, fisher_cross_dn
  F) QQE               — qqe_cross_up, qqe_cross_dn
  G) Schaff Trend Cycle — stc_turn_up, stc_turn_dn
  H) Fair Value Gap    — fvg_bull_form, fvg_bear_form, fvg_bull_fill, fvg_bear_fill

CAUSALITY LAW: all computations use only completed bars; no look-ahead.
Rolling ops use trailing windows only (center=False, no future windows).
Warm-up bars emit 0 (not NaN) for events; states also emit 0 during warm-up.

Data contract: DataFrame with DatetimeIndex, columns: close / high / low / volume.
There is NO 'open' column — never reference it.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cross helpers (NaN-safe, warm-up-safe)
# ---------------------------------------------------------------------------

def _cross_above(a: pd.Series, b: pd.Series | float) -> pd.Series:
    """1.0 on bars where *a* first moves strictly above *b* (prior bar <= b)."""
    b_prev = b.shift(1) if isinstance(b, pd.Series) else b
    cond = (a > b) & (a.shift(1) <= b_prev)
    return cond.fillna(False).astype(float)


def _cross_below(a: pd.Series, b: pd.Series | float) -> pd.Series:
    """1.0 on bars where *a* first moves strictly below *b* (prior bar >= b)."""
    b_prev = b.shift(1) if isinstance(b, pd.Series) else b
    cond = (a < b) & (a.shift(1) >= b_prev)
    return cond.fillna(False).astype(float)


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def _roc(close: pd.Series, n: int) -> pd.Series:
    """Rate of change: (close / close[n periods ago] - 1) * 100."""
    return (close / close.shift(n) - 1) * 100


def _wma(s: pd.Series, n: int) -> pd.Series:
    """Weighted moving average with linearly increasing weights 1..n."""
    weights = np.arange(1, n + 1, dtype=float)
    weights /= weights.sum()

    def _apply(x: np.ndarray) -> float:
        return float(np.dot(x, weights))

    return s.rolling(n, min_periods=n).apply(_apply, raw=True)


# ---------------------------------------------------------------------------
# A) KST — Know Sure Thing (Pring 1992)
# ---------------------------------------------------------------------------
# KST = 1*SMA(ROC(10),10) + 2*SMA(ROC(15),10) + 3*SMA(ROC(20),10) + 4*SMA(ROC(30),15)
# Signal = SMA(KST, 9)
# kst_cross_up: KST crosses above signal while KST < 0
# kst_cross_dn: KST crosses below signal while KST > 0

def _kst(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    kst = (
        1 * _sma(_roc(close, 10), 10)
        + 2 * _sma(_roc(close, 15), 10)
        + 3 * _sma(_roc(close, 20), 10)
        + 4 * _sma(_roc(close, 30), 15)
    )
    signal = _sma(kst, 9)
    return kst, signal


def kst_cross_up(df: pd.DataFrame) -> pd.Series:
    """Event: KST line crosses above its signal line while KST is negative."""
    close = df["close"].astype(float)
    kst, sig = _kst(close)
    fired = _cross_above(kst, sig)
    result = (fired.astype(bool) & (kst < 0)).astype(float)
    result.name = "kst_cross_up"
    return result.fillna(0.0)


def kst_cross_dn(df: pd.DataFrame) -> pd.Series:
    """Event: KST line crosses below its signal line while KST is positive."""
    close = df["close"].astype(float)
    kst, sig = _kst(close)
    fired = _cross_below(kst, sig)
    result = (fired.astype(bool) & (kst > 0)).astype(float)
    result.name = "kst_cross_dn"
    return result.fillna(0.0)


# ---------------------------------------------------------------------------
# B) TSI — True Strength Index (Blau)
# ---------------------------------------------------------------------------
# Δclose = close.diff()
# TSI = 100 * EMA(EMA(Δclose, 25), 13) / EMA(EMA(|Δclose|, 25), 13)
# Signal = EMA(TSI, 13)
# tsi_cross_up: TSI crosses above signal while TSI < 0
# tsi_cross_dn: TSI crosses below signal while TSI > 0

def _tsi(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    delta = close.diff()
    num = _ema(_ema(delta, 25), 13)
    den = _ema(_ema(delta.abs(), 25), 13)
    tsi = 100.0 * num / den.replace(0, np.nan)
    signal = _ema(tsi, 13)
    return tsi, signal


def tsi_cross_up(df: pd.DataFrame) -> pd.Series:
    """Event: TSI crosses above its signal line while TSI is below zero."""
    close = df["close"].astype(float)
    tsi, sig = _tsi(close)
    fired = _cross_above(tsi, sig)
    result = (fired.astype(bool) & (tsi < 0)).astype(float)
    result.name = "tsi_cross_up"
    return result.fillna(0.0)


def tsi_cross_dn(df: pd.DataFrame) -> pd.Series:
    """Event: TSI crosses below its signal line while TSI is above zero."""
    close = df["close"].astype(float)
    tsi, sig = _tsi(close)
    fired = _cross_below(tsi, sig)
    result = (fired.astype(bool) & (tsi > 0)).astype(float)
    result.name = "tsi_cross_dn"
    return result.fillna(0.0)


# ---------------------------------------------------------------------------
# C) Coppock Curve — daily adaptation
# ---------------------------------------------------------------------------
# Canonical monthly: WMA(ROC(14m) + ROC(11m), 10m)
# Daily frozen adaptation: WMA(ROC(294) + ROC(231), 210)
#   294 ≈ 14*21, 231 ≈ 11*21, 210 ≈ 10*21 trading days
# coppock_turn_up: Coppock < 0 AND turns up after >= 5 declining bars
#   (first bar where value > prior value, following a run of >= 5 bars of decline)

_COPP_ROC1 = 294
_COPP_ROC2 = 231
_COPP_WMA = 210
_COPP_MIN_DECLINE = 5


def _coppock(close: pd.Series) -> pd.Series:
    return _wma(_roc(close, _COPP_ROC1) + _roc(close, _COPP_ROC2), _COPP_WMA)


def coppock_turn_up(df: pd.DataFrame) -> pd.Series:
    """Event: Coppock curve is negative and turns up after >= 5 consecutive declining bars.

    Only the FIRST bar that rises after the prolonged decline counts (one event per trough).
    """
    close = df["close"].astype(float)
    copp = _coppock(close)

    vals = copp.to_numpy(dtype=float, na_value=np.nan)
    n = len(vals)
    out = np.zeros(n, dtype=float)

    decline_count = 0  # consecutive bars where copp[i] < copp[i-1]
    for i in range(1, n):
        if np.isnan(vals[i]) or np.isnan(vals[i - 1]):
            decline_count = 0
            continue
        if vals[i] < vals[i - 1]:
            decline_count += 1
        elif vals[i] > vals[i - 1]:
            # turning up
            if decline_count >= _COPP_MIN_DECLINE and vals[i] < 0:
                out[i] = 1.0
            decline_count = 0
        else:
            # flat — do not reset decline count but do not increment
            pass

    result = pd.Series(out, index=df.index, name="coppock_turn_up")
    return result


# ---------------------------------------------------------------------------
# D) Ultimate Oscillator (Williams) 7/14/28
# ---------------------------------------------------------------------------
# BP = close - min(low, prev_close)
# TR = max(high, prev_close) - min(low, prev_close)
# avg_n = sum(BP, n) / sum(TR, n)
# UO = 100 * (4*avg7 + 2*avg14 + avg28) / 7
# uo_os_exit: UO crosses above 30 from below (oversold exit)
# uo_ob_exit: UO crosses below 70 from above (overbought exit)

def _uo(df: pd.DataFrame, p1: int = 7, p2: int = 14, p3: int = 28) -> pd.Series:
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    prev_close = close.shift(1)
    bp = close - pd.concat([low, prev_close], axis=1).min(axis=1)
    tr = (
        pd.concat([high, prev_close], axis=1).max(axis=1)
        - pd.concat([low, prev_close], axis=1).min(axis=1)
    )
    avg1 = bp.rolling(p1, min_periods=p1).sum() / tr.rolling(p1, min_periods=p1).sum()
    avg2 = bp.rolling(p2, min_periods=p2).sum() / tr.rolling(p2, min_periods=p2).sum()
    avg3 = bp.rolling(p3, min_periods=p3).sum() / tr.rolling(p3, min_periods=p3).sum()
    uo = 100.0 * (4 * avg1 + 2 * avg2 + avg3) / 7.0
    return uo


def uo_os_exit(df: pd.DataFrame, p1: int = 7, p2: int = 14, p3: int = 28, level: float = 30.0) -> pd.Series:
    """Event: Ultimate Oscillator crosses above 30 from below (oversold exit)."""
    uo = _uo(df, p1=p1, p2=p2, p3=p3)
    result = _cross_above(uo, level)
    result.name = "uo_os_exit"
    return result.fillna(0.0)


def uo_ob_exit(df: pd.DataFrame, p1: int = 7, p2: int = 14, p3: int = 28, level: float = 70.0) -> pd.Series:
    """Event: Ultimate Oscillator crosses below 70 from above (overbought exit)."""
    uo = _uo(df, p1=p1, p2=p2, p3=p3)
    result = _cross_below(uo, level)
    result.name = "uo_ob_exit"
    return result.fillna(0.0)


# ---------------------------------------------------------------------------
# E) Fisher Transform (Ehlers, n=10)
# ---------------------------------------------------------------------------
# mid = (high + low) / 2
# x_t = 0.33 * 2 * ((mid - minL) / (maxL - minL) - 0.5) + 0.67 * x_{t-1}  [clamp ±0.999]
# F_t = 0.5 * ln((1+x)/(1-x)) + 0.5 * F_{t-1}  (note: spec says *0.5 again after ln — keep)
# Signal = F lagged 1 bar
# fisher_cross_up: F crosses above signal while F < -1
# fisher_cross_dn: F crosses below signal while F > 1
#
# Ehlers canonical recursive form (mesasoftware.com/papers/UsingTheFisherTransform.pdf)

_FISHER_N = 10
_FISHER_CLAMP = 0.999


def _fisher(df: pd.DataFrame, n: int = _FISHER_N) -> pd.Series:
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    length = len(high)
    mid = (high + low) / 2.0

    x = np.zeros(length)
    f = np.zeros(length)

    for i in range(length):
        if i < n - 1:
            x[i] = 0.0
            f[i] = 0.0
            continue
        lo = mid[i - n + 1: i + 1].min()
        hi = mid[i - n + 1: i + 1].max()
        span = hi - lo
        if span < 1e-10:
            norm = 0.0
        else:
            norm = 2.0 * ((mid[i] - lo) / span - 0.5)
        x_raw = 0.33 * norm + 0.67 * x[i - 1]
        x[i] = max(-_FISHER_CLAMP, min(_FISHER_CLAMP, x_raw))
        # Ehlers: Fisher = 0.5 * ln((1+x)/(1-x)) + 0.5 * F_{t-1}
        f[i] = 0.5 * np.log((1.0 + x[i]) / (1.0 - x[i])) + 0.5 * f[i - 1]

    return pd.Series(f, index=df.index)


def fisher_cross_up(df: pd.DataFrame, n: int = _FISHER_N) -> pd.Series:
    """Event: Fisher Transform crosses above its 1-bar-lag signal while Fisher < -1."""
    f = _fisher(df, n=n)
    sig = f.shift(1)
    fired = _cross_above(f, sig)
    result = (fired.astype(bool) & (f < -1.0)).astype(float)
    result.name = "fisher_cross_up"
    return result.fillna(0.0)


def fisher_cross_dn(df: pd.DataFrame, n: int = _FISHER_N) -> pd.Series:
    """Event: Fisher Transform crosses below its 1-bar-lag signal while Fisher > 1."""
    f = _fisher(df, n=n)
    sig = f.shift(1)
    fired = _cross_below(f, sig)
    result = (fired.astype(bool) & (f > 1.0)).astype(float)
    result.name = "fisher_cross_dn"
    return result.fillna(0.0)


# ---------------------------------------------------------------------------
# F) QQE — Quantitative Qualitative Estimation (RSI 14, SF 5, factor 4.236)
# ---------------------------------------------------------------------------
# RsiMa = EMA(RSI14, 5)
# AtrRsi = |ΔRsiMa|   (abs first difference of the smoothed RSI)
# MaAtr = EMA(EMA(AtrRsi, 27), 27)   (double-smoothed)
# delta = MaAtr * 4.236
# Trailing bands (numpy recurrence):
#   longband, shortband updated on each bar based on whether RsiMa crossed
# qqe_cross_up: RsiMa crosses above trailing line while RsiMa < 50
# qqe_cross_dn: RsiMa crosses below trailing line while RsiMa > 50

_QQE_RSI_N = 14
_QQE_SF = 5
_QQE_FACTOR = 4.236
_QQE_ATR_N = 27


def _rsi_series(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def _qqe_trailing(rsi_ma: np.ndarray, delta: np.ndarray,
                   first_valid: int = 0) -> np.ndarray:
    """Numpy recurrence for QQE trailing line.

    Canonical recurrence (Pine Script reference):
      When both RsiMa[i] and RsiMa[i-1] are ABOVE the prior longband,
      the longband ratchets up: longband[i] = max(rm - d, lb_prev).
      Otherwise the band resets: longband[i] = rm - d.
      Symmetrically for shortband with min().

    Warm-up bars before first_valid are left at 0; the first valid bar seeds
    lb = rm - d, sb = rm + d so that zero-initialisation does not pollute the
    recurrence.
    """
    n = len(rsi_ma)
    trail = np.zeros(n)
    longband = np.zeros(n)
    shortband = np.zeros(n)

    # Seed at first valid bar
    if first_valid < n:
        rm0 = rsi_ma[first_valid]
        d0 = delta[first_valid]
        longband[first_valid] = rm0 - d0
        shortband[first_valid] = rm0 + d0
        trail[first_valid] = rm0  # initial trail at RsiMa itself

    for i in range(first_valid + 1, n):
        d = delta[i]
        rm = rsi_ma[i]
        rm_prev = rsi_ma[i - 1]
        lb_prev = longband[i - 1]
        sb_prev = shortband[i - 1]

        # Canonical: ratchet up when BOTH current and prior RsiMa are above the prior longband
        longband[i] = max(rm - d, lb_prev) if (rm > lb_prev and rm_prev > lb_prev) else rm - d
        # Canonical: ratchet down when BOTH current and prior RsiMa are below the prior shortband
        shortband[i] = min(rm + d, sb_prev) if (rm < sb_prev and rm_prev < sb_prev) else rm + d

        # Trail switches on RsiMa crossing through bands
        prev_trail = trail[i - 1]
        if rm_prev > prev_trail and rm < prev_trail:
            trail[i] = shortband[i]
        elif rm_prev < prev_trail and rm > prev_trail:
            trail[i] = longband[i]
        else:
            trail[i] = longband[i] if rm > prev_trail else shortband[i]

    return trail


def _qqe(close: pd.Series, rsi_n: int = _QQE_RSI_N, sf: int = _QQE_SF,
         factor: float = _QQE_FACTOR, atr_n: int = _QQE_ATR_N) -> tuple[pd.Series, pd.Series]:
    rsi14 = _rsi_series(close, n=rsi_n)
    rsi_ma = _ema(rsi14, sf)
    atr_rsi = rsi_ma.diff().abs()
    ma_atr = _ema(_ema(atr_rsi, atr_n), atr_n)
    delta = ma_atr * factor
    # Find the first bar where both rsi_ma and delta are valid (non-NaN)
    valid_mask = rsi_ma.notna() & delta.notna()
    first_valid = int(valid_mask.to_numpy().argmax()) if valid_mask.any() else len(rsi_ma)
    trail_arr = _qqe_trailing(
        rsi_ma.to_numpy(dtype=float, na_value=0.0),
        delta.to_numpy(dtype=float, na_value=0.0),
        first_valid=first_valid,
    )
    trail = pd.Series(trail_arr, index=close.index)
    return rsi_ma, trail


def qqe_cross_up(df: pd.DataFrame, rsi_n: int = _QQE_RSI_N, sf: int = _QQE_SF,
                 factor: float = _QQE_FACTOR) -> pd.Series:
    """Event: QQE RsiMa crosses above trailing band while RsiMa < 50 (bullish)."""
    close = df["close"].astype(float)
    rsi_ma, trail = _qqe(close, rsi_n=rsi_n, sf=sf, factor=factor)
    fired = _cross_above(rsi_ma, trail)
    result = (fired.astype(bool) & (rsi_ma < 50.0)).astype(float)
    result.name = "qqe_cross_up"
    return result.fillna(0.0)


def qqe_cross_dn(df: pd.DataFrame, rsi_n: int = _QQE_RSI_N, sf: int = _QQE_SF,
                 factor: float = _QQE_FACTOR) -> pd.Series:
    """Event: QQE RsiMa crosses below trailing band while RsiMa > 50 (bearish)."""
    close = df["close"].astype(float)
    rsi_ma, trail = _qqe(close, rsi_n=rsi_n, sf=sf, factor=factor)
    fired = _cross_below(rsi_ma, trail)
    result = (fired.astype(bool) & (rsi_ma > 50.0)).astype(float)
    result.name = "qqe_cross_dn"
    return result.fillna(0.0)


# ---------------------------------------------------------------------------
# G) Schaff Trend Cycle (STC) — 23/50/10/3
# ---------------------------------------------------------------------------
# MACD = EMA(close, 23) - EMA(close, 50)
# Stage 1: Stochastic of MACD over 10 bars, EMA-3 smoothed → D1
# Stage 2: Stochastic of D1 over 10 bars, EMA-3 smoothed → STC
# stc_turn_up: STC crosses above 25 from below
# stc_turn_dn: STC crosses below 75 from above

_STC_FAST = 23
_STC_SLOW = 50
_STC_CYCLE = 10
_STC_SMOOTH = 3


def _stoch_of(s: pd.Series, n: int, smooth: int) -> pd.Series:
    """Stochastic of series s over n bars, EMA-smooth smoothed."""
    lo = s.rolling(n, min_periods=n).min()
    hi = s.rolling(n, min_periods=n).max()
    span = hi - lo
    raw = (s - lo) / span.replace(0, np.nan) * 100.0
    raw = raw.ffill().fillna(0.0)
    return _ema(raw, smooth)


def _stc(close: pd.Series, fast: int = _STC_FAST, slow: int = _STC_SLOW,
         cycle: int = _STC_CYCLE, smooth: int = _STC_SMOOTH) -> pd.Series:
    macd_line = close.ewm(span=fast, adjust=False, min_periods=fast).mean() - \
                close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    d1 = _stoch_of(macd_line, cycle, smooth)
    stc = _stoch_of(d1, cycle, smooth)
    return stc


def stc_turn_up(df: pd.DataFrame, fast: int = _STC_FAST, slow: int = _STC_SLOW,
                cycle: int = _STC_CYCLE, smooth: int = _STC_SMOOTH,
                level: float = 25.0) -> pd.Series:
    """Event: STC crosses above 25 from below (bullish turn)."""
    close = df["close"].astype(float)
    stc = _stc(close, fast=fast, slow=slow, cycle=cycle, smooth=smooth)
    result = _cross_above(stc, level)
    result.name = "stc_turn_up"
    return result.fillna(0.0)


def stc_turn_dn(df: pd.DataFrame, fast: int = _STC_FAST, slow: int = _STC_SLOW,
                cycle: int = _STC_CYCLE, smooth: int = _STC_SMOOTH,
                level: float = 75.0) -> pd.Series:
    """Event: STC crosses below 75 from above (bearish turn)."""
    close = df["close"].astype(float)
    stc = _stc(close, fast=fast, slow=slow, cycle=cycle, smooth=smooth)
    result = _cross_below(stc, level)
    result.name = "stc_turn_dn"
    return result.fillna(0.0)


# ---------------------------------------------------------------------------
# H) Fair Value Gap (generic 3-candle imbalance)
# ---------------------------------------------------------------------------
# FENCED: generic 3-candle imbalance; distinct from falsified PM3 gap-map;
# display/challenger only pending fresh prereg.
#
# Bullish FVG: Low[t] > High[t-2]  (gap zone = [High[t-2], Low[t]])
# Bearish FVG: High[t] < Low[t-2]  (gap zone = [High[t], Low[t-2]])
# fvg_bull_form: bullish FVG detected on bar t (event dir+1 setup)
# fvg_bear_form: bearish FVG detected on bar t (event dir-1 setup)
# fvg_bull_fill: close re-enters most recent unfilled bull gap (context, dir=0)
# fvg_bear_fill: close re-enters most recent unfilled bear gap (context, dir=0)
#
# Gap tracking: keep last 20 unfilled zones in numpy pass (PIT-clean)

_FVG_TRACK = 20


def fvg_bull_form(df: pd.DataFrame) -> pd.Series:
    """Event: bullish fair value gap forms (Low[t] > High[t-2])."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    result = (low > high.shift(2)).astype(float)
    result.iloc[:2] = 0.0
    result.name = "fvg_bull_form"
    return result.fillna(0.0)


def fvg_bear_form(df: pd.DataFrame) -> pd.Series:
    """Event: bearish fair value gap forms (High[t] < Low[t-2])."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    result = (high < low.shift(2)).astype(float)
    result.iloc[:2] = 0.0
    result.name = "fvg_bear_form"
    return result.fillna(0.0)


def fvg_bull_fill(df: pd.DataFrame, track: int = _FVG_TRACK) -> pd.Series:
    """Context event: close re-enters the most recent unfilled bullish FVG zone.

    Tracks up to `track` most-recent unfilled bull gap zones. A zone is defined
    by [zone_lo, zone_hi] = [High[t-2], Low[t]] at formation bar t. The fill
    fires on the FIRST bar the close drops back into any tracked zone (one event
    per zone entry), then the zone is consumed (removed from tracking).
    """
    close = df["close"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    n = len(close)
    out = np.zeros(n, dtype=float)

    # Each zone: (zone_lo, zone_hi) = (high[t-2], low[t])
    # We store as list of (lo, hi) pairs, cap at `track`
    zones: list[tuple[float, float]] = []

    for i in range(2, n):
        # Check if a new bull FVG forms on bar i
        if low[i] > high[i - 2]:
            zone_lo = high[i - 2]
            zone_hi = low[i]
            zones.append((zone_lo, zone_hi))
            if len(zones) > track:
                zones.pop(0)

        # Check if close fills any tracked zone
        c = close[i]
        filled_idx = None
        for j, (zlo, zhi) in enumerate(zones):
            if zlo <= c <= zhi:
                filled_idx = j
                break
        if filled_idx is not None:
            out[i] = 1.0
            zones.pop(filled_idx)

    return pd.Series(out, index=df.index, name="fvg_bull_fill")


def fvg_bear_fill(df: pd.DataFrame, track: int = _FVG_TRACK) -> pd.Series:
    """Context event: close re-enters the most recent unfilled bearish FVG zone.

    Bearish FVG zone: [zone_lo, zone_hi] = [High[t], Low[t-2]] when High[t] < Low[t-2].
    """
    close = df["close"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    n = len(close)
    out = np.zeros(n, dtype=float)

    zones: list[tuple[float, float]] = []

    for i in range(2, n):
        # Check if a new bear FVG forms on bar i
        if high[i] < low[i - 2]:
            zone_lo = high[i]
            zone_hi = low[i - 2]
            zones.append((zone_lo, zone_hi))
            if len(zones) > track:
                zones.pop(0)

        # Check if close fills any tracked zone
        c = close[i]
        filled_idx = None
        for j, (zlo, zhi) in enumerate(zones):
            if zlo <= c <= zhi:
                filled_idx = j
                break
        if filled_idx is not None:
            out[i] = 1.0
            zones.pop(filled_idx)

    return pd.Series(out, index=df.index, name="fvg_bear_fill")


# ---------------------------------------------------------------------------
# Registry helper
# ---------------------------------------------------------------------------

def _disp(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


# ---------------------------------------------------------------------------
# SIGNALS registry
# ---------------------------------------------------------------------------

SIGNALS: dict[str, dict[str, Any]] = {
    # ---- A) KST ----
    "kst_cross_up": {
        "fn": kst_cross_up,
        "kind": "event",
        "family": "challenger",
        "direction": +1,
        "default_params": {},
        "display": _disp(
            "KST crosses above signal line (negative territory)",
            "KST 指标上穿信号线（负值区域）",
        ),
        "glyph": "arrow_up",
        # New metadata keys
        "dependency_family": "multi_horizon_momentum",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": True,
        "provenance": "Pring M. (1992), 'Technical Analysis Explained', McGraw-Hill; "
                      "daily KST formula per pring.com/learning-center/kst",
        "actionable_lag": 0,
    },
    "kst_cross_dn": {
        "fn": kst_cross_dn,
        "kind": "event",
        "family": "challenger",
        "direction": -1,
        "default_params": {},
        "display": _disp(
            "KST crosses below signal line (positive territory)",
            "KST 指标下穿信号线（正值区域）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "multi_horizon_momentum",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": True,
        "provenance": "Pring M. (1992), 'Technical Analysis Explained', McGraw-Hill; "
                      "daily KST formula per pring.com/learning-center/kst",
        "actionable_lag": 0,
    },
    # ---- B) TSI ----
    "tsi_cross_up": {
        "fn": tsi_cross_up,
        "kind": "event",
        "family": "challenger",
        "direction": +1,
        "default_params": {},
        "display": _disp(
            "True Strength Index crosses above signal (below zero)",
            "真实强度指数上穿信号线（零线以下）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "double_smoothed_momentum",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": True,
        "provenance": "Blau W. (1995), 'Momentum, Direction and Divergence', Wiley; "
                      "TSI formula investopedia.com/terms/t/tsi.asp",
        "actionable_lag": 0,
    },
    "tsi_cross_dn": {
        "fn": tsi_cross_dn,
        "kind": "event",
        "family": "challenger",
        "direction": -1,
        "default_params": {},
        "display": _disp(
            "True Strength Index crosses below signal (above zero)",
            "真实强度指数下穿信号线（零线以上）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "double_smoothed_momentum",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": True,
        "provenance": "Blau W. (1995), 'Momentum, Direction and Divergence', Wiley; "
                      "TSI formula investopedia.com/terms/t/tsi.asp",
        "actionable_lag": 0,
    },
    # ---- C) Coppock ----
    "coppock_turn_up": {
        "fn": coppock_turn_up,
        "kind": "event",
        "family": "challenger",
        "direction": +1,
        "default_params": {},
        "display": _disp(
            "Coppock curve turns up from a trough (below zero)",
            "科波克指标在零线下方由跌转升",
        ),
        "glyph": "arrow_up",
        "dependency_family": "multi_horizon_momentum",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": True,
        "provenance": "Coppock E.S.C. (1962), Barron's; canonical monthly 14/11/10; "
                      "frozen daily adaptation: WMA(ROC(294)+ROC(231),210) — "
                      "approximately 14/11/10 monthly using 21 trading-days/month",
        "actionable_lag": 0,
    },
    # ---- D) Ultimate Oscillator ----
    "uo_os_exit": {
        "fn": uo_os_exit,
        "kind": "event",
        "family": "challenger",
        "direction": +1,
        "default_params": {"p1": 7, "p2": 14, "p3": 28, "level": 30.0},
        "display": _disp(
            "Ultimate Oscillator exits oversold zone (crosses above 30)",
            "终极振荡器脱离超卖区（上穿30）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "multi_horizon_momentum",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": True,
        "provenance": "Williams L. (1985), 'How I Made One Million Dollars'; "
                      "formula stockcharts.com/school/doku.php?id=chart_school:technical_indicators:ultimate_oscillator",
        "actionable_lag": 0,
    },
    "uo_ob_exit": {
        "fn": uo_ob_exit,
        "kind": "event",
        "family": "challenger",
        "direction": -1,
        "default_params": {"p1": 7, "p2": 14, "p3": 28, "level": 70.0},
        "display": _disp(
            "Ultimate Oscillator exits overbought zone (crosses below 70)",
            "终极振荡器脱离超买区（下穿70）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "multi_horizon_momentum",
        "role": "trigger",
        "entry_stack_blocked": True,
        "challenger_only": True,
        "provenance": "Williams L. (1985), 'How I Made One Million Dollars'; "
                      "formula stockcharts.com/school/doku.php?id=chart_school:technical_indicators:ultimate_oscillator",
        "actionable_lag": 0,
    },
    # ---- E) Fisher Transform ----
    "fisher_cross_up": {
        "fn": fisher_cross_up,
        "kind": "event",
        "family": "challenger",
        "direction": +1,
        "default_params": {"n": _FISHER_N},
        "display": _disp(
            "Fisher Transform crosses above prior bar (below -1)",
            "费雪变换在-1以下向上穿越上期值",
        ),
        "glyph": "arrow_up",
        "dependency_family": "cycle_transform",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "Ehlers J. (2002), 'Using The Fisher Transform', mesasoftware.com; "
                      "mesasoftware.com/papers/UsingTheFisherTransform.pdf",
        "actionable_lag": 0,
    },
    "fisher_cross_dn": {
        "fn": fisher_cross_dn,
        "kind": "event",
        "family": "challenger",
        "direction": -1,
        "default_params": {"n": _FISHER_N},
        "display": _disp(
            "Fisher Transform crosses below prior bar (above +1)",
            "费雪变换在+1以上向下穿越上期值",
        ),
        "glyph": "arrow_down",
        "dependency_family": "cycle_transform",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "Ehlers J. (2002), 'Using The Fisher Transform', mesasoftware.com; "
                      "mesasoftware.com/papers/UsingTheFisherTransform.pdf",
        "actionable_lag": 0,
    },
    # ---- F) QQE ----
    "qqe_cross_up": {
        "fn": qqe_cross_up,
        "kind": "event",
        "family": "challenger",
        "direction": +1,
        "default_params": {"rsi_n": _QQE_RSI_N, "sf": _QQE_SF, "factor": _QQE_FACTOR},
        "display": _disp(
            "QQE smoothed RSI crosses above adaptive band (below 50)",
            "QQE 平滑RSI在50以下上穿自适应轨道",
        ),
        "glyph": "arrow_up",
        "dependency_family": "rsi_composite",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "Qualitative Quantitative Estimation, TradeStation docs; "
                      "github.com/EarnForex/QQE",
        "actionable_lag": 0,
    },
    "qqe_cross_dn": {
        "fn": qqe_cross_dn,
        "kind": "event",
        "family": "challenger",
        "direction": -1,
        "default_params": {"rsi_n": _QQE_RSI_N, "sf": _QQE_SF, "factor": _QQE_FACTOR},
        "display": _disp(
            "QQE smoothed RSI crosses below adaptive band (above 50)",
            "QQE 平滑RSI在50以上下穿自适应轨道",
        ),
        "glyph": "arrow_down",
        "dependency_family": "rsi_composite",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "Qualitative Quantitative Estimation, TradeStation docs; "
                      "github.com/EarnForex/QQE",
        "actionable_lag": 0,
    },
    # ---- G) Schaff Trend Cycle ----
    "stc_turn_up": {
        "fn": stc_turn_up,
        "kind": "event",
        "family": "challenger",
        "direction": +1,
        "default_params": {
            "fast": _STC_FAST, "slow": _STC_SLOW,
            "cycle": _STC_CYCLE, "smooth": _STC_SMOOTH, "level": 25.0,
        },
        "display": _disp(
            "Schaff Trend Cycle crosses above 25 (bullish turn)",
            "沙夫趋势周期上穿25（看涨转折）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "macd_cycle",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "Schaff D. (1999), 'Cybernetics and the Schaff Trend Cycle', "
                      "investopedia.com/terms/s/schaff-trend-cycle.asp",
        "actionable_lag": 0,
    },
    "stc_turn_dn": {
        "fn": stc_turn_dn,
        "kind": "event",
        "family": "challenger",
        "direction": -1,
        "default_params": {
            "fast": _STC_FAST, "slow": _STC_SLOW,
            "cycle": _STC_CYCLE, "smooth": _STC_SMOOTH, "level": 75.0,
        },
        "display": _disp(
            "Schaff Trend Cycle crosses below 75 (bearish turn)",
            "沙夫趋势周期下穿75（看跌转折）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "macd_cycle",
        "role": "trigger",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "Schaff D. (1999), 'Cybernetics and the Schaff Trend Cycle', "
                      "investopedia.com/terms/s/schaff-trend-cycle.asp",
        "actionable_lag": 0,
    },
    # ---- H) Fair Value Gap ----
    "fvg_bull_form": {
        "fn": fvg_bull_form,
        "kind": "event",
        "family": "challenger",
        "direction": +1,
        "default_params": {},
        "display": _disp(
            "Bullish price gap forms (3-candle imbalance zone)",
            "看涨价格缺口形成（三根K线失衡区）",
        ),
        "glyph": "arrow_up",
        "dependency_family": "gap_imbalance",
        "role": "setup",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "generic 3-candle imbalance; distinct from falsified PM3 gap-map; "
                      "display/challenger only pending fresh prereg",
        "actionable_lag": 0,
    },
    "fvg_bear_form": {
        "fn": fvg_bear_form,
        "kind": "event",
        "family": "challenger",
        "direction": -1,
        "default_params": {},
        "display": _disp(
            "Bearish price gap forms (3-candle imbalance zone)",
            "看跌价格缺口形成（三根K线失衡区）",
        ),
        "glyph": "arrow_down",
        "dependency_family": "gap_imbalance",
        "role": "setup",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "generic 3-candle imbalance; distinct from falsified PM3 gap-map; "
                      "display/challenger only pending fresh prereg",
        "actionable_lag": 0,
    },
    "fvg_bull_fill": {
        "fn": fvg_bull_fill,
        "kind": "event",
        "family": "challenger",
        "direction": 0,
        "default_params": {"track": _FVG_TRACK},
        "display": _disp(
            "Bullish gap zone filled (price returns to imbalance area)",
            "看涨缺口区域被回补（价格回归失衡区）",
        ),
        "glyph": "filled",
        "dependency_family": "gap_imbalance",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "generic 3-candle imbalance; distinct from falsified PM3 gap-map; "
                      "display/challenger only pending fresh prereg",
        "actionable_lag": 0,
    },
    "fvg_bear_fill": {
        "fn": fvg_bear_fill,
        "kind": "event",
        "family": "challenger",
        "direction": 0,
        "default_params": {"track": _FVG_TRACK},
        "display": _disp(
            "Bearish gap zone filled (price returns to imbalance area)",
            "看跌缺口区域被回补（价格回归失衡区）",
        ),
        "glyph": "filled",
        "dependency_family": "gap_imbalance",
        "role": "context",
        "entry_stack_blocked": False,
        "challenger_only": True,
        "provenance": "generic 3-candle imbalance; distinct from falsified PM3 gap-map; "
                      "display/challenger only pending fresh prereg",
        "actionable_lag": 0,
    },
}
