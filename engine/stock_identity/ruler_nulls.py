"""Stock Identity W3A — mandatory localization nulls/controls (freeze §4.3, plan Task 3).

Three of the freeze's seven mandatory nulls/controls are ruler-side and built here:

1. **Independent per-fire random placement** (:func:`random_fire_null`) — every
   expert keeps its exact fire COUNT; each fire's session is drawn independently
   and uniformly from the symbol's own trading calendar (freeze review finding
   M11 — a single block-translation offset preserved every inter-fire gap
   exactly, which is a weaker null than independent placement).
2. **Grain/cadence null** (:func:`grain_cadence_null`) — a deterministic, seeded,
   trading-session-space circular shift: one offset ``K`` in ``[63, 252]``
   sessions is drawn per ``(family_key, symbol)`` and every fire in that group is
   moved ``K`` sessions forward on the symbol's own trading calendar, wrapping
   within its coverage (freeze review finding M4 — a uniform ±1/±7 CALENDAR-day
   shift never actually broke episode correspondence at pilot scale and could
   land on non-trading days).
3. **Equal-proximity comparison** (:func:`equal_proximity_control`) — pairs
   cross-family fires within the SAME episode (same anchor) whose ATR-distance
   gap is within a declared tolerance (freeze review finding M2/M3 — the prior
   implementation paired fires globally across symbols/episodes/grains, which is
   not a "similarly-placed" comparison at all).

No function here inspects per-name outcome rank to choose a parameter, expert or
neighborhood (``DNR:KILL-OUTCOME-AUDITION``); each null is a pure, seeded (where
randomness is involved) transform of the input, and every seed used is recorded
by the caller into the W3 registration artifact.
"""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

__all__ = [
    "PROXIMITY_PAIR_COLUMNS",
    "random_fire_null",
    "grain_cadence_null",
    "equal_proximity_control",
]

PROXIMITY_PAIR_COLUMNS: tuple[str, ...] = (
    "left_event_id", "right_event_id", "left_family_key", "right_family_key",
    "left_atr_dist", "right_atr_dist", "atr_dist_gap", "episode_id",
)

#: Deterministic seeded circular-shift offset range for the grain/cadence null
#: (freeze review finding M4) — in TRADING sessions, never calendar days.
GRAIN_CADENCE_NULL_MIN_SESSIONS = 63
GRAIN_CADENCE_NULL_MAX_SESSIONS = 252


def _symbol_calendar(bars_by_symbol: Mapping[str, pd.DataFrame] | None, symbol: str) -> pd.DatetimeIndex:
    if not bars_by_symbol:
        return pd.DatetimeIndex([])
    df = bars_by_symbol.get(symbol)
    if df is None or df.empty:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(sorted(df.index.unique()))


def random_fire_null(
    events: pd.DataFrame, bars_by_symbol: Mapping[str, pd.DataFrame], seed: int,
) -> pd.DataFrame:
    """Independent per-fire random placement (freeze review finding M11).

    For each ``(family_key, symbol)`` group the fire COUNT is preserved exactly;
    each fire's new session is drawn independently and uniformly from that
    symbol's own trading calendar (seeded, deterministic) — never a single
    scalar offset applied to the whole block. Every draw lands on an actual
    trading session (never a non-session date) by construction, since it is
    drawn FROM the calendar itself.
    """
    if events is None or events.empty:
        return events.copy() if events is not None else events

    out = events.copy()
    out["signal_known_ts"] = pd.to_datetime(out["signal_known_ts"])
    if "signal_ts" in out.columns:
        out["signal_ts"] = pd.to_datetime(out["signal_ts"])
    rng = np.random.default_rng(seed)

    for (fam, sym), idx in out.groupby(["family_key", "symbol"]).groups.items():
        calendar = _symbol_calendar(bars_by_symbol, str(sym))
        n = len(calendar)
        sub = out.loc[idx]
        if n == 0:
            continue
        draws = rng.integers(0, n, size=len(sub))
        new_ts = calendar[draws]
        out.loc[sub.index, "signal_known_ts"] = new_ts
        if "signal_ts" in out.columns:
            out.loc[sub.index, "signal_ts"] = new_ts

    return out


def grain_cadence_null(
    events: pd.DataFrame, bars_by_symbol: Mapping[str, pd.DataFrame], seed: int,
) -> pd.DataFrame:
    """Trading-session-space circular shift (freeze review finding M4).

    Per ``(family_key, symbol)`` group, one deterministic seeded offset ``K`` in
    ``[63, 252]`` TRADING sessions is drawn and every fire in the group is moved
    ``K`` sessions forward on that symbol's own trading calendar, wrapping within
    its coverage. This preserves the group's cadence exactly in circular
    session-index space (a uniform rotation preserves every pairwise circular
    distance) while breaking correspondence to the specific episode anchors —
    the null's purpose. Every placed fire lands on an actual trading session by
    construction (it is drawn FROM the calendar), so no null fire can ever fall
    on a non-session date.
    """
    if events is None or events.empty:
        return events.copy() if events is not None else events

    out = events.copy()
    out["signal_known_ts"] = pd.to_datetime(out["signal_known_ts"])
    if "signal_ts" in out.columns:
        out["signal_ts"] = pd.to_datetime(out["signal_ts"])
    rng = np.random.default_rng(seed)

    for (fam, sym), idx in out.groupby(["family_key", "symbol"]).groups.items():
        calendar = _symbol_calendar(bars_by_symbol, str(sym))
        n = len(calendar)
        sub = out.loc[idx]
        if n == 0:
            continue
        k = int(rng.integers(GRAIN_CADENCE_NULL_MIN_SESSIONS, GRAIN_CADENCE_NULL_MAX_SESSIONS + 1))
        positions = calendar.searchsorted(sub["signal_known_ts"].to_numpy(), side="left")
        positions = np.clip(positions, 0, n - 1)
        new_positions = (positions + k) % n
        new_ts = calendar[new_positions]
        out.loc[sub.index, "signal_known_ts"] = new_ts
        if "signal_ts" in out.columns:
            out.loc[sub.index, "signal_ts"] = new_ts

    return out


def equal_proximity_control(metrics: pd.DataFrame, tolerance_atr: float) -> tuple[pd.DataFrame, int]:
    """Pair cross-family fires that fired into the SAME episode (freeze review
    finding M2/M3) whose ``atr_dist`` (distance to anchor, ATR units) differ by
    no more than ``tolerance_atr``. Never pairs two fires from the same
    ``family_key`` (that would not be a cross-expert comparison), never emits a
    pair whose gap exceeds the declared tolerance, and never pairs fires from
    DIFFERENT episodes/symbols/grains — a "similarly-placed" comparison is only
    meaningful anchored to the same episode.

    Per-episode fire counts are small (a handful at most), so no scan cap is
    needed once pairing is grouped by episode — every candidate pair within a
    group is examined. Returns ``(pairs, truncated_count)``; ``truncated_count``
    is always ``0`` under this grouped design (kept as an explicit return value,
    per the freeze review, rather than silently omitted) — a future defensive
    per-episode cap would report a nonzero value here instead of dropping pairs
    silently.
    """
    empty = pd.DataFrame({c: pd.Series(dtype="object") for c in PROXIMITY_PAIR_COLUMNS})
    if metrics is None or metrics.empty or "atr_dist" not in metrics.columns or "episode_id" not in metrics.columns:
        return empty, 0
    if tolerance_atr < 0:
        raise ValueError("tolerance_atr must be >= 0")

    rows: list[dict[str, Any]] = []
    truncated = 0
    for episode_id, group in metrics.dropna(subset=["atr_dist"]).groupby("episode_id"):
        g = group.sort_values("atr_dist").reset_index(drop=True)
        n = len(g)
        atr = g["atr_dist"].to_numpy(dtype=float)
        fam = g["family_key"].to_numpy()
        eid = g["event_id"].to_numpy()
        for i in range(n):
            ai = atr[i]
            for j in range(i + 1, n):
                gap = atr[j] - ai
                if gap > tolerance_atr:
                    break  # sorted ascending: no further j can be within tolerance
                if fam[j] == fam[i]:
                    # same-family pairs are excluded from OUTPUT but never consume
                    # any scan budget (there is none to consume in this grouped,
                    # uncapped design) and never displace a legitimate pair.
                    continue
                rows.append({
                    "left_event_id": eid[i],
                    "right_event_id": eid[j],
                    "left_family_key": fam[i],
                    "right_family_key": fam[j],
                    "left_atr_dist": float(ai),
                    "right_atr_dist": float(atr[j]),
                    "atr_dist_gap": float(abs(gap)),
                    "episode_id": episode_id,
                })
    if not rows:
        return empty, truncated
    return pd.DataFrame(rows)[list(PROXIMITY_PAIR_COLUMNS)], truncated
