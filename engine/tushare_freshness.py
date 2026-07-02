"""Asof-aware Tushare-vs-free-fallback preference + a consume-time staleness badge.

THE BUG (masterplan §W6-CN fix 4): the gated Tushare drip plane (``data/tushare/*.parquet``)
was PREFERRED over fresh free fallbacks on FILE PRESENCE ALONE — never asof. When the
Tushare token drops out of the collection environment the client no-ops silently
(``collectors/tushare_client.query`` returns None with no token), so the last committed
Tushare parquet freezes in place. Consumers kept reading that frozen plane in preference
to the free siblings that were updating daily — inverted source preference: STALE gated
beats FRESH free. (Live 2026-07-01: all ``data/tushare/*`` stuck at 2026-06-18/06-21 while
``china_a_val`` etc. read 2026-06-30/07-01.)

THE FIX: prefer Tushare only when its data-through date is within ``max_lag_sessions`` of
the free source's — otherwise fall back to the fresh free plane. Also exposes the Tushare
plane's data-through date so run_status/health can register it and surfaces can render a
staleness badge.

Pure/best-effort: any parse issue degrades to "unknown asof" which, being conservative,
DE-prefers Tushare (fresh free wins) rather than silently trusting a stale gated file.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config

log = logging.getLogger("tushare_freshness")

# A Tushare drip may legitimately lag the free daily by one session (its cron runs on a
# different lane); beyond that it is stale and the fresh free source should win.
DEFAULT_MAX_LAG_SESSIONS = 1

# Column names that carry a Tushare frame's data-through date, most-authoritative first.
# trade_date = the actual market session the row describes (the honest data-through date).
# ann_date = announcement date (forecast/report tables — when the number became public).
# NOTE: end_date is a reporting-PERIOD end (e.g. the fiscal quarter a forecast covers), NOT a
# data-through date — it runs AHEAD of announcement, so it must rank LAST or it overstates
# freshness (a forecast frozen since its ann_date would read fresh-through its period end).
# asof/date are build stamps (later than the data), so they sit below the true market dates
# but above end_date.
_ASOF_COLS = ("trade_date", "ann_date", "date", "asof", "end_date")


def frame_asof(df: pd.DataFrame | None) -> pd.Timestamp | None:
    """The data-through date of a stored frame (max over its date-ish column/index).

    Reads ``trade_date`` in preference to the build ``asof`` — a frozen Tushare plane
    still stamps a fresh ``asof`` at each no-op build, so ``asof`` would MASK the freeze;
    ``trade_date`` is the honest market-session date. None if undatable."""
    if df is None or len(df) == 0:
        return None
    for col in _ASOF_COLS:
        if col in df.columns:
            s = pd.to_datetime(df[col].astype(str), errors="coerce", format="mixed")
            if s.notna().any():
                return s.max().normalize()
    idx = getattr(df, "index", None)
    if isinstance(idx, pd.DatetimeIndex) and len(idx):
        return idx.max().normalize()
    return None


def tushare_asof(table: str) -> pd.Timestamp | None:
    """data-through date of ``data/tushare/<table>.parquet`` (via frame_asof). None if absent."""
    p = config.data_dir() / "tushare" / f"{table}.parquet"
    if not p.exists():
        return None
    try:
        return frame_asof(pd.read_parquet(p))
    except Exception as e:  # noqa: BLE001 — a broken cache must never break a build
        log.warning("tushare_freshness: %s unreadable (%s)", table, e)
        return None


def prefer_tushare(tushare_df: pd.DataFrame | None, free_df: pd.DataFrame | None, *,
                   max_lag_sessions: int = DEFAULT_MAX_LAG_SESSIONS) -> tuple[pd.DataFrame | None, str]:
    """Choose between a gated Tushare frame and a free-fallback frame, ASOF-AWARE.

    Returns ``(chosen_df, source)`` where source ∈ {"tushare", "free", "none"}. Tushare
    wins only when present AND its data-through date is no more than ``max_lag_sessions``
    calendar days behind the free source's (or the free source is itself undatable/missing).
    A frozen Tushare plane (older than the gate) loses to a fresh free frame. Conservative:
    an undatable Tushare frame de-prefers itself.
    """
    if tushare_df is None or len(tushare_df) == 0:
        return (free_df, "free" if free_df is not None else "none")
    if free_df is None or len(free_df) == 0:
        return (tushare_df, "tushare")          # nothing fresher to compare against
    t_as, f_as = frame_asof(tushare_df), frame_asof(free_df)
    if t_as is None:                            # can't date Tushare → don't trust it over fresh free
        return (free_df, "free")
    if f_as is None:                            # can't date free → keep Tushare (its own asof known)
        return (tushare_df, "tushare")
    lag = (f_as - t_as).days
    if lag > max_lag_sessions:
        log.info("tushare_freshness: Tushare stale (through %s, free through %s, lag %dd > %d) — using free",
                 t_as.date(), f_as.date(), lag, max_lag_sessions)
        return (free_df, "free")
    return (tushare_df, "tushare")


def staleness_badge(table: str, *, expected_cadence_days: int = 1,
                    ref: pd.Timestamp | None = None) -> dict:
    """Consume-time freshness descriptor for a Tushare table:
    ``{table, asof, lag_days, state}`` with state ∈ {fresh, slow, stale, dead}. ``ref`` is
    the comparison date (default: today, UTC). ``dead`` = >10× cadence or missing."""
    ref = (ref or pd.Timestamp.utcnow()).normalize()
    asof = tushare_asof(table)
    if asof is None:
        return {"table": table, "asof": None, "lag_days": None, "state": "dead"}
    lag = int((ref - asof).days)
    if lag <= expected_cadence_days:
        state = "fresh"
    elif lag <= expected_cadence_days * 3:
        state = "slow"
    elif lag <= expected_cadence_days * 10:
        state = "stale"
    else:
        state = "dead"
    return {"table": table, "asof": str(asof.date()), "lag_days": lag, "state": state}
