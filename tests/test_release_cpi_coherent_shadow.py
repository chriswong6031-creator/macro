from __future__ import annotations

import copy
import shutil
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

import engine.release_cpi_coherent_shadow as coherent


ROOT = Path(__file__).resolve().parents[1]


def test_real_bound_corpus_is_deterministic_and_receipt_linked() -> None:
    kwargs = {
        "asof": date(2026, 8, 11),
        "root": ROOT,
        "period": "2026-07",
        "release_date": date(2026, 8, 12),
    }
    for release in ("cpi_headline", "cpi_core"):
        first = coherent.project_cpi_coherent_shadow(release=release, **kwargs)
        second = coherent.project_cpi_coherent_shadow(release=release, **kwargs)

        assert first == second
        assert first["model"] == "coherent_ridge_v1"
        assert first["target_epoch"] == "alfred_same_release_vintage_proxy_v1"
        assert first["display_only"] is True
        assert first["authority"] is False
        assert first["promotion_authorized"] is False
        assert first["training_receipt"]["n"] >= coherent.MIN_TRAIN_OBS
        assert first["interval_receipt"]["n"] >= coherent.MIN_INTERVAL_OBS
        assert first["inputs_hash"] == first["input_manifest"]["sha256"]
        assert (
            first["training_receipt"]["input_manifest_sha256"]
            == first["input_manifest"]["sha256"]
        )
        assert (
            first["interval_receipt"]["training_receipt_sha256"]
            == first["training_receipt"]["sha256"]
        )
        assert first["interval_receipt"]["point_raw"] == first["point_raw"]
        assert first["p10"] <= first["p25"] <= first["p50"] <= first["p75"] <= first["p90"]
        for key in (
            "input_manifest",
            "model_receipt",
            "truth_receipt",
            "training_receipt",
            "interval_receipt",
        ):
            assert coherent.verify_sealed_receipt(first[key])


def test_live_cutoff_and_period_gates_fail_closed() -> None:
    with pytest.raises(coherent.CoherentShadowContractError, match="minus one calendar day"):
        coherent.project_cpi_coherent_shadow(
            release="cpi_core",
            asof=date(2026, 8, 10),
            root=ROOT,
            period="2026-07",
            release_date=date(2026, 8, 12),
        )
    with pytest.raises(coherent.CoherentShadowContractError, match="exact month after"):
        coherent.project_cpi_coherent_shadow(
            release="cpi_core",
            asof=date(2026, 8, 11),
            root=ROOT,
            period="2026-08",
            release_date=date(2026, 8, 12),
        )


def test_interval_rounding_is_outward_for_both_signs() -> None:
    assert coherent._round_interval_endpoint_1dp(0.21, endpoint="lower") == 0.2
    assert coherent._round_interval_endpoint_1dp(-0.21, endpoint="lower") == -0.3
    assert coherent._round_interval_endpoint_1dp(0.21, endpoint="upper") == 0.3
    assert coherent._round_interval_endpoint_1dp(-0.21, endpoint="upper") == -0.2
    assert coherent._round_interval_endpoint_1dp(0.25, endpoint="median") == 0.3


def test_alfred_selection_is_cutoff_safe_and_ambiguous_rows_fail() -> None:
    frame = pd.DataFrame(
        [
            {
                "series": "PPIFIS",
                "period": pd.Timestamp("2026-06-01"),
                "value": 100.0,
                "realtime_start": pd.Timestamp("2026-07-10"),
            },
            {
                "series": "PPIFIS",
                "period": pd.Timestamp("2026-06-01"),
                "value": 200.0,
                "realtime_start": pd.Timestamp("2026-08-12"),
            },
        ]
    )
    value, receipt = coherent._exact_alfred_observation(
        frame,
        series="PPIFIS",
        source_period=date(2026, 6, 1),
        cutoff=date(2026, 8, 11),
    )
    assert value == 100.0
    assert receipt["realtime_start"] == "2026-07-10"

    ambiguous = pd.concat(
        [frame.iloc[:1], frame.iloc[:1].assign(value=101.0)],
        ignore_index=True,
    )
    with pytest.raises(coherent.MissingFeatureError, match="ambiguous"):
        coherent._exact_alfred_observation(
            ambiguous,
            series="PPIFIS",
            source_period=date(2026, 6, 1),
            cutoff=date(2026, 8, 11),
        )


def test_exact_own_lag_must_exist_and_be_released_by_cutoff() -> None:
    target_index = {}
    for lag, period in enumerate(("2026-06", "2026-05", "2026-04"), start=1):
        target_index[("cpi_core", period)] = {
            "period": period,
            "release_date": "2026-08-12" if lag == 1 else "2026-07-01",
            "_release_date": date(2026, 8, 12) if lag == 1 else date(2026, 7, 1),
            "published_proxy_1dp": 0.2,
            "_target": 0.2,
        }
    with pytest.raises(coherent.MissingFeatureError, match="was not released by cutoff"):
        coherent._build_feature_vector(
            release="cpi_core",
            target_period=date(2026, 7, 1),
            cutoff=date(2026, 8, 11),
            target_index=target_index,
            history_hash="sha256:test",
            vintages=pd.DataFrame(),
            gasoline=None,
        )


def test_ridge_is_deterministic_and_intercept_is_unpenalized() -> None:
    X = np.asarray([[0.0], [1.0], [2.0], [3.0]])
    y = np.asarray([2.0, 2.0, 2.0, 2.0])
    point_a, receipt_a = coherent._fit_ridge(X, y, np.asarray([99.0]))
    point_b, receipt_b = coherent._fit_ridge(X, y, np.asarray([99.0]))
    assert point_a == pytest.approx(2.0)
    assert point_b == point_a
    assert receipt_a == receipt_b
    assert receipt_a["intercept"] == pytest.approx(2.0)


def test_walk_forward_residuals_never_use_future_targets() -> None:
    start = date(2010, 1, 1)
    records = [
        {
            "period": f"row-{index:03d}",
            "release_date": start + timedelta(days=index),
            "cutoff": start + timedelta(days=index - 1),
            "target": float(index % 7) / 10.0,
            "features": {"x": float(index)},
        }
        for index in range(70)
    ]
    before = coherent._walk_forward_residuals(records, ("x",))
    changed = copy.deepcopy(records)
    changed[-1]["target"] = 999.0
    after = coherent._walk_forward_residuals(changed, ("x",))
    assert len(before) == 10
    assert before[0]["n_train"] == coherent.MIN_TRAIN_OBS
    assert before[:-1] == after[:-1]
    assert before[-1]["point_raw"] == after[-1]["point_raw"]
    assert before[-1]["residual"] != after[-1]["residual"]


def test_validly_edited_registry_fails_runtime_contract(tmp_path: Path) -> None:
    registry_path = tmp_path / coherent.REGISTRY_PATH
    prereg_path = tmp_path / coherent.PREREG_PATH
    registry_path.parent.mkdir(parents=True)
    prereg_path.parent.mkdir(parents=True)
    shutil.copy2(ROOT / coherent.REGISTRY_PATH, registry_path)
    shutil.copy2(ROOT / coherent.PREREG_PATH, prereg_path)
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry["models"][coherent.MODEL_ID]["training"]["ridge_lambda"] = 2.0
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    with pytest.raises(coherent.CoherentShadowContractError, match="ridge_lambda"):
        coherent._load_model_receipt(tmp_path, date(2026, 8, 11))
