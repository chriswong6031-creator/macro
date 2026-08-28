"""Stock Identity W3A — mandatory localization nulls/controls (freeze §4.3, plan Task 3).

Three of the freeze's seven mandatory nulls/controls are ruler-side and built here:

1. **Count/dwell-matched random fire placement** (:func:`random_fire_null`) — every
   expert keeps its exact fire count and the exact gaps between consecutive fires
   (the "dwell structure"); only the anchor date of the whole sequence moves,
   drawn uniformly within that symbol's episode-catalog span.
2. **Grain/cadence null** (:func:`grain_cadence_null`) — every fire is shifted by
   exactly one cadence period of its own grain class (freeze §4.2 "grain is
   always stratified"). A uniform per-row shift leaves every inter-fire gap and
   every stamp-lag-modulo-cadence identical to the real sequence — the null
   breaks correspondence to the specific episode anchors while leaving the
   expert's own cadence untouched.
3. **Equal-proximity comparison** (:func:`equal_proximity_control`) — pairs
   cross-family fires that landed within a declared ATR tolerance of the same
   anchor, so a later read can compare "similarly-placed" fires across experts
   without ever pairing observations the tolerance would not license.

No function here inspects per-name outcome rank to choose a parameter, expert or
neighborhood (``DNR:KILL-OUTCOME-AUDITION``); each null is a pure, seeded (where
randomness is involved) transform of the input, and every seed used is recorded
by the caller into the W3 registration artifact.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from engine.stock_identity.ruler import grain_class

__all__ = [
    "PROXIMITY_PAIR_COLUMNS",
    "random_fire_null",
    "grain_cadence_null",
    "equal_proximity_control",
]

PROXIMITY_PAIR_COLUMNS: tuple[str, ...] = (
    "left_event_id", "right_event_id", "left_family_key", "right_family_key",
    "left_atr_dist", "right_atr_dist", "atr_dist_gap",
)


def _cadence_shift(grain: Any) -> pd.Timedelta:
    """One full cadence period for ``grain``'s class — 7 days weekly, 1 day daily."""
    return pd.Timedelta(days=7) if grain_class(grain) == "weekly" else pd.Timedelta(days=1)


def random_fire_null(
    events: pd.DataFrame, episodes: pd.DataFrame, seed: int, spec: Any
) -> pd.DataFrame:
    """Re-anchor each (family_key, symbol) group's fire sequence at a uniformly
    random start within that symbol's episode-catalog span, preserving both the
    fire COUNT and every inter-fire gap exactly (LER "dwell structure" law).
    """
    if events is None or events.empty:
        return events.copy() if events is not None else events

    out = events.copy()
    out["signal_known_ts"] = pd.to_datetime(out["signal_known_ts"])
    if "signal_ts" in out.columns:
        out["signal_ts"] = pd.to_datetime(out["signal_ts"])
    rng = np.random.default_rng(seed)

    for (fam, sym), idx in out.groupby(["family_key", "symbol"]).groups.items():
        sub = out.loc[idx].sort_values("signal_known_ts")
        n = len(sub)
        if n == 0:
            continue
        ep_sub = (
            episodes[episodes["symbol"] == sym]
            if episodes is not None and not episodes.empty and "symbol" in episodes.columns
            else pd.DataFrame()
        )
        if not ep_sub.empty:
            lo = pd.to_datetime(ep_sub["start_date"]).min()
            end_col = pd.to_datetime(ep_sub["end_date"]) if "end_date" in ep_sub.columns else pd.Series(dtype="datetime64[ns]")
            hi = end_col.max() if not end_col.empty and end_col.notna().any() else pd.to_datetime(ep_sub["start_date"]).max()
        else:
            lo = sub["signal_known_ts"].min()
            hi = sub["signal_known_ts"].max()
        if pd.isna(lo) or pd.isna(hi) or hi <= lo:
            continue

        real_ts = sub["signal_known_ts"].to_numpy()
        offsets = real_ts - real_ts[0]
        total_span_days = (
            float(offsets[-1] / np.timedelta64(1, "D")) if n > 1 else 0.0
        )
        span_days = (hi - lo).days
        max_start_days = max(span_days - total_span_days, 0)
        start_offset_days = int(rng.integers(0, int(max_start_days) + 1))
        new_start = pd.Timestamp(lo) + pd.Timedelta(days=start_offset_days)
        new_ts = [pd.Timestamp(new_start) + pd.Timedelta(o) for o in offsets]

        out.loc[sub.index, "signal_known_ts"] = new_ts
        if "signal_ts" in out.columns:
            out.loc[sub.index, "signal_ts"] = new_ts

    return out


def grain_cadence_null(events: pd.DataFrame, episodes: pd.DataFrame, spec: Any) -> pd.DataFrame:
    """Shift every fire by exactly one cadence period of its own grain class.

    Deterministic (no seed): a uniform per-row shift changes every fire's absolute
    date but leaves the gap between any two of that expert's fires, and the fire's
    phase modulo its own cadence, unchanged — that IS the cadence/stamp-lag
    invariance this null is required to preserve.
    """
    if events is None or events.empty:
        return events.copy() if events is not None else events
    out = events.copy()
    out["signal_known_ts"] = pd.to_datetime(out["signal_known_ts"])
    if "signal_ts" in out.columns:
        out["signal_ts"] = pd.to_datetime(out["signal_ts"])
    shift = out["grain"].map(_cadence_shift)
    out["signal_known_ts"] = out["signal_known_ts"] + shift
    if "signal_ts" in out.columns:
        out["signal_ts"] = out["signal_ts"] + shift
    return out


#: A dense cluster of near-identical ``atr_dist`` values would otherwise make the
#: sorted-window scan pathologically large (a real risk at pilot scale: 15k+
#: fires). Capping the forward scan keeps this an O(n * MAX_NEIGHBOR_SCAN)
#: diagnostic control rather than a combinatorial all-pairs enumeration; every
#: pair returned still satisfies the exact tolerance test below, so the
#: "never pairs observations outside the ATR tolerance" guarantee is unaffected
#: — the cap can only make the control MISS a legitimate pair, never emit an
#: illegitimate one.
MAX_NEIGHBOR_SCAN = 200


def equal_proximity_control(metrics: pd.DataFrame, tolerance_atr: float) -> pd.DataFrame:
    """Pair cross-family fires whose ``atr_dist`` (distance to anchor, ATR units)
    differ by no more than ``tolerance_atr``. Never pairs two fires from the same
    ``family_key`` (that would not be a cross-expert comparison) and never emits a
    pair whose gap exceeds the declared tolerance.
    """
    empty = pd.DataFrame({c: pd.Series(dtype="object") for c in PROXIMITY_PAIR_COLUMNS})
    if metrics is None or metrics.empty or "atr_dist" not in metrics.columns:
        return empty
    if tolerance_atr < 0:
        raise ValueError("tolerance_atr must be >= 0")

    sub = metrics.dropna(subset=["atr_dist"]).sort_values("atr_dist").reset_index(drop=True)
    n = len(sub)
    atr = sub["atr_dist"].to_numpy(dtype=float)
    fam = sub["family_key"].to_numpy()
    eid = sub["event_id"].to_numpy()

    rows: list[dict[str, Any]] = []
    for i in range(n):
        ai = atr[i]
        j_end = min(i + 1 + MAX_NEIGHBOR_SCAN, n)
        for j in range(i + 1, j_end):
            gap = atr[j] - ai
            if gap > tolerance_atr:
                break  # sorted ascending: no further j can be within tolerance
            if fam[j] == fam[i]:
                continue
            rows.append({
                "left_event_id": eid[i],
                "right_event_id": eid[j],
                "left_family_key": fam[i],
                "right_family_key": fam[j],
                "left_atr_dist": float(ai),
                "right_atr_dist": float(atr[j]),
                "atr_dist_gap": float(abs(gap)),
            })
    if not rows:
        return empty
    return pd.DataFrame(rows)[list(PROXIMITY_PAIR_COLUMNS)]
