"""Pick Lab maturation pass — grade fired picks against the price store (spec §4).

Public API
----------
grade_fires(fires, close_panel, spy_closes, sector_closes=None,
            hold_thesis=False) -> tuple[list[dict], int]
    Grade all eligible fires and return (new_grade_rows, n_ungradeable).

Rules (spec §4):
  exec_date  = next trading session AFTER fire_date (next row in close_panel index)
  exec_price = exec-session CLOSE (conservative, EOD-only data)
  horizons   = {5, 10, 21, 63} for entry books; {126, 252} for LH books
  Grade h    only when exec + h sessions have FULLY elapsed in the panel
  MFE/MAE    over 25 sessions from exec (entry books ONLY), only when exec+25 elapsed
  ret_abs    = (close[exec+h] - exec_price) / exec_price
  ret_excess_spy = ret_abs - spy_ret_h
  ret_rel_sector = ret_abs - sector_ret_h  (null if no sector benchmark)
  Missing ticker in panel → skip + increment ungradeable counter

Sector benchmark:
  Try the _GICS_ETF map from engine.ai_desk (reuses same map the suite uses).
  The fire row's 'sector' field is used to look up the ETF ticker.
  ETF closes come from the same close_panel (if present) — no separate I/O.
  If the ETF is absent from close_panel, ret_rel_sector is null (honest null).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Horizons per book type (spec §4, PL-R3)
ENTRY_HORIZONS = (5, 10, 21, 63)
LH_HORIZONS = (126, 252)
MFE_MAE_SESSIONS = 25  # MFE/MAE window (entry books only)

# Sector → SPDR ETF map (same as engine.ai_desk._GICS_ETF).
# We define it here so grade.py has no hard import from engine.ai_desk
# (which has heavy optional deps). If they drift, that's a concern flagged below.
_GICS_ETF: dict[str, str] = {
    "Energy": "XLE",
    "Information Technology": "XLK",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}


def _next_session(fire_date: pd.Timestamp, date_index: pd.DatetimeIndex) -> Optional[pd.Timestamp]:
    """Return the first date in date_index strictly after fire_date, or None."""
    future = date_index[date_index > fire_date]
    return future[0] if len(future) else None


def _price_at(ticker: str, date: pd.Timestamp, close_panel: pd.DataFrame) -> Optional[float]:
    """Return close price for ticker at date; None if missing or NaN."""
    if ticker not in close_panel.columns:
        return None
    try:
        val = close_panel.at[date, ticker]
    except KeyError:
        return None
    if pd.isna(val):
        return None
    return float(val)


_NOT_YET_ELAPSED = object()  # sentinel: target session not yet in the panel


def _price_nth_session(
    ticker: str,
    exec_date: pd.Timestamp,
    n: int,
    date_index: pd.DatetimeIndex,
    close_panel: pd.DataFrame,
) -> "float | None | object":
    """Price at exec_date + n sessions (0 = exec_date itself).

    Return values:
      float         — price at the target session
      None          — target session is in the panel but the ticker is NaN/missing
                      (elapsed horizon, permanently ungradeable)
      _NOT_YET_ELAPSED — target session has not appeared in the panel yet
                         (do not grade; retry on a later night)
    """
    exec_pos_arr = date_index.searchsorted(exec_date, side="left")
    exec_pos = int(exec_pos_arr)
    target_pos = exec_pos + n
    if target_pos >= len(date_index):
        return _NOT_YET_ELAPSED  # target session not yet in the panel
    target_date = date_index[target_pos]
    return _price_at(ticker, target_date, close_panel)  # None = NaN/missing at elapsed date


def _compute_mfe_mae(
    ticker: str,
    exec_date: pd.Timestamp,
    exec_price: float,
    date_index: pd.DatetimeIndex,
    close_panel: pd.DataFrame,
) -> tuple[Optional[float], Optional[float]]:
    """MFE and MAE over MFE_MAE_SESSIONS from exec_date.

    Returns (None, None) if exec+MFE_MAE_SESSIONS has not fully elapsed.
    MFE = max( (close[t] - exec_price) / exec_price ) over t in [exec+1, exec+25]
    MAE = min( (close[t] - exec_price) / exec_price ) over t in [exec+1, exec+25]
    """
    exec_pos = int(date_index.searchsorted(exec_date, side="left"))
    end_pos = exec_pos + MFE_MAE_SESSIONS
    if end_pos >= len(date_index):
        return None, None  # not elapsed yet

    if ticker not in close_panel.columns:
        return None, None

    window_dates = date_index[exec_pos + 1: end_pos + 1]
    try:
        closes = close_panel.loc[window_dates, ticker].dropna()
    except KeyError:
        return None, None

    if closes.empty:
        return None, None

    rets = (closes - exec_price) / exec_price
    return float(rets.max()), float(rets.min())


def grade_fires(
    fires: list[dict],
    close_panel: pd.DataFrame,
    spy_closes: pd.Series,
    sector_closes: Optional[pd.DataFrame] = None,
    *,
    hold_thesis: bool = False,
    already_graded: Optional[set[tuple]] = None,
) -> tuple[list[dict], int]:
    """Grade eligible fires.

    Parameters
    ----------
    fires            : Fire rows from the ledger (already keep-first deduped).
    close_panel      : DataFrame[date_index x ticker] of daily closes.
                       Must contain 'SPY' column if spy_closes not provided separately.
                       Also used for sector ETF closes.
    spy_closes       : Series[DatetimeIndex] of SPY daily closes.
    sector_closes    : Optional additional DataFrame for sector ETF closes.
                       If None, falls back to close_panel for sector ETFs.
    hold_thesis      : If True, use LH horizons (126, 252); else entry horizons.
    already_graded   : Set of (engine_id, ticker, fire_date, horizon) keys
                       already in the grades ledger; used to skip re-grading.

    Returns
    -------
    (grade_rows, n_ungradeable)
      grade_rows    : list of grade dicts ready for append_grades()
      n_ungradeable : count of fires skipped because ticker absent from panel
    """
    horizons = LH_HORIZONS if hold_thesis else ENTRY_HORIZONS
    already_graded = already_graded or set()

    # Build a unified date index from close_panel
    date_index: pd.DatetimeIndex = close_panel.index
    if not isinstance(date_index, pd.DatetimeIndex):
        date_index = pd.DatetimeIndex(date_index)
    date_index = date_index.sort_values()

    # Merge sector_closes into close_panel view if provided
    # (avoids mutation of caller's data)
    if sector_closes is not None:
        combined_panel = pd.concat(
            [close_panel, sector_closes[[c for c in sector_closes.columns
                                         if c not in close_panel.columns]]],
            axis=1,
        )
    else:
        combined_panel = close_panel

    graded_at = datetime.now(tz=timezone.utc).isoformat()
    grade_rows: list[dict] = []
    n_ungradeable = 0

    for fire in fires:
        engine_id = fire.get("engine_id", "")
        ticker = str(fire.get("ticker", ""))
        fire_date_raw = fire.get("fire_date")
        sector = fire.get("sector")

        # Parse fire_date
        try:
            fire_date = pd.Timestamp(fire_date_raw)
        except Exception:  # noqa: BLE001
            log.warning("grade: bad fire_date %r for %s/%s; skip", fire_date_raw, engine_id, ticker)
            n_ungradeable += 1
            continue

        # exec_date = next trading session after fire_date
        exec_date = _next_session(fire_date, date_index)
        if exec_date is None:
            # No session after fire_date in panel → not yet gradeable
            continue

        # exec_price = close at exec_date
        exec_price = _price_at(ticker, exec_date, combined_panel)
        if exec_price is None:
            log.debug(
                "grade: ticker %s missing from panel at exec_date %s; ungradeable",
                ticker, exec_date,
            )
            n_ungradeable += 1
            continue

        # Sector ETF for rel_sector benchmark
        sector_etf = _GICS_ETF.get(sector) if sector else None

        for h in horizons:
            grade_key = (engine_id, ticker, str(fire_date.date()), h)
            if grade_key in already_graded:
                continue

            # Price at exec + h sessions
            price_h_result = _price_nth_session(ticker, exec_date, h, date_index, combined_panel)
            if price_h_result is _NOT_YET_ELAPSED:
                # Target session not yet in the panel — skip, retry later
                continue
            if price_h_result is None:
                # Target session is in the panel but ticker price is NaN/missing
                # (delisted / halted) — count as ungradeable at this horizon per spec §4
                n_ungradeable += 1
                continue
            price_h: float = price_h_result

            # SPY return over same window.
            # Use exact-session lookup (same date_index positions as the ticker) so
            # both legs of the excess calculation are measured on identical sessions.
            # Return None on an exact-miss rather than silently substituting a stale
            # prior-day close (which biases excess when SPY has a holiday gap).
            spy_price_exec = None
            spy_price_h = None
            try:
                exec_pos = int(date_index.searchsorted(exec_date, side="left"))
                if exec_pos < len(date_index) and date_index[exec_pos] == exec_date:
                    if exec_date in spy_closes.index:
                        spy_price_exec = float(spy_closes[exec_date])
                target_pos = exec_pos + h
                if target_pos < len(date_index):
                    spy_date_h = date_index[target_pos]
                    if spy_date_h in spy_closes.index:
                        spy_price_h = float(spy_closes[spy_date_h])
            except Exception:  # noqa: BLE001
                pass

            ret_abs = (price_h - exec_price) / exec_price

            if spy_price_exec and spy_price_h:
                ret_excess_spy = ret_abs - (spy_price_h - spy_price_exec) / spy_price_exec
            else:
                ret_excess_spy = None

            # Sector benchmark
            ret_rel_sector = None
            if sector_etf:
                sec_exec = _price_at(sector_etf, exec_date, combined_panel)
                sec_h_result = _price_nth_session(sector_etf, exec_date, h, date_index, combined_panel)
                # Only compute if we have a real float (not sentinel or None)
                sec_h = sec_h_result if (
                    sec_h_result is not None and sec_h_result is not _NOT_YET_ELAPSED
                ) else None
                if sec_exec and sec_h:
                    ret_rel_sector = ret_abs - (sec_h - sec_exec) / sec_exec

            # MFE / MAE (entry books only; spec §4)
            mfe: Optional[float] = None
            mae: Optional[float] = None
            if not hold_thesis:
                mfe, mae = _compute_mfe_mae(ticker, exec_date, exec_price, date_index, combined_panel)

            row: dict = {
                "engine_id": engine_id,
                "ticker": ticker,
                "fire_date": str(fire_date.date()),
                "horizon": h,
                "exec_date": str(exec_date.date()),
                "exec_price": round(exec_price, 4),
                "ret_abs": round(ret_abs, 6) if ret_abs is not None else None,
                "ret_excess_spy": round(ret_excess_spy, 6) if ret_excess_spy is not None else None,
                "ret_rel_sector": round(ret_rel_sector, 6) if ret_rel_sector is not None else None,
                "mfe": round(mfe, 6) if mfe is not None else None,
                "mae": round(mae, 6) if mae is not None else None,
                "matured": True,
                "graded_at": graded_at,
                "authority": "display_only",
            }
            grade_rows.append(row)
            already_graded.add(grade_key)

    if n_ungradeable:
        log.info(
            "grade_fires: %d fires ungradeable (ticker absent from panel)",
            n_ungradeable,
        )

    return grade_rows, n_ungradeable
