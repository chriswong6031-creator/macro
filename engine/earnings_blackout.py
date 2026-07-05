"""Entry-Stack W1.5 — Earnings-blackout hygiene veto.

Per-name assessment from data/earnings/earnings.parquet.

PER-ROW LAW (adjudicated 2026-07-05):
  - Candidate rows require next_date >= today.  Rows with next_date < today
    are DROPPED (stale past date — NEVER veto on a passed date).
  - in_blackout iff 0 <= trading_days(today -> next_date) <= 3
    AND the row is fresh (as_of within 10 trading days of today).
  - days_to_earnings is the trading-day distance (integer, None if unavailable).

FAIL-OPEN law: missing store / missing ticker / stale row => in_blackout=False
with stale flag set.  The veto NEVER blocks a board build.

LIVE SEMANTICS: key on next_date (+ next_time where present),
NEVER on 8-K filing calendar dates.  Same-day 8-Ks are mostly filed
after-hours; the live veto must never block an already-announced name.

Returns a dict:
  {
    "in_blackout": bool,
    "days_to_earnings": int | None,
    "next_date": str | None,
    "next_time": str | None,
    "as_of_age_td": int | None,
    "stale": bool,
    "reason": str,           # brief diagnostic
  }

Store-level staleness (file-level as_of older than 10 trading days):
  in_blackout=False for all names; callers should display a staleness warning
  and suppress NOTHING.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────
_BLACKOUT_K = 3         # pre-registered primary (k=3)
_STALE_AGE_TD = 10      # trading days: as_of older than this => stale
_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "earnings" / "earnings.parquet"

# Module-level cache so repeated calls per build don't re-parse the parquet.
_cached_store: pd.DataFrame | None = None
_cached_store_path: str | None = None
_cached_td_calendar: pd.DatetimeIndex | None = None


def _load_store(store_path: Path | None = None) -> pd.DataFrame:
    """Load (and cache) the earnings parquet.  Returns empty df on any error."""
    global _cached_store, _cached_store_path  # noqa: PLW0603
    path = store_path or _STORE_PATH
    path_str = str(path)
    if _cached_store is not None and _cached_store_path == path_str:
        return _cached_store
    try:
        df = pd.read_parquet(path)
        # Normalise index to upper-case tickers for robust lookup.
        df.index = df.index.str.upper()
        _cached_store = df
        _cached_store_path = path_str
        return df
    except FileNotFoundError:
        log.debug("earnings_blackout: store not found at %s — fail-open", path)
        return pd.DataFrame()
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_blackout: failed to load store (%s) — fail-open", exc)
        return pd.DataFrame()


def _build_td_calendar() -> pd.DatetimeIndex:
    """Trading-day calendar from deep panel price files, with bdate_range fallback."""
    global _cached_td_calendar  # noqa: PLW0603
    if _cached_td_calendar is not None:
        return _cached_td_calendar
    stocks_dir = _STORE_PATH.parent.parent / "stocks"
    all_dates: set = set()
    try:
        for p in sorted(stocks_dir.glob("*.parquet")):
            try:
                df = pd.read_parquet(p, columns=["close"])
                all_dates.update(df.index.to_list())
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    if not all_dates:
        log.debug("earnings_blackout: no deep-panel files found; using bdate_range fallback")
        cal = pd.bdate_range("1960-01-01", "2030-12-31")
    else:
        cal = pd.DatetimeIndex(sorted(all_dates))
    # Extend with bdate_range for future dates not yet in the price store.
    # The store ends at the last close date; next_date may be in the future.
    last = cal[-1]
    extension_end = last + pd.Timedelta(days=365)
    future = pd.bdate_range(last + pd.Timedelta(days=1), extension_end)
    if len(future):
        cal = cal.append(future)
    _cached_td_calendar = cal
    return cal


def _td_distance(
    from_date: pd.Timestamp,
    to_date: pd.Timestamp,
    td_index: pd.DatetimeIndex,
) -> int | None:
    """Trading days from from_date to to_date (0 = same day, positive = future).

    Returns None when either date falls outside td_index range.
    Uses the same searchsorted-position subtraction as the W1-SEV study
    (scripts/research/run_w1_sev.py:_td_distance), keeping live semantics
    consistent with the historical study.
    """
    from_pos = td_index.searchsorted(from_date, side="left")
    to_pos = td_index.searchsorted(to_date, side="left")
    if from_pos >= len(td_index) or to_pos >= len(td_index):
        return None
    return int(to_pos - from_pos)


def _td_age(from_date: pd.Timestamp, to_date: pd.Timestamp,
            td_index: pd.DatetimeIndex) -> int | None:
    """Trading-day age: how many trading sessions after from_date is to_date.

    Same as _td_distance but we express it as a non-negative age.
    Returns None if not computable.
    """
    d = _td_distance(from_date, to_date, td_index)
    return d if d is not None else None


def _parse_as_of(as_of_str: str) -> pd.Timestamp | None:
    """Parse an ISO-format as_of string, stripping timezone for tz-naive comparison."""
    try:
        ts = pd.Timestamp(as_of_str)
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None) if ts.tzinfo is None else ts.tz_convert(None)
        return ts.normalize()  # midnight, tz-naive
    except Exception:  # noqa: BLE001
        return None


def store_staleness(today: date | None = None,
                    store_path: Path | None = None) -> dict[str, Any]:
    """Return a store-level staleness report.

    Keys:
      stale (bool), as_of_age_td (int|None), as_of_str (str|None),
      store_missing (bool)
    """
    path = store_path or _STORE_PATH
    if not path.exists():
        return {"stale": True, "as_of_age_td": None, "as_of_str": None,
                "store_missing": True}
    df = _load_store(path)
    if df.empty:
        return {"stale": True, "as_of_age_td": None, "as_of_str": None,
                "store_missing": False}
    # Use the most recent as_of across the whole store as the store-level age.
    as_of_col = df.get("as_of")
    if as_of_col is None or as_of_col.empty:
        return {"stale": True, "as_of_age_td": None, "as_of_str": None,
                "store_missing": False}
    # Take the most recent as_of (max, not last row — some runs use two different as_of values)
    try:
        most_recent_str = as_of_col.dropna().max()
    except Exception:  # noqa: BLE001
        return {"stale": True, "as_of_age_td": None, "as_of_str": None,
                "store_missing": False}
    as_of_ts = _parse_as_of(str(most_recent_str))
    if as_of_ts is None:
        return {"stale": True, "as_of_age_td": None, "as_of_str": str(most_recent_str),
                "store_missing": False}
    today_ts = pd.Timestamp(today or date.today()).normalize()
    td_cal = _build_td_calendar()
    age = _td_age(as_of_ts, today_ts, td_cal)
    stale = (age is None) or (age > _STALE_AGE_TD)
    return {"stale": stale, "as_of_age_td": age, "as_of_str": str(most_recent_str),
            "store_missing": False}


def assess(ticker: str,
           today: date | None = None,
           store_path: Path | None = None) -> dict[str, Any]:
    """Assess earnings-blackout status for a single ticker.

    Parameters
    ----------
    ticker : str
        The US equity ticker (case-insensitive).
    today : date | None
        Reference date for 'today' (defaults to date.today()).
    store_path : Path | None
        Override path to earnings.parquet (used in tests).

    Returns
    -------
    dict with keys:
        in_blackout (bool), days_to_earnings (int|None), next_date (str|None),
        next_time (str|None), as_of_age_td (int|None), stale (bool),
        reason (str)
    """
    today_date = today or date.today()
    today_ts = pd.Timestamp(today_date).normalize()

    # ── FAIL-OPEN template ────────────────────────────────────────────────
    def _fail_open(reason: str, stale: bool = True,
                   age: int | None = None) -> dict[str, Any]:
        return {"in_blackout": False, "days_to_earnings": None,
                "next_date": None, "next_time": None,
                "as_of_age_td": age, "stale": stale, "reason": reason}

    # ── Load store ────────────────────────────────────────────────────────
    df = _load_store(store_path)
    if df.empty:
        return _fail_open("store_missing_or_empty")

    # ── Ticker lookup ─────────────────────────────────────────────────────
    tk_upper = ticker.strip().upper()
    if tk_upper not in df.index:
        return _fail_open("ticker_not_in_store", stale=False)

    row = df.loc[tk_upper]
    # Handle duplicate index entries: take the first if multiple
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]

    # ── Parse next_date ───────────────────────────────────────────────────
    next_date_str = row.get("next_date") if hasattr(row, "get") else row["next_date"]
    next_time_val = row.get("next_time") if hasattr(row, "get") else row["next_time"]
    next_time_str: str | None = str(next_time_val) if pd.notna(next_time_val) else None

    if not next_date_str or pd.isna(next_date_str):
        return _fail_open("next_date_missing", stale=False)

    try:
        next_ts = pd.Timestamp(str(next_date_str)).normalize()
    except Exception:  # noqa: BLE001
        return _fail_open("next_date_unparseable", stale=False)

    # ── PER-ROW LAW: DROP passed dates ───────────────────────────────────
    # next_date < today => past announcement => NEVER veto (fail-open)
    if next_ts < today_ts:
        return {"in_blackout": False, "days_to_earnings": None,
                "next_date": str(next_date_str), "next_time": next_time_str,
                "as_of_age_td": None, "stale": False,
                "reason": "next_date_in_past"}

    # ── Parse as_of + check row freshness ────────────────────────────────
    as_of_raw = row.get("as_of") if hasattr(row, "get") else row["as_of"]
    as_of_ts = _parse_as_of(str(as_of_raw)) if (as_of_raw and pd.notna(as_of_raw)) else None

    td_cal = _build_td_calendar()

    if as_of_ts is None:
        # Cannot assess freshness — fail-open
        return _fail_open("as_of_unparseable", stale=True)

    as_of_age = _td_age(as_of_ts, today_ts, td_cal)
    row_stale = (as_of_age is None) or (as_of_age > _STALE_AGE_TD)

    if row_stale:
        # Stale row => fail-open per law
        return {"in_blackout": False, "days_to_earnings": None,
                "next_date": str(next_date_str), "next_time": next_time_str,
                "as_of_age_td": as_of_age, "stale": True,
                "reason": "row_stale"}

    # ── Trading-day distance ──────────────────────────────────────────────
    days_to = _td_distance(today_ts, next_ts, td_cal)

    if days_to is None:
        # Calendar gap — fail-open
        return {"in_blackout": False, "days_to_earnings": None,
                "next_date": str(next_date_str), "next_time": next_time_str,
                "as_of_age_td": as_of_age, "stale": False,
                "reason": "td_calendar_gap"}

    # ── Blackout verdict ──────────────────────────────────────────────────
    in_blackout = 0 <= days_to <= _BLACKOUT_K

    return {
        "in_blackout": in_blackout,
        "days_to_earnings": days_to,
        "next_date": str(next_date_str),
        "next_time": next_time_str,
        "as_of_age_td": as_of_age,
        "stale": False,
        "reason": f"k={_BLACKOUT_K}_blackout" if in_blackout else "outside_window",
    }


def clear_cache() -> None:
    """Reset module-level caches (used in tests to inject a custom store)."""
    global _cached_store, _cached_store_path, _cached_td_calendar  # noqa: PLW0603
    _cached_store = None
    _cached_store_path = None
    _cached_td_calendar = None
