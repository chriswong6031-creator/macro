"""Event -> identity episode, under W1's frozen ``P_pre`` (registration §4).

The join is deliberately the simplest thing that can be true::

    an event attributes to episode E  iff
        signal_known_ts ∈ [E.start_date − P_pre sessions, E.end_date]

``P_pre = 5`` is a **frozen W1 constant** read from ``si_constants_v1.json`` — never a knob
this wave sets, because a constant chosen after seeing the events it selects is not a
constant. The window opens on the event's ``signal_known_ts``, never on ``signal_ts``: an
event that could not be known until after an episode closed did not anticipate it.

Three properties this join must have, and which the tests pin:

1. **Unresolved and censored episodes attribute normally.** They simply have no anchor
   yet. Excluding them would build a survivorship filter into the join itself — the
   YELP-class decline that never prints a durable low is exactly the case the pilot was
   built to contain.
2. **Events outside every episode are RETAINED**, carrying a null episode edge. The §7.3
   unconditional block needs them at PR-3: an expert that fires 500 times a year with 5
   fires inside episodes would look perfectly localized while being worthless live, and
   that arithmetic is only possible if the 495 are still in the store.
3. **Join coverage is the ONLY published aggregate** — events joined / total, per family
   and per name. It is a count, not a ruler metric, and nothing here measures how WELL an
   event sits inside its episode. Distance, lead, lag and outcome are PR-3's object.

An event inside overlapping episodes attributes to ALL of them: episodes of different
types genuinely overlap, and picking one would be an unregistered ranking rule.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from engine.stock_identity.authority import authority_block

__all__ = ["ATTRIBUTION_COLUMNS", "attribute", "coverage_counts"]

ATTRIBUTION_COLUMNS: tuple[str, ...] = (
    "event_id",
    "family_key",
    "symbol",
    "signal_known_ts",
    "episode_index",
    "episode_type",
    "episode_tier",
    "episode_start_date",
    "episode_end_date",
    "episode_resolution",
    "episode_censored",
    "attributed",
    "p_pre_sessions",
) + tuple(f"authority_{k}" for k in authority_block())


def _session_offset(
    calendar: pd.DatetimeIndex, dates: pd.Series, back: int
) -> np.ndarray:
    """``dates`` moved ``back`` SESSIONS earlier on ``calendar`` (not calendar days)."""
    pos = calendar.searchsorted(pd.DatetimeIndex(dates), side="left")
    pos = np.maximum(pos - int(back), 0)
    return np.asarray(calendar)[pos]


def attribute(
    events: pd.DataFrame,
    catalog: pd.DataFrame,
    *,
    p_pre: int,
    calendar: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    """One row per (event, episode) hit, plus one null row per unattributed event."""
    cols = {c: pd.Series(dtype="object") for c in ATTRIBUTION_COLUMNS}
    if events is None or events.empty:
        return pd.DataFrame(cols)

    auth = authority_block()
    out: list[dict[str, Any]] = []
    cat = catalog if catalog is not None else pd.DataFrame()
    by_symbol = {
        str(s): sub.reset_index(drop=True)
        for s, sub in (cat.groupby("symbol") if not cat.empty else [])
    }

    for symbol, ev_sub in events.groupby("symbol"):
        eps = by_symbol.get(str(symbol))
        known = pd.to_datetime(ev_sub["signal_known_ts"])
        if eps is None or eps.empty:
            for eid, fam, ts in zip(ev_sub["event_id"], ev_sub["family_key"], known):
                out.append({
                    "event_id": eid, "family_key": fam, "symbol": str(symbol),
                    "signal_known_ts": ts, "episode_index": None, "episode_type": None,
                    "episode_tier": None, "episode_start_date": None,
                    "episode_end_date": None, "episode_resolution": None,
                    "episode_censored": None, "attributed": False,
                    "p_pre_sessions": int(p_pre),
                    **{f"authority_{k}": v for k, v in auth.items()},
                })
            continue

        cal = pd.DatetimeIndex(calendar) if calendar is not None else \
            pd.DatetimeIndex(sorted(set(known) | set(pd.to_datetime(eps["start_date"]))))
        starts = pd.DatetimeIndex(_session_offset(cal, eps["start_date"], p_pre))
        ends = pd.to_datetime(eps["end_date"])
        # A censored episode has no end; it runs to the end of the tape.
        ends = ends.fillna(pd.Timestamp.max.normalize())

        k_arr = known.to_numpy()
        s_arr = starts.to_numpy()
        e_arr = pd.DatetimeIndex(ends).to_numpy()
        for eid, fam, ts in zip(ev_sub["event_id"], ev_sub["family_key"], k_arr):
            hits = np.flatnonzero((s_arr <= ts) & (ts <= e_arr))
            if hits.size == 0:
                out.append({
                    "event_id": eid, "family_key": fam, "symbol": str(symbol),
                    "signal_known_ts": pd.Timestamp(ts), "episode_index": None,
                    "episode_type": None, "episode_tier": None,
                    "episode_start_date": None, "episode_end_date": None,
                    "episode_resolution": None, "episode_censored": None,
                    "attributed": False, "p_pre_sessions": int(p_pre),
                    **{f"authority_{k}": v for k, v in auth.items()},
                })
                continue
            for j in hits:
                r = eps.iloc[int(j)]
                out.append({
                    "event_id": eid, "family_key": fam, "symbol": str(symbol),
                    "signal_known_ts": pd.Timestamp(ts), "episode_index": int(j),
                    "episode_type": str(r["episode_type"]),
                    "episode_tier": int(r["tier"]) if pd.notna(r["tier"]) else None,
                    "episode_start_date": pd.Timestamp(r["start_date"]),
                    "episode_end_date": pd.Timestamp(r["end_date"])
                    if pd.notna(r["end_date"]) else None,
                    "episode_resolution": str(r["resolution"]),
                    "episode_censored": bool(r["censored"]),
                    "attributed": True, "p_pre_sessions": int(p_pre),
                    **{f"authority_{k}": v for k, v in auth.items()},
                })

    df = pd.DataFrame(out)
    for c in ATTRIBUTION_COLUMNS:
        if c not in df.columns:
            df[c] = None
    return df[list(ATTRIBUTION_COLUMNS)].reset_index(drop=True)


def coverage_counts(attribution: pd.DataFrame) -> pd.DataFrame:
    """Join coverage: events attributed / total, per family x name. Counts only."""
    if attribution is None or attribution.empty:
        return pd.DataFrame(columns=["family_key", "symbol", "n_events",
                                     "n_attributed", "n_unattributed"])
    per_event = attribution.groupby(
        ["family_key", "symbol", "event_id"], as_index=False
    )["attributed"].max()
    grouped = per_event.groupby(["family_key", "symbol"], as_index=False).agg(
        n_events=("event_id", "nunique"), n_attributed=("attributed", "sum")
    )
    grouped["n_attributed"] = grouped["n_attributed"].astype(int)
    grouped["n_unattributed"] = grouped["n_events"] - grouped["n_attributed"]
    return grouped.sort_values(["family_key", "symbol"]).reset_index(drop=True)
