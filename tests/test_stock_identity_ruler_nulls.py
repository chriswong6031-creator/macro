"""Stock Identity W3A — mandatory localization null/control invariance (plan Task 3).

1. ``random_fire_null`` preserves per-expert fire COUNT and the declared dwell
   structure (every inter-fire gap, in days, is exactly preserved).
2. ``grain_cadence_null`` preserves each expert's cadence: every inter-fire gap is
   unchanged and every fire's phase modulo its own cadence period is unchanged.
3. ``equal_proximity_control`` never pairs observations whose ATR-distance gap
   exceeds the declared tolerance, and never pairs two fires from the same family.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.stock_identity.ruler_nulls import (
    PROXIMITY_PAIR_COLUMNS,
    equal_proximity_control,
    grain_cadence_null,
    random_fire_null,
)


def _events_for_symbol(symbol="AAA", family_key="fam.x", grain="1D", n=5, start="2020-01-06", step_days=10):
    ts = [pd.Timestamp(start) + pd.Timedelta(days=step_days * i) for i in range(n)]
    return pd.DataFrame({
        "event_id": [f"E{i}" for i in range(n)],
        "family_key": [family_key] * n,
        "symbol": [symbol] * n,
        "signal_ts": ts,
        "signal_known_ts": ts,
        "grain": [grain] * n,
    })


def _episodes_for_symbol(symbol="AAA", start="2019-01-01", end="2021-12-31"):
    return pd.DataFrame([{
        "symbol": symbol, "episode_type": "reset_decline", "tier": 1,
        "start_date": pd.Timestamp(start), "end_date": pd.Timestamp(end),
    }])


class _Spec:
    pass


def test_random_fire_null_preserves_count_and_dwell_structure():
    events = _events_for_symbol()
    episodes = _episodes_for_symbol()
    out = random_fire_null(events, episodes, seed=7, spec=_Spec())

    assert len(out) == len(events)
    real_gaps = np.diff(pd.to_datetime(events.sort_values("signal_known_ts")["signal_known_ts"]).to_numpy())
    null_gaps = np.diff(pd.to_datetime(out.sort_values("signal_known_ts")["signal_known_ts"]).to_numpy())
    assert list(real_gaps) == list(null_gaps)
    # anchor actually moved (deterministic seed, span wide enough that P(no-move) is negligible)
    assert not events["signal_known_ts"].reset_index(drop=True).equals(
        out.sort_values("signal_known_ts")["signal_known_ts"].reset_index(drop=True)
    )


def test_random_fire_null_is_seed_deterministic():
    events = _events_for_symbol()
    episodes = _episodes_for_symbol()
    a = random_fire_null(events, episodes, seed=42, spec=_Spec())
    b = random_fire_null(events, episodes, seed=42, spec=_Spec())
    pd.testing.assert_series_equal(a["signal_known_ts"], b["signal_known_ts"])


def test_grain_cadence_null_preserves_gaps_and_phase():
    events = _events_for_symbol(grain="3D", step_days=9)
    episodes = _episodes_for_symbol()
    out = grain_cadence_null(events, episodes, spec=_Spec())

    real_gaps = np.diff(pd.to_datetime(events["signal_known_ts"]).to_numpy())
    null_gaps = np.diff(pd.to_datetime(out["signal_known_ts"]).to_numpy())
    assert list(real_gaps) == list(null_gaps)

    # daily-class grain -> shifted by exactly 1 day
    shift = pd.to_datetime(out["signal_known_ts"]) - pd.to_datetime(events["signal_known_ts"])
    assert (shift == pd.Timedelta(days=1)).all()


def test_grain_cadence_null_weekly_class_shifts_by_seven_days():
    events = _events_for_symbol(grain="W", step_days=14)
    episodes = _episodes_for_symbol()
    out = grain_cadence_null(events, episodes, spec=_Spec())
    shift = pd.to_datetime(out["signal_known_ts"]) - pd.to_datetime(events["signal_known_ts"])
    assert (shift == pd.Timedelta(days=7)).all()


def test_equal_proximity_control_never_exceeds_tolerance():
    metrics = pd.DataFrame({
        "event_id": ["E1", "E2", "E3", "E4"],
        "family_key": ["fam.a", "fam.b", "fam.a", "fam.c"],
        "atr_dist": [0.10, 0.15, 5.0, 0.90],
    })
    out = equal_proximity_control(metrics, tolerance_atr=0.5)
    assert list(out.columns) == list(PROXIMITY_PAIR_COLUMNS)
    assert (out["atr_dist_gap"] <= 0.5).all()
    # E1/E3 share family_key -> never paired regardless of distance
    pairs = set(zip(out["left_event_id"], out["right_event_id"])) | set(
        zip(out["right_event_id"], out["left_event_id"])
    )
    assert ("E1", "E3") not in pairs and ("E3", "E1") not in pairs


def test_equal_proximity_control_empty_on_no_qualifying_pairs():
    metrics = pd.DataFrame({
        "event_id": ["E1", "E2"],
        "family_key": ["fam.a", "fam.b"],
        "atr_dist": [0.0, 10.0],
    })
    out = equal_proximity_control(metrics, tolerance_atr=0.1)
    assert out.empty
    assert list(out.columns) == list(PROXIMITY_PAIR_COLUMNS)
