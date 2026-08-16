"""SEA event classes — a pure filter over the Signal Episode Atlas's committed store.

``data/stock_events/events_backfill.parquet`` plus ``data/stock_events/live/YYYY-MM.parquet``
is an append-only, bar-by-bar replayable store whose events carry the frozen SEA class
taxonomy (grid x direction x depth-percentile x level x washout-length x alignment). Nothing
is recomputed here: the extraction selects the pilot names, unions the backfill with the
live months, and **honors keep-FIRST** on the store's own key ``(ticker, grid, date,
direction)`` — the store's documented idempotency rule, so a re-run cannot change an event
that was already published.

**The outcome columns are never read.** ``fwd_13w``, ``fwd_26w``, ``fwd_21s``, ``fwd_63s``,
``exc_*``, ``matured*`` are outcome content and belong to PR-3's ruler, not to a W2
artifact; this module selects the classification columns by name and lets everything else
stay in the store.

Grain and known-ts: SEA events are stamped on their own grid (``2B``/``3B``/``W``) at the
bar date the store records, which is the bar the class was computable on — so
``signal_known_ts`` equals the store's ``date`` and ``known_basis`` records the store as the
authority for it rather than a bucket rule this module would otherwise have to invent.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from engine.stock_identity.replay import events as ev

__all__ = ["FAMILY_KEY", "BACKFILL_PATH", "LIVE_DIR", "constants", "load_store", "fires"]

FAMILY_KEY = "sea_event_classes"
BACKFILL_PATH = "data/stock_events/events_backfill.parquet"
LIVE_DIR = "data/stock_events/live"

#: Classification columns only. Outcome columns are deliberately absent.
_KEEP = (
    "ticker", "grid", "date", "direction", "era", "depth_pctile", "depth_window_n",
    "depth_class", "level", "washout_len", "washout_len_class", "align_class",
)
_KEY = ("ticker", "grid", "date", "direction")

#: The store's own key ordering makes an event's identity; SEA's era column is its era pin.
KNOWN_BASIS = "sea_store_bar_date"


def constants() -> dict[str, Any]:
    return {
        "producer": "engine.stock_events -> data/stock_events/{events_backfill,live/*}.parquet",
        "store_key": list(_KEY),
        "idempotency": "keep-FIRST (the store's own documented rule)",
        "columns_read": list(_KEEP),
        "columns_deliberately_not_read": [
            "fwd_13w", "fwd_26w", "fwd_21s", "fwd_63s",
            "exc_13w", "exc_26w", "exc_21s", "exc_63s", "matured", "matured_short",
        ],
        "taxonomy": "frozen SEA class taxonomy (grid x direction x depth x level x washout x align)",
    }


def load_store(repo_root: str | Path, symbols: list[str] | None = None) -> pd.DataFrame:
    """Backfill ∪ live, pilot-filtered, keep-FIRST on the store's key."""
    root = Path(repo_root)
    frames: list[pd.DataFrame] = []
    p = root / BACKFILL_PATH
    if p.exists():
        df = pd.read_parquet(p, columns=list(_KEEP))
        if symbols is not None:
            df = df[df["ticker"].isin(symbols)]
        frames.append(df)
    live = root / LIVE_DIR
    if live.is_dir():
        for f in sorted(live.glob("*.parquet")):
            df = pd.read_parquet(f)
            cols = [c for c in _KEEP if c in df.columns]
            df = df[cols]
            if symbols is not None:
                df = df[df["ticker"].isin(symbols)]
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=list(_KEEP))
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    # keep-FIRST: backfill first, then live months in order — the publication order.
    return out.drop_duplicates(subset=list(_KEY), keep="first").reset_index(drop=True)


def fires(
    store: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hash: str,
    family_first_available: str | None,
) -> list[dict[str, Any]]:
    if store is None or store.empty:
        return []
    sub = store[store["ticker"] == symbol]
    rows: list[dict[str, Any]] = []
    for r in sub.itertuples(index=False):
        ts = pd.Timestamp(r.date)
        rows.append(ev.make_event(
            family_key=FAMILY_KEY,
            producer="engine.stock_events -> data/stock_events",
            family="sea_event_class",
            subtype=f"{r.grid}_{r.direction}",
            stage="CONTEXT",
            symbol=symbol,
            price_plane_id=price_plane_id,
            grain=str(r.grid),
            signal_ts=ts,
            signal_known_ts=ts,
            known_basis=KNOWN_BASIS,
            signal_era=str(r.era),
            family_era=str(r.era),
            detector_spec_hash=spec_hash,
            source_hash=spec_hash,
            field_origin="ledger_recorded",
            provenance_class="R",
            family_first_available=family_first_available,
            scored_authority=False,
            spec_postdates_history=False,
            context={
                "depth_class": str(r.depth_class),
                "level": str(r.level),
                "washout_len_class": str(r.washout_len_class),
                "align_class": int(r.align_class) if pd.notna(r.align_class) else None,
                "depth_window_n": int(r.depth_window_n) if pd.notna(r.depth_window_n) else None,
            },
        ))
    return rows
