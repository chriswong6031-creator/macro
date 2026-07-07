"""engine/tech_stars.py — StockInvest Golden Star / Death Star signal reconstruction.

Reconstructs the Golden Star (bullish) and Death Star (bearish) signals as described
in the reconciled spec derived from primary-source reverse-engineering.

IMPORTANT CAVEATS (print these with every result)
--------------------------------------------------
1. SURVIVORSHIP BIAS: universe = data/stocks/ (~224 mega-cap survivors). A bottom-
   finding test on this universe is OPTIMISTIC. Delisted names and small-caps are absent.
2. UNKNOWN PARAMETERS: the true price-line proximity P, liquidity floor L, and trend
   lookback k are UNKNOWN (spec labels them ASSUMED). We implement:
       P = 0.03  (3% — the Death Star's verbatim "1–3%" band, back-propagated)
       L = $5M dollar ADV over 21 days  (StockInvest flags low-liquidity as false-signal-prone)
       k = 20 trading days  (trend lookback for long-MA slope check)
   A NULL falsifies THIS RECONSTRUCTION, not StockInvest's private construction.
3. MA TYPE: assumed SMA (the platform cites conventional SMA period standards).
4. CONFIRMATION: 2-trading-day confirmation (verbatim). PIT entry = open of confirm_day+1
   (implemented as position set at confirm_day's close → backtest_core enters next bar).
5. RSI-14 / RSI-21 are CONTEXT / DISPLAY inputs, not hard gates (assumed).
6. This is display-only / research. No LLM-originated signals or escalations.

Signal families and MA pairs
----------------------------
- Golden Star Short-Term: (7, 35) and (21, 100)   [pre-registered; confirmed by platform lists]
- Death Star Short-Term:  (7, 35) and (21, 100)   [bearish mirror]
- Golden Star Long-Term:  (50, 200)                [out of scope for bottom-finding backtest]

Backtest spec reference: spec §B, pre-registered 2026-07-07.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (pre-registered; do not tune)
# ---------------------------------------------------------------------------
PRICE_GATE_PCT: float = 0.03        # P: price within 3% of crossing MA (spec A1/A5 ASSUMED)
ADV_FLOOR_USD: float = 5_000_000.0  # L: dollar ADV(21) >= $5M (spec B2)
TREND_K: int = 20                   # k: long-MA slope over trailing 20 days (spec A1 ASSUMED)
CONFIRM_DAYS: int = 2               # verbatim: 2-trading-day confirmation lag (spec A1)
ATR_N: int = 14                     # ATR window for durable-bottom definition (spec B3)
ATR_DURABLE_MULT: float = 1.0       # durable bottom = low never revisits < signal_low - 1×ATR


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _dollar_adv(close: pd.Series, volume: pd.Series, n: int = 21) -> pd.Series:
    """21-day rolling dollar average daily volume (close × volume)."""
    dv = close * volume
    return dv.rolling(n, min_periods=max(1, n // 2)).mean()


def _sma_slope_positive(sma_series: pd.Series, k: int) -> pd.Series:
    """True where SMA[t] > SMA[t-k] (uptrend condition over k bars)."""
    return sma_series > sma_series.shift(k)


def _price_near_ma(close: pd.Series, ma: pd.Series, pct: float) -> pd.Series:
    """True where abs(close - ma) / close <= pct (price-line coincidence gate)."""
    return (close - ma).abs() / close.clip(lower=1e-9) <= pct


# ---------------------------------------------------------------------------
# Golden Star signal
# ---------------------------------------------------------------------------

def golden_star_signal(
    df: pd.DataFrame,
    short_n: int = 7,
    long_n: int = 35,
    price_gate_pct: float = PRICE_GATE_PCT,
    trend_k: int = TREND_K,
    adv_floor: float = ADV_FLOOR_USD,
    confirm_days: int = CONFIRM_DAYS,
    apply_price_gate: bool = True,
) -> pd.Series:
    """Compute the Golden Star position Series for a single-ticker OHLCV DataFrame.

    Returns a float Series in {0.0, 1.0}: 1.0 on days where a confirmed Golden Star
    is active (position entered), 0.0 otherwise.

    Construction (per reconciled spec §A1/A2):
    - Short MA crosses ABOVE long MA (golden cross)
    - Price-line gate: price within ``price_gate_pct`` of the short MA at the cross bar
      (the documented "three-entity intersection" distinguishing Golden Star from a plain
      Golden Cross). Gate is ON by default; can be toggled for the pre-registered sensitivity.
    - Liquidity gate: dollar_adv(21) >= adv_floor at signal date
    - Trend gate: long MA rising over trailing trend_k days (long MA slope > 0)
    - 2-day confirmation: the cross must still hold (short_ma > long_ma) at confirm_day.
      Position is set at confirm_day's close so backtest_core enters next bar (open of
      confirm_day+1) — PIT-clean, no look-ahead on the confirm bar.
    - Time-exit: NOT applied here; caller (backtest harness) owns the horizon/exit logic.
      Position is held as 1.0 from entry; the caller slices the holding window.

    Parameters
    ----------
    df : DataFrame
        OHLCV frame (close, high, low, volume).
    short_n, long_n : int
        MA periods. Pre-registered pairs: (7, 35) and (21, 100).
    price_gate_pct : float
        Price-line proximity gate (default 0.03 = 3%).
    trend_k : int
        Long-MA uptrend lookback in trading days (default 20).
    adv_floor : float
        Dollar ADV(21) gate in USD (default $5M).
    confirm_days : int
        Number of days the cross must persist before entry (verbatim: 2).
    apply_price_gate : bool
        Toggle for the pre-registered {with/without} price-gate sensitivity.

    Returns
    -------
    pd.Series[float]
        Position series aligned to df.index; 1.0 = long, 0.0 = flat.
        Named 'golden_star_{short_n}_{long_n}'.
    """
    close = df["close"]
    volume = df.get("volume", pd.Series(np.nan, index=close.index))

    # --- moving averages -----------------------------------------------------
    from engine.strategy_signals import sma  # noqa: PLC0415
    ma_s = sma(close, short_n)
    ma_l = sma(close, long_n)

    # --- raw cross detection: short crosses ABOVE long -----------------------
    # cross[t] = True if short > long at t AND short <= long at t-1
    cross = (ma_s > ma_l) & (ma_s.shift(1) <= ma_l.shift(1))

    # --- filters at cross bar ------------------------------------------------
    liq_ok = _dollar_adv(close, volume).fillna(0.0) >= adv_floor
    trend_ok = _sma_slope_positive(ma_l, trend_k)
    price_ok = (
        _price_near_ma(close, ma_s, price_gate_pct)
        if apply_price_gate
        else pd.Series(True, index=close.index, dtype=bool)
    )

    # raw signal fires where all conditions hold AND it was a cross
    raw_signal = cross & liq_ok & trend_ok & price_ok

    # --- 2-day confirmation --------------------------------------------------
    # After a raw fire on day t, check that short_ma > long_ma still holds on
    # day t+confirm_days. Position goes active on day t+confirm_days (PIT: enter
    # at open of t+confirm_days+1 via backtest_core's shift(1)).
    still_crossed = (ma_s > ma_l)  # True on every day the cross is intact

    # For each raw fire at day t, mark day t+confirm_days as the entry bar IF
    # still_crossed is True there. We implement this with a rolling forward fill:
    # propagate the raw_signal mark forward confirm_days steps.
    fire_idx = raw_signal[raw_signal].index
    pos = pd.Series(0.0, index=close.index)

    if len(fire_idx) > 0:
        # mark confirm_day for each fire
        date_to_pos = close.index.get_indexer(fire_idx, method=None)
        for i in date_to_pos:
            confirm_i = i + confirm_days
            if confirm_i < len(close.index) and still_crossed.iloc[confirm_i]:
                pos.iloc[confirm_i] = 1.0

    pos.name = f"golden_star_{short_n}_{long_n}"
    return pos


def death_star_signal(
    df: pd.DataFrame,
    short_n: int = 7,
    long_n: int = 35,
    price_gate_pct: float = PRICE_GATE_PCT,
    trend_k: int = TREND_K,
    adv_floor: float = ADV_FLOOR_USD,
    confirm_days: int = CONFIRM_DAYS,
    apply_price_gate: bool = True,
) -> pd.Series:
    """Compute the Death Star position Series (bearish mirror of Golden Star).

    Returns 1.0 on days of confirmed Death Star (short side signal), 0.0 otherwise.

    Construction (spec §A5): short MA crosses BELOW long MA, price-line coincident
    (within price_gate_pct of short MA at cross bar), 2-day confirmation.
    The 'trend_ok' condition for bearish: long MA falling over trailing trend_k days.
    """
    close = df["close"]
    volume = df.get("volume", pd.Series(np.nan, index=close.index))

    from engine.strategy_signals import sma  # noqa: PLC0415
    ma_s = sma(close, short_n)
    ma_l = sma(close, long_n)

    # bearish cross: short crosses BELOW long
    cross = (ma_s < ma_l) & (ma_s.shift(1) >= ma_l.shift(1))

    liq_ok = _dollar_adv(close, volume).fillna(0.0) >= adv_floor
    # trend_ok for bearish: long MA declining
    trend_ok = ~_sma_slope_positive(ma_l, trend_k)
    price_ok = (
        _price_near_ma(close, ma_s, price_gate_pct)
        if apply_price_gate
        else pd.Series(True, index=close.index, dtype=bool)
    )

    raw_signal = cross & liq_ok & trend_ok & price_ok

    still_crossed = (ma_s < ma_l)
    fire_idx = raw_signal[raw_signal].index
    pos = pd.Series(0.0, index=close.index)

    if len(fire_idx) > 0:
        date_to_pos = close.index.get_indexer(fire_idx, method=None)
        for i in date_to_pos:
            confirm_i = i + confirm_days
            if confirm_i < len(close.index) and still_crossed.iloc[confirm_i]:
                pos.iloc[confirm_i] = 1.0

    pos.name = f"death_star_{short_n}_{long_n}"
    return pos


# ---------------------------------------------------------------------------
# Per-fire forward-return metrics (not aggregate backtest_core — these compute
# the event-study metrics required by spec §B3: MFE, MAE, durable-bottom rate)
# ---------------------------------------------------------------------------

def compute_fire_metrics(
    df: pd.DataFrame,
    pos: pd.Series,
    horizon: int = 21,
    atr_n: int = ATR_N,
    atr_mult: float = ATR_DURABLE_MULT,
) -> pd.DataFrame:
    """Compute per-fire forward metrics for a long-signal position Series.

    For each date t where pos[t] == 1.0 (i.e. a confirmed signal fires), compute:
    - fwd_ret: forward absolute return over [t+1, t+horizon] (close[t+horizon] / close[t+1] - 1)
      We use t+1 as entry (next bar, matching backtest_core's shift(1)), t+1+horizon as exit.
      Actually: position is at t's close, enters at t+1's open (approx t+1 close).
      So fwd_ret = close[t+horizon+1] / close[t+1] - 1 ... but we unify to:
      entry_close = close[t+1], exit_close = close[t+1+horizon]
      (horizon bars from entry = the held period).
    - win: fwd_ret > 0
    - mfe: max forward excess close over entry_close within window, / entry_close
    - mae: max adverse close drop from entry_close within window, / entry_close (as positive number)
    - mfe_mae: mfe / mae (NaN if mae == 0)
    - durable: close never revisits below (signal_day_low - atr_mult * ATR(atr_n)) within window

    Parameters
    ----------
    df : DataFrame
        OHLCV frame aligned to pos.
    pos : Series
        Position series from golden_star_signal / placebo_signal.
    horizon : int
        Exit horizon in trading days (default 21).
    atr_n : int
        ATR window for durability check (default 14).
    atr_mult : float
        ATR multiplier for the durable-bottom breach level (default 1.0).

    Returns
    -------
    DataFrame with one row per fire date and columns:
    fire_date, entry_close, exit_close, fwd_ret, win, mfe, mae, mfe_mae, durable.
    """
    from engine.stock_technicals import atr  # noqa: PLC0415

    close = df["close"].sort_index()
    low = df["low"].sort_index() if "low" in df.columns else close
    high = df["high"].sort_index() if "high" in df.columns else close

    atr_series = atr(high, low, close, n=atr_n) if "high" in df.columns else pd.Series(np.nan, index=close.index)

    fire_dates = pos[pos > 0].index
    rows = []
    close_idx = close.index

    for fd in fire_dates:
        t = close_idx.get_loc(fd)  # integer position of fire date
        entry_t = t + 1            # entry bar (next close after signal)
        exit_t = entry_t + horizon # exit bar

        if entry_t >= len(close_idx) or exit_t > len(close_idx):
            continue  # not enough forward bars — skip

        entry_close = close.iloc[entry_t]
        exit_close = close.iloc[min(exit_t, len(close_idx) - 1)]

        window_closes = close.iloc[entry_t: entry_t + horizon + 1]
        if len(window_closes) < 2:
            continue

        fwd_ret = exit_close / entry_close - 1.0
        win = bool(fwd_ret > 0)

        mfe = float((window_closes.max() - entry_close) / entry_close)
        mae = float((entry_close - window_closes.min()) / entry_close)
        mfe_mae = (mfe / mae) if mae > 1e-9 else np.nan

        # durable bottom: signal_day_low - atr_mult * ATR(atr_n) at signal day
        signal_low = low.iloc[t]
        signal_atr = atr_series.iloc[t] if not pd.isna(atr_series.iloc[t]) else (close.iloc[t] * 0.02)
        breach_level = signal_low - atr_mult * signal_atr
        window_closes_for_dur = close.iloc[entry_t: entry_t + horizon + 1]
        durable = bool((window_closes_for_dur >= breach_level).all())

        rows.append({
            "fire_date": fd,
            "entry_close": round(entry_close, 4),
            "exit_close": round(exit_close, 4),
            "fwd_ret": round(fwd_ret, 6),
            "win": win,
            "mfe": round(mfe, 6),
            "mae": round(mae, 6),
            "mfe_mae": round(mfe_mae, 4) if not np.isnan(mfe_mae) else None,
            "durable": durable,
        })

    if not rows:
        return pd.DataFrame(columns=["fire_date", "entry_close", "exit_close",
                                     "fwd_ret", "win", "mfe", "mae", "mfe_mae", "durable"])
    return pd.DataFrame(rows).set_index("fire_date")


# ---------------------------------------------------------------------------
# Placebo null constructor (spec §B4)
# ---------------------------------------------------------------------------

def build_placebo_entries(
    fire_dates: pd.DatetimeIndex,
    universe: dict[str, pd.DataFrame],
    firing_tickers: set[str],
    m_per_fire: int = 1000,
    seed: int = 42,
) -> list[tuple[str, pd.Timestamp]]:
    """Build M=1000 date-and-liquidity-matched placebo entries.

    For each fire date, draw M random (ticker, date) pairs where:
    - The date is within the same calendar week as the fire date
    - The ticker is NOT a firing ticker for this fire date
    - The ticker's dollar_adv(21) is in the same ADV decile as the median firing ADV

    Returns a flat list of (ticker, entry_date) tuples for placebo entries.

    Note: This is a simplified version that matches on calendar week × universe
    membership. Full ADV-decile matching requires the ADV series per date, which is
    expensive to compute for M=1000 × n_fires. We approximate by: same calendar week
    from non-firing tickers.

    Per spec §B4: "block-bootstrap null per metric" — the block bootstrap is applied
    to the DISTRIBUTION of placebo metrics, not individual draws. This function
    generates the raw (ticker, date) pairs; the caller assembles the distribution.
    """
    rng = np.random.default_rng(seed)
    result = []

    # Build a week → available_tickers→DataFrame lookup
    # Key: ISO week string "YYYY-WXX"
    all_tickers = list(universe.keys())

    for fd in fire_dates:
        week_start = fd - pd.Timedelta(days=fd.weekday())
        week_end = week_start + pd.Timedelta(days=6)

        candidates = []
        for tk in all_tickers:
            if tk in firing_tickers:
                continue
            df = universe[tk]
            # find dates in the same calendar week
            mask = (df.index >= week_start) & (df.index <= week_end)
            week_dates = df.index[mask]
            if len(week_dates) > 0:
                candidates.append((tk, week_dates))

        if not candidates:
            continue

        # draw M entries
        drawn = 0
        max_attempts = m_per_fire * 5
        attempts = 0
        while drawn < m_per_fire and attempts < max_attempts:
            attempts += 1
            tk_idx = int(rng.integers(0, len(candidates)))
            tk, wdates = candidates[tk_idx]
            d_idx = int(rng.integers(0, len(wdates)))
            result.append((tk, wdates[d_idx]))
            drawn += 1

    return result


# ---------------------------------------------------------------------------
# Regime split helper (spec §B6 gate 4)
# ---------------------------------------------------------------------------

def regime_split(
    df_spx: pd.DataFrame,
    fire_dates: pd.DatetimeIndex,
    ma_period: int = 200,
) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Split fire_dates into downtrend (below SPX 200dma) and uptrend (above) groups.

    Parameters
    ----------
    df_spx : DataFrame
        SPX OHLCV or close DataFrame.
    fire_dates : DatetimeIndex
        All signal fire dates.
    ma_period : int
        MA period for the SPX trend filter (default 200).

    Returns
    -------
    (downtrend_dates, uptrend_dates) — the two regime subsets of fire_dates.
    """
    from engine.strategy_signals import sma  # noqa: PLC0415
    spx_close = df_spx["close"] if "close" in df_spx.columns else df_spx.iloc[:, 0]
    spx_ma = sma(spx_close, ma_period)
    above_ma = (spx_close > spx_ma).reindex(fire_dates, method="ffill").fillna(False)

    up_dates = fire_dates[above_ma.values]
    down_dates = fire_dates[~above_ma.values]
    return down_dates, up_dates
