"""Append-only PIT store helpers for the per-name drip caches (zt_pool, margin_detail, LHB, …).

Historically each drip collector did ``pd.DataFrame(rows).to_parquet(OUT)`` — a SNAPSHOT overwrite
that kept exactly ONE date on disk. That is fine for a "today's picture" display but destroys the
point-in-time record needed to (a) stamp a pinned-at-limit entry flag against the date it was true,
(b) back a future 连板 (consecutive-board) chase-veto, and (c) grade any drip-derived signal without
look-ahead. CN-1 masterplan §W6-CN converts them to APPEND-ONLY, keyed by their natural PIT date.

Two functions keep the change safe for existing consumers:
  • append_snapshot(path, rows, date_col) — concat today's rows onto the on-disk history and de-dup
    by (date_col, ticker) keep-LAST (a same-day re-collect corrects, never duplicates); returns the
    number of rows for the LATEST date (what the collector used to write).
  • latest_snapshot(df, date_col) — the newest-date slice, so a consumer that expects a single-day
    per-ticker snapshot reads exactly what it read before the store grew a history dimension.

Append-only, keep-last-per-day, never raises fatally on the collector path.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def latest_snapshot(df: pd.DataFrame | None, date_col: str = "date") -> pd.DataFrame | None:
    """Return only the rows of the MOST RECENT ``date_col`` value — the single-day snapshot every
    legacy drip consumer expects. Passes df through unchanged if the column is absent (older files)."""
    if df is None or df.empty or date_col not in df.columns:
        return df
    dates = df[date_col].dropna().astype(str)
    if dates.empty:
        return df
    return df[df[date_col].astype(str) == dates.max()]


def append_snapshot(path: Path, rows: list[dict] | pd.DataFrame, date_col: str = "date") -> int:
    """Append ``rows`` to the append-only history at ``path``, de-duping (date_col, ticker) keep-LAST.

    Returns the row count for the LATEST date after the merge (the number the snapshot collectors
    used to report). Best-effort — logs and returns 0 on any write failure, never raises."""
    new = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if new is None or new.empty:
        return 0
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            prior = pd.read_parquet(path)
            # a same-day re-collect must CORRECT, not duplicate → keep-last on (date, ticker).
            key = [c for c in (date_col, "ticker") if c in new.columns and c in prior.columns]
            combined = pd.concat([prior, new], ignore_index=True)
            if key:
                combined = combined.drop_duplicates(subset=key, keep="last")
        else:
            combined = new
        combined.to_parquet(path, index=False)
        latest = latest_snapshot(combined, date_col)
        return int(len(latest)) if latest is not None else 0
    except Exception as e:  # noqa: BLE001 — drip persistence is telemetry, never fatal
        log.warning("append_snapshot(%s) failed: %s", path, e)
        return 0
