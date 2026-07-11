"""engine/htf_oscillators.py — 2W oscillator helpers for Flow Leaders Desk (FL-R7).

Pure-function layer; zero I/O.  All 2W resampling via
``engine.htf_durability._biweekly_close`` — ``resample('2W-FRI')`` FORBIDDEN
(calendar-anchor drift, not PIT-safe).

Compliance:
  FL-R7  — 2W StochRSI K/D + 2W MACD bars_to_cross ETA (display/B-chip only)
  A2 case law: 2W oscillator turns tested NULL at basket grain ("catastrophically
  late") — these are operator-requested display context; never standalone signal,
  never sort key, never fire-qualifying.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.htf_durability import _biweekly_close
from engine.signal_quality import _stoch_rsi_kd

log = logging.getLogger(__name__)

# ── Minimum coverage gates (FL-R7) ───────────────────────────────────────────
_MIN_DAILY_BARS: int = 20    # daily bars required before biweekly resampling
# StochRSI math needs RSI(14) + Stoch(14) + SMA_K(3) + SMA_D(3) = 34 bars minimum;
# use 35 as the gate to guarantee at least one non-null k output.
_MIN_BIWEEKLY_BARS: int = 35

# ── MACD parameters (12, 26, 9) — standard; mirrors cycles.macd_parts ────────
_MACD_FAST: int = 12
_MACD_SLOW: int = 26
_MACD_SIG: int = 9
_MACD_MIN_BARS: int = max(_MACD_SLOW, 40)  # need enough 2W bars for the EMA to settle

# ── Approaching-cross ETA cap (mirrors cycles._MACD_APPROACH_MAX_BARS) ────────
_MACD_APPROACH_MAX_BARS: int = 6


def _coverage_ok(daily_close: pd.Series) -> tuple[bool, pd.Series]:
    """Return (coverage_met, biweekly_series).  All-None when coverage fails."""
    if daily_close is None or len(daily_close) < _MIN_DAILY_BARS:
        return False, pd.Series(dtype=float)
    bw = _biweekly_close(daily_close)
    if len(bw) < _MIN_BIWEEKLY_BARS:
        return False, pd.Series(dtype=float)
    return True, bw


def stochrsi_2w(daily_close: pd.Series) -> dict:
    """2W StochRSI K and D on the epoch-anchored biweekly close (FL-R7).

    Uses ``engine.htf_durability._biweekly_close`` for resampling (PIT-safe,
    EPOCH-anchored) and ``engine.signal_quality._stoch_rsi_kd`` for the pinned
    math (RSI(14) → Stoch(14) → SMA_K(3) → SMA_D(3)).

    Args:
        daily_close: Date-indexed daily close Series (ascending).

    Returns:
        dict with keys:
          ``k``             : float | None — latest StochRSI K value (0-100)
          ``d``             : float | None — latest StochRSI D value (0-100)
          ``oversold``      : bool | None — K < 20 (True/False); None on cold-start
          ``htf_coverage``  : bool — True when enough daily/biweekly bars exist

    Cold-start: < _MIN_DAILY_BARS daily bars OR < _MIN_BIWEEKLY_BARS biweekly bars
    → all None + htf_coverage=False.  Never fake-False.
    """
    null = {"k": None, "d": None, "oversold": None, "htf_coverage": False}

    ok, bw = _coverage_ok(daily_close)
    if not ok:
        return null

    try:
        k_series, d_series = _stoch_rsi_kd(bw)
    except Exception as e:  # noqa: BLE001
        log.debug("stochrsi_2w: _stoch_rsi_kd failed: %s", e)
        return null

    k_clean = k_series.dropna()
    d_clean = d_series.dropna()

    if k_clean.empty:
        return null

    k_val = float(k_clean.iloc[-1]) if pd.notna(k_clean.iloc[-1]) else None
    d_val = float(d_clean.iloc[-1]) if (not d_clean.empty and pd.notna(d_clean.iloc[-1])) else None
    oversold = bool(k_val < 20) if k_val is not None else None

    return {"k": k_val, "d": d_val, "oversold": oversold, "htf_coverage": True}


def _macd_parts_2w(bw: pd.Series) -> pd.DataFrame:
    """2W MACD(12,26,9) histogram on a biweekly close series."""
    ema12 = bw.ewm(span=_MACD_FAST, min_periods=_MACD_FAST).mean()
    ema26 = bw.ewm(span=_MACD_SLOW, min_periods=_MACD_SLOW).mean()
    line = ema12 - ema26
    sig = line.ewm(span=_MACD_SIG, min_periods=_MACD_SIG).mean()
    return pd.DataFrame({"line": line, "signal": sig, "hist": line - sig}, index=bw.index)


def macd_bars_to_cross_2w(daily_close: pd.Series) -> dict:
    """2W MACD(12,26,9) bars-to-cross ETA on the epoch-anchored biweekly close (FL-R7).

    Mirrors ``engine.cycles._tf_state`` projection math:
      - If hist > 0 and recently crossed (within 3 bars — h[-4:-1] detection window):
        state='crossed', bars_since = distance from the earliest ≤0 bar in h[-4:-1]
      - If hist < 0 AND rising 3 consecutive bars AND linear-extrapolation ETA
        ≤ _MACD_APPROACH_MAX_BARS (6): state='approaching', bars_to_cross=eta
      - Otherwise: state='none'

    The 3-bar slope (h[-1] - h[-4]) / 3 and ETA = -h[-1] / slope follow
    cycles._tf_state exactly (with h the histogram dropna series).

    Note: the B4 chip applies its own ≤2-bar ETA gate at the caller before
    displaying htf_cross_near; this function returns the raw ETA for the caller
    to apply that gate independently.

    Args:
        daily_close: Date-indexed daily close Series (ascending).

    Returns:
        dict with keys:
          ``state``         : 'crossed' | 'approaching' | 'none'
          ``bars_since``    : int | None — bars since cross (state='crossed' only)
          ``bars_to_cross`` : float | None — ETA bars (state='approaching' only)
          ``htf_coverage``  : bool
    """
    null = {"state": "none", "bars_since": None, "bars_to_cross": None, "htf_coverage": False}

    ok, bw = _coverage_ok(daily_close)
    if not ok:
        return null

    if len(bw) < _MACD_MIN_BARS:
        # not enough biweekly bars for EMA26 to settle
        return {"state": "none", "bars_since": None, "bars_to_cross": None, "htf_coverage": True}

    try:
        macd_df = _macd_parts_2w(bw)
    except Exception as e:  # noqa: BLE001
        log.debug("macd_bars_to_cross_2w: MACD computation failed: %s", e)
        return null

    hist = macd_df["hist"]
    h = hist.dropna()
    if len(h) < 4:
        return {"state": "none", "bars_since": None, "bars_to_cross": None, "htf_coverage": True}

    latest = float(h.iloc[-1])

    # ── crossed: hist > 0 and any bar in the detection window h[-4:-1] was ≤ 0 ──
    # bars_since counting uses the SAME h[-4:-1] window so a cross at h[-4]
    # reports bars_since=3, not a phantom 0.
    if latest > 0 and (h.iloc[-4:-1] <= 0).any():
        # Search h[-4:-1] from oldest to newest to find the first ≤0 bar;
        # bars_since = distance from that bar to h[-1].
        detection_window = h.iloc[-4:-1]  # h[-4], h[-3], h[-2]
        bars_since = 3  # default: cross was at h[-4] (3 bars before h[-1])
        for offset, v in enumerate(detection_window.values):
            # offset 0 → h[-4], offset 1 → h[-3], offset 2 → h[-2]
            if float(v) <= 0:
                bars_since = 3 - offset  # h[-4]→3, h[-3]→2, h[-2]→1
                break
        return {"state": "crossed", "bars_since": bars_since, "bars_to_cross": None, "htf_coverage": True}

    # ── approaching: hist < 0, rising 3 consecutive bars, ETA ≤ 6 ───────────
    if latest < 0:
        rising = bool(float(h.iloc[-1]) > float(h.iloc[-2]) > float(h.iloc[-3]))
        if rising and len(h) >= 4:
            slope = (float(h.iloc[-1]) - float(h.iloc[-4])) / 3.0
            if slope > 0:
                eta = -latest / slope
                if eta <= _MACD_APPROACH_MAX_BARS:
                    btc = round(float(max(eta, 0.5)), 1)
                    return {"state": "approaching", "bars_since": None, "bars_to_cross": btc, "htf_coverage": True}

    return {"state": "none", "bars_since": None, "bars_to_cross": None, "htf_coverage": True}
