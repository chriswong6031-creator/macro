from __future__ import annotations

import pandas as pd

from scripts.research import pss_f4_hazard as hazard


def test_feature_ablation_is_disjoint_and_complete() -> None:
    assert set(hazard.F4_FEATURES).isdisjoint(hazard.ORTHOGONAL_FEATURES)
    assert (
        hazard.FEATURE_SETS["hazard_full"]
        == hazard.F4_FEATURES + hazard.ORTHOGONAL_FEATURES
    )
    assert all(name.startswith("x_") for name in hazard.F4_FEATURES)
    assert all(name.startswith("x_") for name in hazard.ORTHOGONAL_FEATURES)


def test_scored_events_applies_frozen_boolean_gates() -> None:
    rows = []
    for i in range(3):
        row = {
            "sym": "A",
            "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
            "month": "2024-01",
            "delay": 0,
            "mae": -5.0,
            "prox": 2.0,
            "w5": True,
            "called": True,
            "tail10": False,
            "tdt": 1.0,
            "gate_price_matched": i == 0,
        }
        for kind in hazard.FEATURE_SETS:
            row[f"gate_{kind}"] = i == 1
        rows.append(row)

    events = hazard.scored_events(pd.DataFrame(rows))

    assert (events.kind == "inc").sum() == 3
    assert (events.kind == "price_matched").sum() == 1
    for kind in hazard.FEATURE_SETS:
        assert (events.kind == kind).sum() == 1
