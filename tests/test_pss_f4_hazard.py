from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from engine.personality_terminality_shadow import score_frozen_model
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


def test_json_tree_export_matches_sklearn_with_missing_values() -> None:
    rng = np.random.default_rng(42)
    x = rng.normal(size=(800, 4))
    x[::13, 1] = np.nan
    y = ((np.nan_to_num(x[:, 0]) - 0.4 * np.nan_to_num(x[:, 2])) > 0).astype(int)
    model = HistGradientBoostingClassifier(
        max_iter=20,
        max_leaf_nodes=7,
        max_depth=3,
        min_samples_leaf=20,
        early_stopping=False,
        random_state=7,
    ).fit(x, y)
    names = tuple(f"x_{i}" for i in range(x.shape[1]))
    frozen = hazard._tree_document(model, names)
    expected = model.predict_proba(x[:100])[:, 1]
    actual = np.array(
        [
            score_frozen_model(
                frozen,
                {name: float(value) for name, value in zip(names, row, strict=True)},
            )
            for row in x[:100]
        ]
    )
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-14)
