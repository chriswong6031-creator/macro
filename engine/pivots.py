"""engine/pivots.py — StockInvest 'Pivot Bottoms' / 'Pivot Tops' signal reconstruction.

Reconstructs the Pivot Bottom (bullish) and Pivot Top (bearish) signals per the
StockInvest algo-zigzag specification: confirmed turning points identified by a k-bar
local extremum (zigzag pivot), optionally verified with a ±verify_pct price threshold,
volume confirmation, RSI-context, and trend direction.

CAVEATS
-------
1. SURVIVORSHIP BIAS: universe = data/stocks/ (~224 mega-cap survivors). Testing on
   this universe is OPTIMISTIC; delisted names and small-caps are absent.
2. PARAMETERS: k (confirmation window), verify_pct (margin), volume_factor (volume
   spike threshold), rsi_window and rsi_lo/rsi_hi bands are ASSUMED from the spec
   description "confirmed with a +/-3% margin, considering volume/RSI/trend".
3. PIT CONTRACT: a pivot at bar i is CONFIRMED on bar i+k (earliest bar when both
   sides of the window are complete). The signal fires on the CONFIRMATION BAR
   (i+k), not the pivot bar (i). This is the only PIT-clean fire time.
4. REUSE: zigzag backbone reuses engine.cycles._pivots (line ~438) which was purpose-
   built for exactly this: confirmed extrema, no look-ahead, last k bars excluded.
5. This is display-only / research. No LLM-originated signals or escalations.

Signal IDs
----------
- pivot_bottom: fires on the confirmation bar of a verified pivot low (+1 direction)
- pivot_top:    fires on the confirmation bar of a verified pivot high (-1 direction)
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default parameters (pre-registered; do not tune without a pre-reg amendment)
# ---------------------------------------------------------------------------
DEFAULT_K: int = 5                  # bars each side for zigzag extremum detection
DEFAULT_VERIFY_PCT: float = 0.03    # ±3% price margin (verbatim from spec)
DEFAULT_VOLUME_FACTOR: float = 1.0  # volume at pivot bar >= factor * rolling_vol_mean
DEFAULT_VOL_WINDOW: int = 20        # rolling window for volume mean
DEFAULT_RSI_WINDOW: int = 14        # RSI lookback
DEFAULT_RSI_LO: float = 40.0        # RSI <= rsi_lo for pivot bottom confirmation
DEFAULT_RSI_HI: float = 60.0        # RSI >= rsi_hi for pivot top confirmation


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _roll_vol_mean(volume: pd.Series, n: int) -> pd.Series:
    """Rolling mean of volume over trailing n bars (min_periods = n//2)."""
    return volume.rolling(n, min_periods=max(1, n // 2)).mean()


# ---------------------------------------------------------------------------
# Public signal functions
# ---------------------------------------------------------------------------

def pivot_bottom(
    df: pd.DataFrame,
    k: int = DEFAULT_K,
    verify_pct: float = DEFAULT_VERIFY_PCT,
    volume_factor: float = DEFAULT_VOLUME_FACTOR,
    vol_window: int = DEFAULT_VOL_WINDOW,
    rsi_window: int = DEFAULT_RSI_WINDOW,
    rsi_hi_gate: float = DEFAULT_RSI_LO,
    apply_rsi_gate: bool = True,
    apply_volume_gate: bool = True,
) -> pd.Series:
    """Return a {0.0, 1.0} event Series firing on the CONFIRMATION BAR of each
    verified pivot bottom (local low).

    PIT contract: a pivot low at bar i is only knowable at bar i+k (both sides
    of the k-bar window are complete). The signal fires on bar i+k, not bar i.
    No centering, no future referencing.

    Verification conditions (all must hold, optional gates toggleable):
    - The bar is a k-bar local minimum (zigzag low) via engine.cycles._pivots
    - Price at the pivot bar is within verify_pct of that local minimum
      (i.e. the pivot bar's close is the confirmed low — always True by construction,
       but the ±verify_pct gate applies to the CLOSE vs LOW comparison on the pivot bar:
       abs(close[i] - low[i]) / close[i] <= verify_pct, confirming the candle closed near
       its intrabar low — a "real" bottom, not a wick test)
    - Volume at pivot bar >= volume_factor × trailing vol_window-bar mean volume
    - RSI(rsi_window) at confirmation bar <= rsi_hi_gate (oversold context)

    Parameters
    ----------
    df : DataFrame
        OHLCV frame (close, high, low, volume; DatetimeIndex).
    k : int
        Half-window for zigzag extremum (default 5 bars each side).
    verify_pct : float
        Close-to-low proximity gate (default 0.03 = ±3%).
    volume_factor : float
        Volume spike gate: volume[pivot] >= factor * mean_volume.
    vol_window : int
        Rolling window for mean volume.
    rsi_hi_gate : float
        RSI upper bound for pivot bottom context (default 40).
    apply_rsi_gate : bool
        Whether to apply the RSI context filter.
    apply_volume_gate : bool
        Whether to apply the volume spike filter.

    Returns
    -------
    pd.Series[float]
        Event series in {0.0, 1.0} aligned to df.index; 1.0 on confirmation bars.
        Named 'pivot_bottom'.
    """
    from engine.cycles import _pivots  # noqa: PLC0415
    from engine.canon import rsi  # noqa: PLC0415

    close = df["close"]
    low = df.get("low", close)
    volume = df.get("volume", pd.Series(np.nan, index=close.index))

    arr = close.to_numpy(dtype=float)
    low_arr = low.to_numpy(dtype=float) if hasattr(low, "to_numpy") else arr

    # Zigzag pivot lows (integer indices into arr) — already PIT-safe
    pivot_indices = _pivots(arr, k, "low")

    # Precompute filters at pivot bars
    rsi_vals = rsi(close, rsi_window) if apply_rsi_gate else pd.Series(np.nan, index=close.index)
    vol_mean = _roll_vol_mean(volume, vol_window)

    fire = pd.Series(0.0, index=close.index)

    for i in pivot_indices:
        confirm_i = i + k  # PIT: fire on confirmation bar
        if confirm_i >= len(close):
            continue

        # --- verify_pct gate: close at pivot bar near the local low
        ci = close.iloc[i]
        li = low_arr[i]
        if ci > 0 and abs(ci - li) / ci > verify_pct:
            continue

        # --- volume gate: volume at pivot bar vs trailing mean
        if apply_volume_gate:
            vol_at_pivot = volume.iloc[i]
            mean_vol = vol_mean.iloc[i]
            if pd.notna(vol_at_pivot) and pd.notna(mean_vol) and mean_vol > 0:
                if vol_at_pivot < volume_factor * mean_vol:
                    continue

        # --- RSI gate: RSI at CONFIRMATION bar (PIT: latest knowable RSI)
        if apply_rsi_gate:
            rsi_val = rsi_vals.iloc[confirm_i]
            if pd.notna(rsi_val) and rsi_val > rsi_hi_gate:
                continue

        fire.iloc[confirm_i] = 1.0

    fire.name = "pivot_bottom"
    return fire


def pivot_top(
    df: pd.DataFrame,
    k: int = DEFAULT_K,
    verify_pct: float = DEFAULT_VERIFY_PCT,
    volume_factor: float = DEFAULT_VOLUME_FACTOR,
    vol_window: int = DEFAULT_VOL_WINDOW,
    rsi_window: int = DEFAULT_RSI_WINDOW,
    rsi_lo_gate: float = DEFAULT_RSI_HI,
    apply_rsi_gate: bool = True,
    apply_volume_gate: bool = True,
) -> pd.Series:
    """Return a {0.0, 1.0} event Series firing on the CONFIRMATION BAR of each
    verified pivot top (local high).

    PIT contract: same as pivot_bottom — fires on bar i+k (confirmation bar),
    where bar i is the zigzag high.

    Verification conditions (mirror of pivot_bottom for the bearish side):
    - Bar is a k-bar local maximum via engine.cycles._pivots
    - abs(close[i] - high[i]) / close[i] <= verify_pct (close near intrabar high)
    - Volume at pivot bar >= volume_factor × trailing vol_window-bar mean volume
    - RSI(rsi_window) at confirmation bar >= rsi_lo_gate (overbought context)

    Parameters
    ----------
    df : DataFrame
        OHLCV frame (close, high, low, volume; DatetimeIndex).
    k : int
        Half-window for zigzag extremum (default 5 bars each side).
    verify_pct : float
        Close-to-high proximity gate (default 0.03 = ±3%).
    volume_factor : float
        Volume spike gate.
    vol_window : int
        Rolling window for mean volume.
    rsi_lo_gate : float
        RSI lower bound for pivot top context (default 60).
    apply_rsi_gate : bool
        Whether to apply the RSI context filter.
    apply_volume_gate : bool
        Whether to apply the volume spike filter.

    Returns
    -------
    pd.Series[float]
        Event series in {0.0, 1.0} aligned to df.index; 1.0 on confirmation bars.
        Named 'pivot_top'.
    """
    from engine.cycles import _pivots  # noqa: PLC0415
    from engine.canon import rsi  # noqa: PLC0415

    close = df["close"]
    high = df.get("high", close)
    volume = df.get("volume", pd.Series(np.nan, index=close.index))

    arr = close.to_numpy(dtype=float)
    high_arr = high.to_numpy(dtype=float) if hasattr(high, "to_numpy") else arr

    pivot_indices = _pivots(arr, k, "high")

    rsi_vals = rsi(close, rsi_window) if apply_rsi_gate else pd.Series(np.nan, index=close.index)
    vol_mean = _roll_vol_mean(volume, vol_window)

    fire = pd.Series(0.0, index=close.index)

    for i in pivot_indices:
        confirm_i = i + k  # PIT: fire on confirmation bar
        if confirm_i >= len(close):
            continue

        # --- verify_pct gate: close at pivot bar near the local high
        ci = close.iloc[i]
        hi = high_arr[i]
        if ci > 0 and abs(ci - hi) / ci > verify_pct:
            continue

        # --- volume gate
        if apply_volume_gate:
            vol_at_pivot = volume.iloc[i]
            mean_vol = vol_mean.iloc[i]
            if pd.notna(vol_at_pivot) and pd.notna(mean_vol) and mean_vol > 0:
                if vol_at_pivot < volume_factor * mean_vol:
                    continue

        # --- RSI gate at confirmation bar
        if apply_rsi_gate:
            rsi_val = rsi_vals.iloc[confirm_i]
            if pd.notna(rsi_val) and rsi_val < rsi_lo_gate:
                continue

        fire.iloc[confirm_i] = 1.0

    fire.name = "pivot_top"
    return fire


# ---------------------------------------------------------------------------
# SIGNALS catalog registration
# ---------------------------------------------------------------------------

SIGNALS: dict[str, dict] = {
    "pivot_bottom": {
        "fn": pivot_bottom,
        "kind": "event",
        "family": "pivots",
        "direction": +1,
        "default_params": {
            "k": DEFAULT_K,
            "verify_pct": DEFAULT_VERIFY_PCT,
            "volume_factor": DEFAULT_VOLUME_FACTOR,
            "vol_window": DEFAULT_VOL_WINDOW,
            "rsi_window": DEFAULT_RSI_WINDOW,
            "rsi_hi_gate": DEFAULT_RSI_LO,
            "apply_rsi_gate": True,
            "apply_volume_gate": True,
        },
        "display": {
            "en": "Pivot Bottom",
            "zh": "转折底部",
        },
        "glyph": "circle_green",
    },
    "pivot_top": {
        "fn": pivot_top,
        "kind": "event",
        "family": "pivots",
        "direction": -1,
        "default_params": {
            "k": DEFAULT_K,
            "verify_pct": DEFAULT_VERIFY_PCT,
            "volume_factor": DEFAULT_VOLUME_FACTOR,
            "vol_window": DEFAULT_VOL_WINDOW,
            "rsi_window": DEFAULT_RSI_WINDOW,
            "rsi_lo_gate": DEFAULT_RSI_HI,
            "apply_rsi_gate": True,
            "apply_volume_gate": True,
        },
        "display": {
            "en": "Pivot Top",
            "zh": "转折顶部",
        },
        "glyph": "circle_red",
    },
}
