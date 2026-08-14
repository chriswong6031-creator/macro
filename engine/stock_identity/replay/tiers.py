"""T1-T4 confluence cascade onsets — Class B locked-spec backcast.

The cascade's per-bar T2-T4 history is persisted nowhere (archaeology §4.5 item 4), so the
only route is recomputation via :func:`engine.confluence_tiers.tier_stream` under the
module's own ``ANCHOR_ERA``. That era string postdates almost all of the recomputed
history, which is exactly what **Class B** means: every row is stamped
``spec_postdates_history=True`` and may never be cited as evidence that the cascade *as it
then existed* did anything.

**An event is a tier ONSET, not a tier day.** ``tier_stream`` returns a per-day tier state;
publishing one row per day would be a state series, not an event history, and would bury a
real transition under thousands of duplicates. A fire is the day a name ENTERS ``T_k``
from something else — the same "transition, not level" convention the washout organ's own
ledger uses.

**The trailing row is dropped.** ``tier_stream``'s docstring is explicit that interior rows
read the last COMPLETED bucket while the FINAL row sits on the in-progress partial bucket
(the live board's provisional basis). Interior rows are therefore causal; the final row is
not, so it is discarded. The residual difference between this stream and what the live
board actually saw on ~8% of days is a live-vs-replay basis difference, recorded in the
registry's ``replay_notes`` — it is not a leak, and W2 makes no claim about the live board.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from engine.confluence_tiers import (
    ANCHOR_ERA as CT_ANCHOR_ERA,
    FRESH_TICKS,
    tier_stream,
)

from engine.stock_identity.replay import events as ev
from engine.stock_identity.replay.grid import KNOWN_BASIS_DAILY

__all__ = ["TIERS", "FAMILY_KEYS", "ERA", "constants", "fires"]

TIERS: tuple[str, ...] = ("T1", "T2", "T3", "T4")
FAMILY_KEYS: dict[str, str] = {t: f"tier_cascade_{t.lower()}" for t in TIERS}
ERA = CT_ANCHOR_ERA


def constants() -> dict[str, Any]:
    return {
        "producer": "engine.confluence_tiers:tier_stream",
        "anchor_era": CT_ANCHOR_ERA,
        "fresh_ticks": FRESH_TICKS,
        "event_convention": "tier ONSET (entry into T_k from a different state)",
        "provisional_row": "final row dropped — it reads the in-progress partial bucket",
    }


def fires(
    df: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hash: str,
    family_first_available: str | None,
) -> list[dict[str, Any]]:
    """One event per tier onset, per tier family."""
    close = df["close"].astype(float)
    stream = tier_stream(close, market="US")
    if stream is None or stream.empty or "tier" not in stream:
        return []
    stream = stream.iloc[:-1]          # drop the provisional trailing row
    if stream.empty:
        return []

    tier = stream["tier"].astype("object")
    prev = tier.shift(1)
    onset = (tier != prev) & tier.notna()
    idx = pd.DatetimeIndex(stream.index)

    rows: list[dict[str, Any]] = []
    for i in np.flatnonzero(onset.to_numpy()):
        t = str(tier.iloc[i])
        if t not in FAMILY_KEYS:
            continue
        ts = pd.Timestamp(idx[i])
        row_era = stream["anchor_era"].iloc[i] if "anchor_era" in stream.columns else ERA
        rows.append(
            ev.make_event(
                family_key=FAMILY_KEYS[t],
                producer="engine.confluence_tiers:tier_stream",
                family="tier_cascade",
                subtype=t,
                stage="TIER",
                symbol=symbol,
                price_plane_id=price_plane_id,
                grain="1D-state-over-2D/3D-buckets",
                signal_ts=ts,
                signal_known_ts=ts,
                known_basis=KNOWN_BASIS_DAILY,
                signal_era=ERA,
                family_era=str(row_era) if isinstance(row_era, str) else ERA,
                detector_spec_hash=spec_hash,
                source_hash=spec_hash,
                field_origin="replay_recomputed",
                provenance_class="B",
                family_first_available=family_first_available,
                # The cascade GATES the Standout boards, so its authority is real and is
                # recorded here as the fact it is. Recording it grants this store nothing.
                scored_authority=True,
                spec_postdates_history=True,
                context={
                    "prior_tier": None if pd.isna(prev.iloc[i]) else str(prev.iloc[i]),
                },
            )
        )
    return rows
