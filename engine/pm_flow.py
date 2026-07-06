"""Prediction-market flow analytics — unusual-volume detection.

Computes per-event volume-delta z-scores from the snapshot history built by
collectors/prediction_markets.py.  This module is PURE COMPUTE — no alerts
wiring, no UI output.  Results are written to a sibling parquet:

    data/prediction_markets/flow_z.parquet

Schema:
    snapshot_date   str        — date of observation
    event_key       str        — configured event key
    vol24_delta     float      — day-over-day change in event volume24hr
    vol24_z         float      — (delta − rolling_mean) / rolling_std
    n_snapshots     int        — snapshot count used for the z-score (min gate)

The z-score is computed over the *delta* series (first difference of volume24hr)
so it catches acceleration, not just level.  Requires MIN_HISTORY (20) snapshots
per event before emitting a z-score (otherwise the field is NaN).

Intended consumer: alerts session (next PR); the store here is append-safe.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

MIN_HISTORY = 20  # minimum snapshot count before emitting a z-score


def compute_flow_z(
    snapshots: pd.DataFrame,
    min_history: int = MIN_HISTORY,
) -> pd.DataFrame:
    """Compute per-event volume-delta z-scores from snapshot history.

    Parameters
    ----------
    snapshots:
        DataFrame with at least columns: snapshot_date, event_key, volume24hr.
        Rows without volume24hr (legacy rows) are silently ignored.
    min_history:
        Minimum number of snapshots with non-null volume24hr required before a
        z-score is emitted.  Rows below this gate carry NaN for vol24_z.

    Returns
    -------
    DataFrame with columns: snapshot_date, event_key, vol24_delta, vol24_z,
    n_snapshots.  One row per (snapshot_date, event_key) pair; deduped to the
    last observation when multiple outcome rows exist for the same event/date
    (volume24hr is event-level so all outcome rows share the same value).
    """
    required = {"snapshot_date", "event_key", "volume24hr"}
    missing = required - set(snapshots.columns)
    if missing:
        raise ValueError(f"snapshots missing columns: {missing}")

    # Collapse to one row per (date, event_key) — volume24hr is event-level.
    ev = (
        snapshots[["snapshot_date", "event_key", "volume24hr"]]
        .dropna(subset=["volume24hr"])
        .drop_duplicates(subset=["snapshot_date", "event_key"], keep="last")
        .copy()
    )
    if ev.empty:
        log.warning("pm_flow: no rows with volume24hr — returning empty frame")
        return pd.DataFrame(columns=["snapshot_date", "event_key",
                                     "vol24_delta", "vol24_z", "n_snapshots"])

    ev = ev.sort_values(["event_key", "snapshot_date"]).reset_index(drop=True)
    ev["vol24_delta"] = ev.groupby("event_key")["volume24hr"].diff()

    rows = []
    for key, grp in ev.groupby("event_key"):
        deltas = grp["vol24_delta"].dropna()
        n = len(deltas)
        for _, row in grp.iterrows():
            delta = row["vol24_delta"]
            if pd.isna(delta) or n < min_history:
                z = float("nan")
                snap_n = n
            else:
                # Use all deltas up to and including this date (expanding window)
                # for a proper point-in-time z-score.
                hist = deltas[deltas.index <= row.name]
                snap_n = len(hist)
                if snap_n < min_history or hist.std(ddof=1) == 0:
                    z = float("nan")
                else:
                    z = (delta - hist.mean()) / hist.std(ddof=1)
            rows.append({
                "snapshot_date": row["snapshot_date"],
                "event_key": key,
                "vol24_delta": None if pd.isna(delta) else round(float(delta), 2),
                "vol24_z": None if (isinstance(z, float) and np.isnan(z)) else round(float(z), 4),
                "n_snapshots": snap_n,
            })
    return pd.DataFrame(rows)


def update_flow_z(data_dir: Path) -> pd.DataFrame:
    """Read snapshots, compute z-scores, write flow_z.parquet, return result.

    This function is APPEND-SAFE: it rewrites flow_z.parquet in full on each
    call (the parquet is derived, not primary).  It is idempotent — re-running
    with the same snapshots produces identical output.
    """
    snap_path = data_dir / "prediction_markets" / "snapshots.parquet"
    if not snap_path.exists():
        log.warning("pm_flow: snapshots.parquet not found at %s", snap_path)
        return pd.DataFrame()

    snapshots = pd.read_parquet(snap_path)
    result = compute_flow_z(snapshots)
    if result.empty:
        log.info("pm_flow: no flow_z rows (insufficient history)")
        return result

    out_path = data_dir / "prediction_markets" / "flow_z.parquet"
    result.to_parquet(out_path, index=False)
    high_z = result.dropna(subset=["vol24_z"])
    high_z = high_z[high_z["vol24_z"].abs() >= 2.0]
    log.info(
        "pm_flow: %d flow_z rows, %d with |z|>=2 on %s",
        len(result),
        len(high_z),
        result["snapshot_date"].max() if not result.empty else "—",
    )
    return result
