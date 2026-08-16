"""Confirmed BUY / REBUY — the ledger arm and the deeper recompute arm.

Two arms, never merged into one undifferentiated series:

**Ledger arm** (``field_origin = ledger_recorded``). ``data/signal_archive/track_record.parquet``
is append-only, keyed ``(ticker, date, type)``, and carries the buy-filter verdict
(``quality`` ∈ take/block plus its ``reason``) — the surface that actually had scored
authority. Extraction is a **pure filter**: no row is mutated, no key is re-derived, and
``scored_authority=True`` records what that surface's authority was, as a fact about the
past and never as a grant.

**Recompute arm** (``field_origin = replay_recomputed``). The ledger covers only the names
that live on the curated ``data/stocks`` plane — measured on this pilot, 9 of 21 names have
ledger rows and 12 have none at all. For those names, and for any history before a name's
first ledger row, the 3D confluence CB is recomputed by the producer's own function
(``signal_quality.signal_frame``'s ``CB`` column). That column is the **pre-filter**
confluence cross, not the filtered take, so it carries its own subtype and
``scored_authority=False``: reading it as "the ledger, extended" would silently promote a
raw cross into a graded verdict. ``spec_postdates_history=True`` is stamped on every row
the ledger does not cover.

``signal_known_ts`` comes from :func:`engine.signal_quality.marker_last_session` — the
producer's OWN knowability function, not an arithmetic offset from the label (its docstring
records a measured case where a busday derivation missed a bucket the frame actually had).

No ruler content: the ledger's forward-return and outcome columns are never read here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.signal_quality import (
    ANCHOR_ERA as SQ_ANCHOR_ERA,
    BUY_RSI_MAX,
    CONF_W,
    MA_LEN,
    OS,
    RSI_LEN,
    marker_last_session,
    signal_frame,
)

from engine.stock_identity.replay import events as ev
from engine.stock_identity.replay.grid import KNOWN_BASIS_BUCKET, macro_grid

__all__ = [
    "LEDGER_PATH",
    "FAMILY_BUY",
    "FAMILY_REBUY",
    "ERA",
    "constants",
    "load_ledger",
    "ledger_fires",
    "recompute_fires",
]

LEDGER_PATH = "data/signal_archive/track_record.parquet"
FAMILY_BUY = "confirmed_buy"
FAMILY_REBUY = "rebuy"
ERA = SQ_ANCHOR_ERA

#: Ledger columns this extraction is allowed to see. Everything else in that store —
#: fwd_ret_*, fwd_mdd_*, fwd_mfe_*, trade_ret, outcome, terminal_state_* — is OUTCOME
#: content, which is PR-3's object and may not enter a W2 artifact.
_LEDGER_COLUMNS = ("ticker", "date", "type", "quality", "reason", "anchor_era",
                   "first_seen_asof")
_LEDGER_TYPES = ("buy", "rebuy")


def constants() -> dict[str, Any]:
    return {
        "producer": "engine.signal_quality:analyze/_buy_filter -> data/signal_archive/track_record.parquet",
        "recompute_producer": "engine.signal_quality:signal_frame.CB",
        "anchor_era": SQ_ANCHOR_ERA,
        "grid_sessions": 3,
        "rsi_len": RSI_LEN,
        "conf_w": CONF_W,
        "os_band": OS,
        "buy_rsi_max": BUY_RSI_MAX,
        "ma_len": MA_LEN,
        "ledger_key": "(ticker, date, type)",
        "ledger_semantics": "append-only; extraction is a pure filter, keep-FIRST honored",
        "cb_legs": "macdBullCross & recentStochBull(<=CONF_W) & (weeklyBull|fromOS) & rsi14<BUY_RSI_MAX",
    }


def load_ledger(repo_root: str | Path, symbols: list[str] | None = None) -> pd.DataFrame:
    """The buy/rebuy slice of the track record — a pure filter, never a mutation."""
    p = Path(repo_root) / LEDGER_PATH
    if not p.exists():
        return pd.DataFrame(columns=list(_LEDGER_COLUMNS))
    df = pd.read_parquet(p, columns=list(_LEDGER_COLUMNS))
    df = df[df["type"].isin(_LEDGER_TYPES)]
    if symbols is not None:
        df = df[df["ticker"].isin(symbols)]
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    # keep-FIRST on the store's own key: an append-only ledger may carry a re-stamped
    # duplicate, and the FIRST row is the one that was actually published.
    return df.sort_index().drop_duplicates(subset=["ticker", "date", "type"], keep="first")


def ledger_fires(
    ledger: pd.DataFrame,
    df: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hash: str,
    family_first_available: str | None,
) -> list[dict[str, Any]]:
    """One event per committed ledger row for ``symbol``."""
    sub = ledger[ledger["ticker"] == symbol]
    if sub.empty:
        return []
    close = df["close"].astype(float)
    rows: list[dict[str, Any]] = []
    for r in sub.itertuples(index=False):
        signal_ts = pd.Timestamp(r.date)
        known = marker_last_session(close, signal_ts, market="US")
        if known is None:
            # The label is not a bucket of THIS series (the ledger was built on the
            # production plane, which may differ from the program's plane for this name).
            # A guessed known_ts would break the known-ts law, so the row is skipped and
            # counted rather than stamped.
            continue
        era = str(r.anchor_era) if isinstance(r.anchor_era, str) and r.anchor_era else None
        rows.append(
            ev.make_event(
                family_key=FAMILY_BUY if r.type == "buy" else FAMILY_REBUY,
                producer="engine.signal_quality:analyze -> data/signal_archive/track_record.parquet",
                family="confirmed_buy",
                subtype=str(r.type),
                stage="CONFIRMED",
                symbol=symbol,
                price_plane_id=price_plane_id,
                grain="3D",
                signal_ts=signal_ts,
                signal_known_ts=pd.Timestamp(known),
                known_basis=KNOWN_BASIS_BUCKET,
                signal_era=ERA,
                family_era=era or "pre-era-stamp (ledger vintage predates anchor_era)",
                detector_spec_hash=spec_hash,
                source_hash=spec_hash,
                field_origin="ledger_recorded",
                provenance_class="R",
                family_first_available=family_first_available,
                scored_authority=True,
                spec_postdates_history=False,
                quality=str(r.quality) if isinstance(r.quality, str) else None,
                context={
                    "reason": str(r.reason) if isinstance(r.reason, str) else None,
                    "first_seen_asof": str(r.first_seen_asof),
                },
            )
        )
    return rows


def recompute_fires(
    df: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hash: str,
    family_first_available: str | None,
    ledger_first_date: pd.Timestamp | None,
) -> list[dict[str, Any]]:
    """The 3D confluence CB recomputed by the producer's own function.

    ``ledger_first_date`` is the symbol's earliest committed ledger row (``None`` when the
    ledger does not cover the name at all). Every recomputed row at or before it — i.e.
    every row the ledger does not already record — is stamped ``spec_postdates_history``.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float) if "high" in df.columns else None
    low = df["low"].astype(float) if "low" in df.columns else None
    frame = signal_frame(close, high, low, market="US")
    if frame is None or frame.empty or "CB" not in frame:
        return []
    grid = macro_grid(close, 3)
    if len(grid) != len(frame):
        return []
    fired = frame["CB"].fillna(False).to_numpy().astype(bool) & grid.completed_mask()

    rows: list[dict[str, Any]] = []
    for i in np.flatnonzero(fired):
        signal_ts = pd.Timestamp(grid.label[i])
        covered = ledger_first_date is not None and signal_ts >= pd.Timestamp(ledger_first_date)
        rows.append(
            ev.make_event(
                family_key=FAMILY_BUY,
                producer="engine.signal_quality:signal_frame.CB",
                family="confirmed_buy",
                subtype="cb_3d_confluence",
                stage="CONFIRMED",
                symbol=symbol,
                price_plane_id=price_plane_id,
                grain="3D",
                signal_ts=signal_ts,
                signal_known_ts=pd.Timestamp(grid.known.iloc[i]),
                known_basis=KNOWN_BASIS_BUCKET,
                signal_era=ERA,
                detector_spec_hash=spec_hash,
                source_hash=spec_hash,
                field_origin="replay_recomputed",
                provenance_class="R",
                family_first_available=family_first_available,
                # The RAW confluence cross is display-tier; only the filtered verdict in
                # the ledger ever had scored authority. Recording otherwise would promote
                # a pre-filter cross into a graded one.
                scored_authority=False,
                spec_postdates_history=not covered,
                context={
                    "arm": "pre_filter_confluence_cross",
                    "ledger_covers_this_date": bool(covered),
                },
            )
        )
    return rows
