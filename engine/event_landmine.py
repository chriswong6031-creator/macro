"""Codex B5: per-name event-window display composition.

Returns a DISPLAY-ONLY block {earnings, fomc_within, debt} describing upcoming
event windows and balance-sheet context derived from pre-loaded inputs.

DISPLAY-ONLY LAW (adjudicated):
  - All returned fields are descriptive facts (dates, amounts, distances in days).
  - No scoring, ranking, sizing, gating, or recommendation language.
  - No LLM calls; every field is deterministically computed from existing data.
  - Fail-soft throughout: missing or malformed inputs return None for that leg.

Three legs:
  earnings    -- next earnings date and calendar-day distance, from earnings.parquet.
                 Reuses the already-loaded earnings dict (same parquet as earnings_blackout).
  fomc_within -- next FOMC decision date and calendar-day distance, from the
                 _FOMC_MEETINGS hardcoded list in engine.catalyst_tone.
  debt        -- near-term debt maturity context: current_debt (<=12 months per EDGAR
                 tag DebtCurrent/LongTermDebtCurrent), long_term_debt, cash, net_debt,
                 all from the most recent quarter in statements_quarterly.parquet.

CPI/NFP leg: SKIPPED -- no pre-computed US macro-release calendar exists in the repo.
FDA/PDUFA leg: SKIPPED -- openFDA is historical-only; no credible free forward source
               found in the repo or publicly available keyless.
# TODO(B5-FDA): add FDA/PDUFA leg when a reliable free forward calendar becomes available.

Coverage caveats:
  - Earnings coverage: names present in data/earnings/earnings.parquet (~nightly refresh).
  - FOMC: hardcoded through 2026-12; refresh _FOMC_MEETINGS in catalyst_tone.py yearly.
  - Debt: names in data/edgar/statements_quarterly.parquet (~1,500 EDGAR filers); absent
    for names not yet crawled by backfill_edgar_quarterly.py.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_num(v: Any) -> float | None:
    """Return float or None; never raise."""
    try:
        f = float(v)
        return f if not (f != f) else None  # exclude NaN
    except (TypeError, ValueError):
        return None


def _r(v: float | None, n: int = 0) -> float | None:
    """Round to n decimal places, or None if v is None."""
    return round(v, n) if v is not None else None


# ---------------------------------------------------------------------------
# FOMC date helper
# ---------------------------------------------------------------------------

def _fomc_dates() -> list[date]:
    """Return FOMC decision dates as a list of date objects.

    Source: engine.catalyst_tone._FOMC_MEETINGS -- hardcoded through 2026-12.
    Deferred import avoids circular-import issues.
    """
    try:
        from engine.catalyst_tone import _FOMC_MEETINGS  # noqa: PLC0415
        return [date.fromisoformat(d) for d in _FOMC_MEETINGS]
    except Exception as exc:  # noqa: BLE001
        log.debug("event_landmine: could not import _FOMC_MEETINGS (%s)", exc)
        return []


# ---------------------------------------------------------------------------
# Per-leg compose helpers
# ---------------------------------------------------------------------------

def _compose_earnings_leg(
    earnings_row: dict | None,
    today: date,
) -> dict | None:
    """Compose the earnings leg from a pre-loaded earnings row.

    Parameters
    ----------
    earnings_row : dict | None
        Row from the earnings.parquet dict keyed by ticker (output of
        stock_fundamentals._load_earnings() or a compatible dict with keys
        next_date, next_time).  None or {} => leg absent.
    today : date
        Reference date for the calendar-day distance calculation.

    Returns
    -------
    dict with keys:
        date  (str)        -- ISO next_date
        tdays (int)        -- calendar days from today to next_date
                             (0=today, positive=future; past dates suppressed)
        time  (str | None) -- pre-market / after-hours / None
    or None when the leg is absent or the date is in the past.

    Note: tdays is CALENDAR days (simple, fast), not trading days. The
    display layer shows the raw integer to give a quick time-horizon read;
    the earnings_blackout module uses trading days for the suppression gate
    (a separate concern).
    """
    if not earnings_row:
        return None
    nd = earnings_row.get("next_date")
    if not nd or nd in ("nan", "", None):
        return None
    try:
        nd_date = date.fromisoformat(str(nd)[:10])
    except ValueError:
        return None
    # Suppress past dates -- same law as earnings_blackout: never display stale past date
    if nd_date < today:
        return None
    tdays = (nd_date - today).days
    nt = earnings_row.get("next_time")
    tmap = {"time-pre-market": "pre-market", "time-after-hours": "after-hours"}
    time_str = tmap.get(str(nt)) if nt and str(nt) not in ("nan", "", "None") else None
    return {"date": str(nd)[:10], "tdays": tdays, "time": time_str}


def _compose_fomc_leg(
    today: date,
    fomc_dates: list[date] | None = None,
) -> dict | None:
    """Compose the FOMC leg.

    Returns the next FOMC decision on or after today with its calendar-day distance.

    Parameters
    ----------
    today : date
        Reference date.
    fomc_dates : list[date] | None
        Override list for testability; if None, uses _fomc_dates().

    Returns
    -------
    dict with keys:
        date  (str) -- ISO date of next FOMC decision
        tdays (int) -- calendar days from today (0 = same day)
    or None when no future FOMC date is in the list.
    """
    dates = fomc_dates if fomc_dates is not None else _fomc_dates()
    future = sorted(d for d in dates if d >= today)
    if not future:
        return None
    nxt = future[0]
    return {"date": nxt.isoformat(), "tdays": (nxt - today).days}


def _compose_debt_leg(
    quarterly_df: pd.DataFrame | None,
    ticker: str,
) -> dict | None:
    """Compose the debt-maturity proximity leg from the EDGAR quarterly store.

    Extracts the most recent quarter's balance-sheet debt metrics for the ticker.

    Fields in the returned dict:
        current_debt    -- debt due within ~12 months (EDGAR DebtCurrent tag), USD
        long_term_debt  -- non-current long-term debt (LongTermDebtNoncurrent), USD
        cash            -- cash and equivalents, USD
        net_debt        -- current_debt + long_term_debt - cash (pre-computed by crawl)
        period_end      -- statement period end date (ISO string)
        filed           -- SEC filing date (ISO string)

    All monetary amounts are in raw USD as reported (same units as EDGAR XBRL).
    None for individual fields means the EDGAR tag was absent for that ticker/period.
    The leg itself is None when the ticker is not in the store or all
    debt/cash fields are absent.

    Source: data/edgar/statements_quarterly.parquet (written by
    scripts/backfill_edgar_quarterly.py, columns added by PR #1782).
    Coverage: ~1,500 EDGAR filers; absent for un-crawled names.
    """
    if quarterly_df is None or quarterly_df.empty:
        return None
    tk = ticker.upper()
    rows = quarterly_df[quarterly_df["ticker"] == tk]
    if rows.empty:
        return None
    try:
        latest = rows.sort_values("period_end").iloc[-1]
    except Exception:  # noqa: BLE001
        return None

    ltd = _safe_num(latest.get("long_term_debt"))
    cur = _safe_num(latest.get("current_debt"))
    cash = _safe_num(latest.get("cash"))
    net = _safe_num(latest.get("net_debt"))

    # Absent leg: no debt fields at all and no cash either
    if ltd is None and cur is None and cash is None:
        return None

    period_end = str(latest.get("period_end", ""))[:10] or None
    filed = str(latest.get("filed", ""))[:10] or None

    return {
        "current_debt":   _r(cur, 0),
        "long_term_debt": _r(ltd, 0),
        "cash":           _r(cash, 0),
        "net_debt":       _r(net, 0),
        "period_end":     period_end,
        "filed":          filed,
    }


# ---------------------------------------------------------------------------
# Main compose entry point
# ---------------------------------------------------------------------------

def compose(
    ticker: str,
    earnings_row: dict | None,
    quarterly_df: pd.DataFrame | None,
    today: date | None = None,
    fomc_dates: list[date] | None = None,
) -> dict | None:
    """Compose the per-name event-windows block for the stock detail page.

    This is a pure compose function: it takes pre-loaded inputs and returns
    a descriptive dict.  All I/O (parquet loads) must happen in the caller.

    Parameters
    ----------
    ticker : str
        Ticker (case-insensitive).
    earnings_row : dict | None
        Pre-loaded earnings row for this ticker (from stock_fundamentals._load_earnings()
        or engine.earnings_blackout store).  Passed in so the caller loads once and
        reuses across many tickers.  Expected keys: next_date, next_time.
    quarterly_df : pd.DataFrame | None
        Pre-loaded statements_quarterly.parquet DataFrame (load once per run).
        Passed in so the caller does not re-read the parquet per ticker.
    today : date | None
        Reference date (defaults to date.today()).
    fomc_dates : list[date] | None
        Override FOMC date list (for tests; None = import from catalyst_tone).

    Returns
    -------
    dict with keys:
        earnings      (dict | None) -- {date, tdays, time}
        fomc_within   (dict | None) -- {date, tdays}
        debt          (dict | None) -- {current_debt, long_term_debt, cash,
                                         net_debt, period_end, filed}
        _display_only (bool)        -- always True; firewall marker for callers
    or None when all three legs are absent.

    Individual legs are None when their input is missing; the caller / template
    must handle each leg independently.
    """
    today_date = today or date.today()

    earnings_leg = None
    try:
        earnings_leg = _compose_earnings_leg(earnings_row, today_date)
    except Exception as exc:  # noqa: BLE001
        log.debug("event_landmine: earnings leg failed for %s (%s)", ticker, exc)

    fomc_leg = None
    try:
        fomc_leg = _compose_fomc_leg(today_date, fomc_dates)
    except Exception as exc:  # noqa: BLE001
        log.debug("event_landmine: fomc leg failed for %s (%s)", ticker, exc)

    debt_leg = None
    try:
        debt_leg = _compose_debt_leg(quarterly_df, ticker)
    except Exception as exc:  # noqa: BLE001
        log.debug("event_landmine: debt leg failed for %s (%s)", ticker, exc)

    if earnings_leg is None and fomc_leg is None and debt_leg is None:
        return None

    return {
        "earnings":    earnings_leg,
        "fomc_within": fomc_leg,
        "debt":        debt_leg,
        "_display_only": True,
    }


def load_quarterly_df(path: str | None = None) -> pd.DataFrame | None:
    """Load statements_quarterly.parquet once, with graceful failure.

    Callers in panels() already open this file for capital_allocation -- pass
    the ``_quarterly_df`` from that closure rather than calling this again.

    This helper exists for standalone / test callers that do not have the
    pre-loaded DataFrame available.
    """
    import pathlib  # noqa: PLC0415
    from lib import config  # noqa: PLC0415
    p = (config.data_dir() / "edgar" / "statements_quarterly.parquet"
         if path is None else pathlib.Path(path))
    try:
        if not p.exists():
            return None
        return pd.read_parquet(str(p))
    except Exception as exc:  # noqa: BLE001
        log.warning("event_landmine: could not load quarterly parquet (%s)", exc)
        return None
