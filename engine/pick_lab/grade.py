"""Pick Lab maturation pass — grade fired picks against the price store (spec §4).

Public API
----------
resolve_exec_session(ticker, fire_date, date_index, panel, fill_window=0)
    -> ('resolved', exec_date, exec_close) | ('deferred',) | ('void',)
    Shared helper for exec-session resolution with optional fill window.
    Used by grade_fires internally and by the HK wrapper for pre-scan.

grade_fires(fires, close_panel, spy_closes, sector_closes=None,
            hold_thesis=False, already_graded=None, high_panel=None,
            low_panel=None, exec_price_fn=None, exec_fill_window=0,
            halt_grade_to_last_trade=False) -> tuple[list[dict], int]
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

exec_price_fn (optional):
  Called with (ticker, exec_date) -> Optional[float].  A non-None positive return
  REPLACES the exec-session close as exec_price.  None → fall back to panel close.

exec_fill_window (int, default 0):
  When the exec session's price is None/NaN, search FORWARD up to exec_fill_window
  sessions for the ticker's first non-NaN close.  That session becomes exec_date
  (and exec_price = its close, still overridable by exec_price_fn).
  Deferral: if fewer than exec_fill_window sessions past the natural exec session
  exist in the panel, the fire is silently skipped (retry later).
  Only when >= exec_fill_window sessions have elapsed with no print is the fire
  counted ungradeable at this layer.

halt_grade_to_last_trade (bool, default False):
  When a horizon target session has elapsed but the ticker's price there is NaN:
  look back within (exec_date, target_date] for the last non-NaN close; if found,
  grade to that price and set row['halted']=True.  If none found, current ungradeable.
  When True, ALL ret rows carry an explicit 'halted' key (False default).
  When False (US/CN), the 'halted' key is not added (schema unchanged).

Path rows (kind='path'):
  Emitted per fire (entry books only, not hold_thesis) at two windows: path-25 and path-63.
  A path-w row is emitted only when exec + w sessions have FULLY elapsed.
  Fields: engine_id, ticker, fire_date, horizon (25|63), kind='path', exec_date,
  exec_price, mfe, mae, t_mfe, t_mae, mfe_hl, mae_hl, mae_before_mfe,
  sessions_underwater, matured=True, graded_at, authority='display_only'.

Sector benchmark:
  Try the _GICS_ETF map from engine.ai_desk (reuses same map the suite uses).
  The fire row's 'sector' field is used to look up the ETF ticker.
  ETF closes come from the same close_panel (if present) — no separate I/O.
  If the ETF is absent from close_panel, ret_rel_sector is null (honest null).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Horizons per book type (spec §4, PL-R3)
ENTRY_HORIZONS = (5, 10, 21, 63)
LH_HORIZONS = (126, 252)
MFE_MAE_SESSIONS = 25  # MFE/MAE window (entry books only)

# Path-row windows emitted per fire (entry books only)
PATH_WINDOWS = (25, 63)

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


def _price_at(ticker: str, date: pd.Timestamp, panel: pd.DataFrame) -> Optional[float]:
    """Return price for ticker at date; None if missing or NaN."""
    if ticker not in panel.columns:
        return None
    try:
        val = panel.at[date, ticker]
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
    panel: pd.DataFrame,
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
    return _price_at(ticker, target_date, panel)  # None = NaN/missing at elapsed date


def resolve_exec_session(
    ticker: str,
    fire_date: pd.Timestamp,
    date_index: pd.DatetimeIndex,
    panel: pd.DataFrame,
    fill_window: int = 0,
) -> tuple:
    """Resolve the exec session for a fire, optionally filling forward on halts.

    Parameters
    ----------
    ticker      : Ticker symbol (must be in panel for a result).
    fire_date   : The fire date; exec = next session strictly after this.
    date_index  : Sorted DatetimeIndex of trading sessions.
    panel       : DataFrame[date_index x ticker] of daily closes.
    fill_window : Number of sessions forward to search when exec-session price is
                  None/NaN.  0 = no fill (US/CN behaviour).

    Returns
    -------
    ('resolved', exec_date, exec_close)
        exec_date  : pd.Timestamp of the resolved exec session.
        exec_close : float close at that session (from panel; may be overridden by
                     exec_price_fn in the caller).
    ('deferred',)
        The natural exec session exists but price is NaN, and fewer than fill_window
        sessions have elapsed past it — cannot resolve yet; skip and retry later.
    ('void',)
        fill_window sessions have elapsed past the natural exec session with no
        print, OR the natural exec session has a NaN print with fill_window=0.
        (A fire whose natural exec session is not yet in the panel is 'deferred'.)
    """
    # Natural exec session
    natural_exec = _next_session(fire_date, date_index)
    if natural_exec is None:
        # No session after fire_date yet — not gradeable (not a void, just deferred)
        return ("deferred",)

    exec_price = _price_at(ticker, natural_exec, panel)
    if exec_price is not None:
        # Happy path: exec session has a print
        return ("resolved", natural_exec, exec_price)

    # exec session exists but price is NaN/missing
    if fill_window == 0:
        # No fill allowed — this fire is ungradeable
        return ("void",)

    # Search forward up to fill_window sessions past the natural exec session
    natural_exec_pos = int(date_index.searchsorted(natural_exec, side="left"))
    sessions_past = len(date_index) - (natural_exec_pos + 1)

    if sessions_past < fill_window:
        # Not enough sessions have elapsed to declare void — defer (retry later)
        return ("deferred",)

    # fill_window sessions have elapsed — search for first non-NaN close
    for offset in range(1, fill_window + 1):
        candidate_pos = natural_exec_pos + offset
        if candidate_pos >= len(date_index):
            break
        candidate_date = date_index[candidate_pos]
        p = _price_at(ticker, candidate_date, panel)
        if p is not None:
            return ("resolved", candidate_date, p)

    # fill_window elapsed with no print → void
    return ("void",)


def _compute_path_metrics(
    ticker: str,
    exec_date: pd.Timestamp,
    exec_price: float,
    window: int,
    date_index: pd.DatetimeIndex,
    close_panel: pd.DataFrame,
    high_panel: Optional[pd.DataFrame],
    low_panel: Optional[pd.DataFrame],
) -> Optional[dict]:
    """Compute path metrics over [exec+1, exec+window] for a given window size.

    Returns None if exec+window has not fully elapsed.

    Fields returned:
      mfe, mae             — close-based max/min pct vs exec_price
      t_mfe, t_mae         — 1-based session index of close peak/trough
      mfe_hl, mae_hl       — intraday versions (None if panels absent or ticker missing)
      mae_before_mfe       — bool, t_mae < t_mfe (close-based)
      sessions_underwater  — count of sessions with close < exec_price
    """
    exec_pos = int(date_index.searchsorted(exec_date, side="left"))
    end_pos = exec_pos + window
    if end_pos >= len(date_index):
        return None  # not elapsed yet

    if ticker not in close_panel.columns:
        return None

    window_dates = date_index[exec_pos + 1: end_pos + 1]
    try:
        closes = close_panel.loc[window_dates, ticker]
    except KeyError:
        return None

    if closes.empty or closes.isna().all():
        return None

    rets = (closes - exec_price) / exec_price

    # Close-based MFE/MAE
    mfe_val = float(rets.max())
    mae_val = float(rets.min())

    # 1-based session index of peak/trough
    t_mfe_val = int(rets.argmax()) + 1
    t_mae_val = int(rets.argmin()) + 1

    # Intraday MFE (high panel) and MAE (low panel)
    mfe_hl: Optional[float] = None
    mae_hl: Optional[float] = None

    if high_panel is not None and ticker in high_panel.columns:
        try:
            highs = high_panel.loc[window_dates, ticker].dropna()
            if not highs.empty:
                hl_rets_hi = (highs - exec_price) / exec_price
                mfe_hl = float(hl_rets_hi.max())
        except KeyError:
            pass

    if low_panel is not None and ticker in low_panel.columns:
        try:
            lows = low_panel.loc[window_dates, ticker].dropna()
            if not lows.empty:
                hl_rets_lo = (lows - exec_price) / exec_price
                mae_hl = float(hl_rets_lo.min())
        except KeyError:
            pass

    sessions_underwater = int((rets < 0).sum())

    return {
        "mfe": round(mfe_val, 6),
        "mae": round(mae_val, 6),
        "t_mfe": t_mfe_val,
        "t_mae": t_mae_val,
        "mfe_hl": round(mfe_hl, 6) if mfe_hl is not None else None,
        "mae_hl": round(mae_hl, 6) if mae_hl is not None else None,
        "mae_before_mfe": bool(t_mae_val < t_mfe_val),
        "sessions_underwater": sessions_underwater,
    }


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
    high_panel: Optional[pd.DataFrame] = None,
    low_panel: Optional[pd.DataFrame] = None,
    exec_price_fn: Optional[Callable[[str, pd.Timestamp], Optional[float]]] = None,
    exec_fill_window: int = 0,
    halt_grade_to_last_trade: bool = False,
) -> tuple[list[dict], int]:
    """Grade eligible fires.

    Parameters
    ----------
    fires            : Fire rows from the ledger (already keep-first deduped).
    close_panel      : DataFrame[date_index x ticker] of daily closes.
                       Must contain 'SPY' column if spy_closes not provided separately.
                       Also used for sector ETF closes.
    spy_closes       : Series[DatetimeIndex] of SPY daily closes (or benchmark).
    sector_closes    : Optional additional DataFrame for sector ETF closes.
                       If None, falls back to close_panel for sector ETFs.
    hold_thesis      : If True, use LH horizons (126, 252); else entry horizons.
                       Path rows are only emitted for entry (not hold_thesis) fires.
    already_graded   : Set of (engine_id, ticker, fire_date, horizon, kind) keys
                       already in the grades ledger; used to skip re-grading.
                       kind defaults to 'ret' when missing (legacy rows).
    high_panel       : Optional DataFrame[date_index x ticker] of daily highs;
                       used for intraday MFE on path rows (mfe_hl).
    low_panel        : Optional DataFrame[date_index x ticker] of daily lows;
                       used for intraday MAE on path rows (mae_hl).
    exec_price_fn    : Optional callable (ticker, exec_date) -> Optional[float].
                       When provided and returns a non-None positive value, that value
                       REPLACES the exec-session close as exec_price.  None → fall
                       back to panel close (current US/CN behaviour).
    exec_fill_window : When the exec session's price is NaN, search FORWARD up to
                       this many sessions for the ticker's first non-NaN close.
                       0 = no fill (US/CN default).  See resolve_exec_session for
                       deferral/void semantics.
    halt_grade_to_last_trade : When True and a horizon target session has elapsed but
                       the ticker's price is NaN/missing, look back within
                       (exec_date, target_date] for the last non-NaN close and grade
                       to it with row['halted']=True.  When True, ALL ret rows carry
                       an explicit 'halted' key (False default).  When False
                       (US/CN), the 'halted' key is not added (schema unchanged).

    Returns
    -------
    (grade_rows, n_ungradeable)
      grade_rows    : list of grade dicts ready for append_grades()
      n_ungradeable : count of fires skipped because ticker absent from panel
                      (counted once per fire, not once per horizon)
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

        # Resolve exec session (with optional fill window)
        res = resolve_exec_session(ticker, fire_date, date_index, combined_panel, exec_fill_window)
        if res[0] == "deferred":
            # Not enough sessions elapsed to determine exec — skip, retry later
            continue
        if res[0] == "void":
            # Exec session has no print after fill_window elapsed — ungradeable
            log.debug(
                "grade: ticker %s exec void after fill_window=%d sessions; ungradeable",
                ticker, exec_fill_window,
            )
            n_ungradeable += 1
            continue

        # res[0] == 'resolved'
        exec_date: pd.Timestamp = res[1]
        exec_price: float = res[2]

        # Allow caller to override exec_price (e.g. CN hl2 fill)
        if exec_price_fn is not None:
            override = exec_price_fn(ticker, exec_date)
            if override is not None and override > 0:
                exec_price = float(override)

        # Sector ETF for rel_sector benchmark
        sector_etf = _GICS_ETF.get(sector) if sector else None

        # ── Return rows (one per horizon) ─────────────────────────────────────
        for h in horizons:
            # Dedup key includes kind='ret'
            grade_key = (engine_id, ticker, str(fire_date.date()), h, "ret")
            if grade_key in already_graded:
                continue

            # Price at exec + h sessions
            price_h_result = _price_nth_session(ticker, exec_date, h, date_index, combined_panel)
            if price_h_result is _NOT_YET_ELAPSED:
                # Target session not yet in the panel — skip, retry later
                continue
            if price_h_result is None:
                # Target session is in the panel but ticker price is NaN/missing
                if halt_grade_to_last_trade:
                    # Look back within (exec_date, target_date] for last non-NaN close
                    exec_pos = int(date_index.searchsorted(exec_date, side="left"))
                    target_pos = exec_pos + h
                    # target_pos is in-bounds since price_h_result was None (not sentinel)
                    price_h_result = None
                    for back_pos in range(target_pos - 1, exec_pos, -1):
                        candidate = _price_at(ticker, date_index[back_pos], combined_panel)
                        if candidate is not None:
                            price_h_result = candidate
                            break
                    if price_h_result is None:
                        n_ungradeable += 1
                        continue
                    price_h: float = price_h_result
                    is_halted = True
                else:
                    # count as ungradeable at this horizon per spec §4
                    n_ungradeable += 1
                    continue
            else:
                price_h = price_h_result
                is_halted = False

            # SPY return over same window.
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
            # Kept on return rows for spec continuity (null-honest when not elapsed).
            mfe: Optional[float] = None
            mae: Optional[float] = None
            if not hold_thesis:
                mfe, mae = _compute_mfe_mae(ticker, exec_date, exec_price, date_index, combined_panel)

            row: dict = {
                "engine_id": engine_id,
                "ticker": ticker,
                "fire_date": str(fire_date.date()),
                "horizon": h,
                "kind": "ret",
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
            if halt_grade_to_last_trade:
                row["halted"] = is_halted
            grade_rows.append(row)
            already_graded.add(grade_key)

        # ── Path rows (entry books only; two windows: 25, 63) ─────────────────
        if not hold_thesis:
            for w in PATH_WINDOWS:
                path_key = (engine_id, ticker, str(fire_date.date()), w, "path")
                if path_key in already_graded:
                    continue

                metrics = _compute_path_metrics(
                    ticker, exec_date, exec_price, w,
                    date_index, combined_panel,
                    high_panel, low_panel,
                )
                if metrics is None:
                    # Window not yet elapsed — skip, retry later
                    continue

                path_row: dict = {
                    "engine_id": engine_id,
                    "ticker": ticker,
                    "fire_date": str(fire_date.date()),
                    "horizon": w,
                    "kind": "path",
                    "exec_date": str(exec_date.date()),
                    "exec_price": round(exec_price, 4),
                    "mfe": metrics["mfe"],
                    "mae": metrics["mae"],
                    "t_mfe": metrics["t_mfe"],
                    "t_mae": metrics["t_mae"],
                    "mfe_hl": metrics["mfe_hl"],
                    "mae_hl": metrics["mae_hl"],
                    "mae_before_mfe": metrics["mae_before_mfe"],
                    "sessions_underwater": metrics["sessions_underwater"],
                    "matured": True,
                    "graded_at": graded_at,
                    "authority": "display_only",
                }
                grade_rows.append(path_row)
                already_graded.add(path_key)

    if n_ungradeable:
        log.info(
            "grade_fires: %d fires ungradeable (ticker absent from panel)",
            n_ungradeable,
        )

    return grade_rows, n_ungradeable
