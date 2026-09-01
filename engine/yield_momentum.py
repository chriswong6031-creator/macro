"""Pure, display-only multi-horizon yield momentum read.

The caller supplies the already-collected canonical rate feature frame.  This module
does not fetch, persist, score, rank, size, or trade: rebuilding the same input frame
always returns the same read, including after a source correction.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


SERIES: dict[str, str] = {
    "2y": "us2y",
    "5y": "us5y",
    "10y": "us10y",
    "20y": "us20y",  # canonical CCW series; never substitute DGS20.
    "30y": "us30y",
}
HORIZONS: tuple[int, ...] = (5, 22, 63)
TURN_LOOKBACK = 1260


def _date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        stamp = pd.Timestamp(value)
        return None if pd.isna(stamp) else str(stamp.date())
    except Exception:
        return None


def _bp_change(values: pd.Series, horizon: int) -> float | None:
    if len(values) <= horizon:
        return None
    return round(float(values.iloc[-1] - values.iloc[-horizon - 1]) * 100, 1)


def _turn_watch(values: pd.Series, change_22d_bp: float | None) -> str | None:
    if change_22d_bp is None or len(values) < 60:
        return None
    trailing = values.iloc[-TURN_LOOKBACK:]
    percentile = float((trailing <= trailing.iloc[-1]).mean())
    if percentile >= 0.85 and change_22d_bp <= -12:
        return "rolldown_forming"
    if percentile >= 0.90:
        return "extreme_high_watch"
    if percentile <= 0.15 and change_22d_bp >= 12:
        return "rollup_forming"
    if percentile <= 0.10:
        return "extreme_low_watch"
    return None


def _series_read(
    frame: pd.DataFrame,
    column: str,
    available_at: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if column not in frame:
        return {
            "source_column": column,
            "status": "missing",
            "as_of": None,
            "available_at": None,
            "availability_status": "not_provided_by_feature_frame",
            "level": None,
            "velocity_bp": {f"{h}d": None for h in HORIZONS},
            "acceleration_bp": None,
            "turn_watch": None,
            "null_reason": f"source column {column} unavailable",
        }

    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    source_available_at = _date((available_at or {}).get(column))
    if values.empty:
        return {
            "source_column": column,
            "status": "missing",
            "as_of": None,
            "available_at": source_available_at,
            "availability_status": "provided" if source_available_at else "not_provided_by_feature_frame",
            "level": None,
            "velocity_bp": {f"{h}d": None for h in HORIZONS},
            "acceleration_bp": None,
            "turn_watch": None,
            "null_reason": f"source column {column} has no observed values",
        }

    velocity = {f"{h}d": _bp_change(values, h) for h in HORIZONS}
    acceleration = None
    if len(values) > 44:
        current = _bp_change(values, 22)
        prior = round(float(values.iloc[-23] - values.iloc[-45]) * 100, 1)
        acceleration = round(current - prior, 1) if current is not None else None
    enough = len(values) >= 64
    return {
        "source_column": column,
        "status": "available" if enough else "insufficient_history",
        "as_of": _date(values.index[-1]),
        "available_at": source_available_at,
        "availability_status": "provided" if source_available_at else "not_provided_by_feature_frame",
        "level": round(float(values.iloc[-1]), 3),
        "velocity_bp": velocity,
        "acceleration_bp": acceleration,
        "turn_watch": _turn_watch(values, velocity["22d"]) if enough else None,
        "null_reason": None if enough else "requires 64 observed points for 63d velocity",
    }


def build_yield_momentum(
    frame: pd.DataFrame,
    *,
    available_at: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a causal, deterministic read of the canonical yield-series frame.

    ``available_at`` is optional provenance supplied by the source owner.  Its absence
    stays explicit rather than being inferred from an observation timestamp.
    """
    as_of = _date(frame.index[-1]) if len(frame.index) else None
    return {
        "schema": "yield_momentum.v1",
        "asof": as_of,
        "display_only": True,
        "authority": False,
        "can_score": False,
        "can_size": False,
        "can_trade": False,
        "series": {
            label: _series_read(frame, column, available_at)
            for label, column in SERIES.items()
        },
    }
