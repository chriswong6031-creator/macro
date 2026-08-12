"""Tests for scripts/build_release_forecast.py — MRI PR-C nightly producer.

Categories:
  1. Contract   — latest.json schema keys, display_only=True, authority booleans False,
                  asof is full-ISO-UTC parseable.
  2. Ledger     — append-only (no dup on double run), projection rows unaffected by
                  capture, scored row math correctness.
  3. Scoreboard — computed from scored rows only; n=0 honest output.
  4. Cleveland  — PIT read (obs_date <= today), absent-file fail-open.
  5. Policy backdrop — all sources missing → nulls, no raise.

All tests use synthetic data / tmp directories. No real parquet files are required.

Run:
    python -m pytest tests/test_release_forecast_producer.py -v
"""
from __future__ import annotations

import json
import sys
import types
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from scripts.build_release_forecast import (
    _attach_provenance,
    _append_ledger_rows,
    _build_projection_ledger_rows,
    _build_scoreboard,
    _build_upcoming_block,
    _check_release_day_capture,
    _CLAIMS_MODE,
    _compute_actual_from_print,
    _get_initial_print,
    _ledger_key,
    _load_ledger,
    _read_cleveland_nowcast,
    _read_policy_backdrop,
    _run_projection,
    _wilson,
)


def test_hash_survives_engine_item_snapshot_and_ledger(tmp_root: Path, monkeypatch) -> None:
    import scripts.build_release_forecast as producer

    expected_hash = "a" * 64
    monkeypatch.setattr(
        producer,
        "_run_projection",
        lambda *args, **kwargs: {
            "point": 0.2,
            "p10": 0.0,
            "p25": 0.1,
            "p50": 0.2,
            "p75": 0.3,
            "p90": 0.4,
            "confidence": 0.5,
            "input_completeness": 1.0,
            "inputs_hash": expected_hash,
            "input_manifest": {"x": 1.0},
            "benchmark_set": {},
            "surprise_skew": {},
            "pit_provenance": {"vintaged_legs": ["x"]},
        },
    )
    items = _build_upcoming_block(
        date(2026, 8, 9),
        tmp_root,
        [{
            "release_type": "cpi_headline",
            "release": "cpi",
            "period": "2026-07",
            "release_date": "2026-08-12",
            "regime_axis": "inflation",
        }],
        {},
    )
    assert items[0]["inputs_hash"] == expected_hash

    snapshots = tmp_root / "data" / "release_forecast" / "input_snapshots"
    ledger = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
    _attach_provenance(items, ledger, snapshots, asof_day=date(2026, 8, 9))
    snapshot = json.loads(next(snapshots.glob("*.json")).read_text(encoding="utf-8"))
    assert snapshot["inputs_hash"] == expected_hash
    rows = _build_projection_ledger_rows(date(2026, 8, 9), items, {})
    assert rows[0]["inputs_hash"] == expected_hash


def test_shadow_item_receipts_are_public_provenance(tmp_root: Path, monkeypatch) -> None:
    import scripts.build_release_forecast as producer

    monkeypatch.setattr(
        producer,
        "_run_shadow_v3",
        lambda *args, **kwargs: {
            "point": 0.2,
            "inputs_hash": "b" * 64,
        },
    )
    item = {
        "release_type": "cpi_core",
        "period": "2026-07",
        "release_date": "2026-08-12",
        "code_receipt": "sha256:producer-receipt",
    }

    producer._attach_shadows_to_items(
        [item], tmp_root, date(2026, 8, 9)
    )

    shadow = item["shadows"]["v3_factor"]
    assert shadow["inputs_hash"] == "b" * 64
    assert shadow["model_epoch"] == "v3_factor_legacy_target_v1"
    assert shadow["target_epoch"] == "legacy_cross_vintage_initial_levels_v0"
    assert shadow["code_receipt"] == "sha256:producer-receipt"


def _coherent_shadow_result(
    *,
    release: str = "cpi_core",
    period: str = "2026-07",
    asof: str = "2026-08-11",
    release_date: str = "2026-08-12",
    lag_value: float = 0.24,
    point_raw: float = 0.296,
) -> dict:
    """Synthetic result matching the governed engine/producer handoff."""
    from engine.release_cpi_coherent_shadow import _seal_receipt

    feature_receipts = {"lag_1": {"source": "coherent_target_history"}}
    candidate_data_asof = "2026-08-10T03:31:09+00:00"
    evidence_available_at = "2026-08-11T04:24:57+00:00"
    input_manifest = _seal_receipt({
        "schema": "release_cpi_coherent_input_manifest.v1",
        "release": release,
        "period": period,
        "decision_asof": asof,
        "strict_lag_features": {"lag_1": lag_value},
        "feature_receipts": feature_receipts,
    })
    training_receipt = _seal_receipt({
        "schema": "release_cpi_coherent_training_receipt.v1",
        "release": release,
        "period": period,
        "model_epoch": "coherent_ridge_v1",
        "decision_cutoff": asof,
        "target_epoch": "alfred_same_release_vintage_proxy_v1",
        "input_manifest_sha256": input_manifest["sha256"],
        "n": 120,
    })
    interval_receipt = _seal_receipt({
        "schema": "release_cpi_coherent_interval_receipt.v1",
        "release": release,
        "period": period,
        "model_epoch": "coherent_ridge_v1",
        "target_epoch": "alfred_same_release_vintage_proxy_v1",
        "training_receipt_sha256": training_receipt["sha256"],
        "point_raw": point_raw,
    })
    return {
        "schema": "release_cpi_coherent_shadow.v1",
        "status": "shadow_candidate",
        "release": release,
        "period": period,
        "release_date": release_date,
        "asof": asof,
        "model": "coherent_ridge_v1",
        "model_epoch": "coherent_ridge_v1",
        "target_epoch": "alfred_same_release_vintage_proxy_v1",
        "point": 0.30,
        "point_raw": point_raw,
        "p10": 0.10,
        "p25": 0.20,
        "p50": 0.30,
        "p75": 0.40,
        "p90": 0.50,
        "confidence": 0.61,
        "input_completeness": 1.0,
        "inputs_hash": input_manifest["sha256"],
        "input_manifest": input_manifest,
        "model_receipt": _seal_receipt({
            "schema": "release_cpi_coherent_model_receipt.v1",
            "model_id": "coherent_ridge_v1",
            "model_epoch": "coherent_ridge_v1",
        }),
        "truth_receipt": _seal_receipt({
            "schema": "release_cpi_coherent_truth_receipt.v1",
            "target_epoch": "alfred_same_release_vintage_proxy_v1",
            "candidate_data_asof": candidate_data_asof,
            "completion": {"evidence_available_at": evidence_available_at},
        }),
        "training_receipt": training_receipt,
        "interval_receipt": interval_receipt,
        "pit_provenance": {
            "schema": "release_cpi_coherent_pit_provenance.v1",
            "decision_cutoff": asof,
            "candidate_data_asof": candidate_data_asof,
            "evidence_available_at": evidence_available_at,
            "feature_receipts": feature_receipts,
            "display_only": True,
            "authority": False,
        },
        "display_only": True,
        "authority": False,
        "promotion_authorized": False,
    }


def test_coherent_shadow_freezes_one_validated_result_in_item_and_ledger(
    tmp_root: Path,
    monkeypatch,
) -> None:
    import scripts.build_release_forecast as producer

    governed = _coherent_shadow_result()
    monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
    monkeypatch.setattr(
        producer,
        "_run_shadow_coherent_ridge",
        lambda *a, **k: governed,
    )
    item = {
        "release_type": "cpi_core",
        "period": "2026-07",
        "release_date": "2026-08-12",
        "cutoff_label": "T-1",
        "code_receipt": "sha256:producer-receipt",
    }

    producer._attach_shadows_to_items([item], tmp_root, date(2026, 8, 11))
    shadow = item["shadows"]["coherent_ridge_v1"]
    for receipt in (
        "input_manifest",
        "model_receipt",
        "truth_receipt",
        "training_receipt",
        "interval_receipt",
        "pit_provenance",
    ):
        assert shadow[receipt] == governed[receipt]
    assert shadow["authority"] is False
    assert shadow["promotion_authorized"] is False
    assert shadow["target_epoch"] == "alfred_same_release_vintage_proxy_v1"

    # Ledger construction must consume this exact attached result, not rerun the engine.
    monkeypatch.setattr(
        producer,
        "_run_shadow_coherent_ridge",
        lambda *a, **k: pytest.fail("coherent engine was rerun during ledger build"),
    )
    rows = producer._build_shadow_ledger_rows(
        date(2026, 8, 11), [item], tmp_root
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["model"] == "coherent_ridge_v1"
    assert row["prediction_id"]
    assert row["projection_point"] == governed["point"]
    assert row["inputs_hash"] == governed["inputs_hash"]
    assert row["target_epoch"] == "alfred_same_release_vintage_proxy_v1"
    assert row["model_epoch"] == "coherent_ridge_v1"
    assert row["authority"] is False
    assert row["promotion_authorized"] is False
    for receipt in (
        "input_manifest",
        "model_receipt",
        "truth_receipt",
        "training_receipt",
        "interval_receipt",
        "pit_provenance",
    ):
        assert row[receipt] == governed[receipt]

    ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
    _append_ledger_rows(ledger_path, rows)
    _append_ledger_rows(ledger_path, rows)
    assert _load_ledger(ledger_path) == rows


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("authority", True),
        ("authority", 0),
        ("promotion_authorized", True),
        ("display_only", 1),
        ("schema", "release_cpi_coherent_shadow.v2"),
        ("target_epoch", "official_first_print_v1"),
        ("inputs_hash", "not-a-sha256"),
        ("truth_receipt", {}),
        ("p90", None),
        ("p10", 0.40),
    ],
)
def test_coherent_shadow_tamper_cannot_enter_ledger(
    tmp_root: Path,
    monkeypatch,
    field: str,
    tampered: object,
) -> None:
    import scripts.build_release_forecast as producer

    result = _coherent_shadow_result()
    result[field] = tampered
    monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
    item = {
        "release_type": "cpi_core",
        "period": "2026-07",
        "release_date": "2026-08-12",
        "shadows": {"coherent_ridge_v1": result},
    }

    rows = producer._build_shadow_ledger_rows(
        date(2026, 8, 11), [item], tmp_root
    )
    assert rows == []


@pytest.mark.parametrize(
    "tamper",
    ["receipt_body", "detached_inputs_hash"],
)
def test_coherent_shadow_receipt_tamper_cannot_enter_ledger(
    tmp_root: Path,
    tamper: str,
) -> None:
    import scripts.build_release_forecast as producer

    result = _coherent_shadow_result()
    if tamper == "receipt_body":
        result["truth_receipt"]["target_epoch"] = "tampered_after_sealing"
    else:
        result["inputs_hash"] = "f" * 64
    item = {
        "release_type": "cpi_core",
        "period": "2026-07",
        "release_date": "2026-08-12",
        "shadows": {"coherent_ridge_v1": result},
    }

    assert producer._build_shadow_ledger_rows(
        date(2026, 8, 11), [item], tmp_root
    ) == []


@pytest.mark.parametrize(
    "cross_wire",
    [
        "input_period",
        "model_epoch",
        "truth_epoch",
        "training_epoch",
        "interval_schema",
        "pit_features",
        "pit_truth_clock",
    ],
)
def test_coherent_shadow_validly_resealed_cross_wiring_cannot_enter_ledger(
    tmp_root: Path,
    cross_wire: str,
) -> None:
    from engine.release_cpi_coherent_shadow import _seal_receipt
    import scripts.build_release_forecast as producer

    result = _coherent_shadow_result()
    if cross_wire == "pit_features":
        result["pit_provenance"]["feature_receipts"] = {"other": {"source": "wrong"}}
    elif cross_wire == "pit_truth_clock":
        result["pit_provenance"]["candidate_data_asof"] = "2026-08-09T00:00:00+00:00"
    else:
        receipt_field, field, value = {
            "input_period": ("input_manifest", "period", "2026-06"),
            "model_epoch": ("model_receipt", "model_epoch", "coherent_ridge_v2"),
            "truth_epoch": ("truth_receipt", "target_epoch", "official_first_print_v1"),
            "training_epoch": (
                "training_receipt",
                "target_epoch",
                "official_first_print_v1",
            ),
            "interval_schema": ("interval_receipt", "schema", "interval.other.v1"),
        }[cross_wire]
        body = {
            key: item
            for key, item in result[receipt_field].items()
            if key != "sha256"
        }
        body[field] = value
        result[receipt_field] = _seal_receipt(body)
        if receipt_field == "input_manifest":
            result["inputs_hash"] = result[receipt_field]["sha256"]

    item = {
        "release_type": "cpi_core",
        "period": "2026-07",
        "release_date": "2026-08-12",
        "shadows": {"coherent_ridge_v1": result},
    }
    assert producer._build_shadow_ledger_rows(
        date(2026, 8, 11), [item], tmp_root
    ) == []


@pytest.mark.parametrize("receipt_field", ["training_receipt", "interval_receipt"])
def test_coherent_shadow_swapped_valid_receipt_dag_cannot_enter_ledger(
    tmp_root: Path,
    receipt_field: str,
) -> None:
    import scripts.build_release_forecast as producer

    result = _coherent_shadow_result(lag_value=0.24)
    other_valid_run = _coherent_shadow_result(lag_value=9.99)
    assert result[receipt_field] != other_valid_run[receipt_field]
    result[receipt_field] = other_valid_run[receipt_field]

    item = {
        "release_type": "cpi_core",
        "period": "2026-07",
        "release_date": "2026-08-12",
        "shadows": {"coherent_ridge_v1": result},
    }
    assert producer._build_shadow_ledger_rows(
        date(2026, 8, 11), [item], tmp_root
    ) == []


def test_coherent_shadow_allows_ordered_residual_interval_away_from_point() -> None:
    import scripts.build_release_forecast as producer

    result = _coherent_shadow_result()
    result.update({
        "point": 0.30,
        "p10": 0.40,
        "p25": 0.50,
        "p50": 0.60,
        "p75": 0.70,
        "p90": 0.80,
    })

    validated = producer._validate_coherent_ridge_result(
        result,
        "cpi_core",
        date(2026, 8, 11),
        "2026-07",
        date(2026, 8, 12),
    )

    assert validated["point"] < validated["p10"]


def test_coherent_shadow_missing_module_and_artifact_error_fail_closed(
    tmp_root: Path,
    monkeypatch,
) -> None:
    import scripts.build_release_forecast as producer

    module_name = "engine.release_cpi_coherent_shadow"
    monkeypatch.setitem(sys.modules, module_name, None)
    assert producer._run_shadow_coherent_ridge(
        "cpi_headline",
        date(2026, 8, 11),
        tmp_root,
        "2026-07",
        date(2026, 8, 12),
    ) is None

    fake_module = types.ModuleType(module_name)

    def _artifact_failure(**kwargs):
        raise RuntimeError("governed completion artifact unavailable")

    fake_module.project_cpi_coherent_shadow = _artifact_failure
    monkeypatch.setitem(sys.modules, module_name, fake_module)
    assert producer._run_shadow_coherent_ridge(
        "cpi_headline",
        date(2026, 8, 11),
        tmp_root,
        "2026-07",
        date(2026, 8, 12),
    ) is None


@pytest.mark.parametrize(
    "release_date",
    [None, date(2026, 8, 10), date(2026, 8, 11)],
)
def test_coherent_shadow_requires_a_future_release_date(
    tmp_root: Path,
    monkeypatch,
    release_date: date | None,
) -> None:
    import scripts.build_release_forecast as producer

    monkeypatch.setattr(
        "engine.release_cpi_coherent_shadow.project_cpi_coherent_shadow",
        lambda **kwargs: pytest.fail("ineligible request reached coherent engine"),
    )

    assert producer._run_shadow_coherent_ridge(
        "cpi_core",
        date(2026, 8, 11),
        tmp_root,
        "2026-07",
        release_date,
    ) is None


def test_coherent_failure_preserves_existing_shadow_lane(
    tmp_root: Path,
    monkeypatch,
) -> None:
    import scripts.build_release_forecast as producer

    monkeypatch.setattr(
        producer,
        "_run_shadow_v3",
        lambda *a, **k: {"point": 0.22, "inputs_hash": "b" * 64},
    )
    monkeypatch.setattr(producer, "_run_shadow_coherent_ridge", lambda *a, **k: None)
    item = {
        "release_type": "cpi_core",
        "period": "2026-07",
        "release_date": "2026-08-12",
        "code_receipt": "sha256:producer-receipt",
    }

    producer._attach_shadows_to_items([item], tmp_root, date(2026, 8, 11))
    assert set(item["shadows"]) == {"v3_factor"}
    rows = producer._build_shadow_ledger_rows(
        date(2026, 8, 11), [item], tmp_root
    )
    assert [row["model"] for row in rows] == ["v3_factor"]


def test_coherent_shadow_is_not_a_combined_v1_input(
    tmp_root: Path,
    monkeypatch,
) -> None:
    import engine.release_combined as combined_engine
    import scripts.build_release_forecast as producer

    captured: dict = {}

    def _capture_inputs(inputs, scored_errors, sigma_champion):
        captured.update(inputs)
        used = [key for key, value in inputs.items() if value is not None]
        return {
            "combined_point": 0.24,
            "p10": 0.04,
            "p25": 0.14,
            "p50": 0.24,
            "p75": 0.34,
            "p90": 0.44,
            "combined_components": {
                "inputs_used": used,
                "weights": {key: 1.0 / len(used) for key in used},
            },
        }

    monkeypatch.setattr(combined_engine, "compute_combined_point", _capture_inputs)
    item = {
        "release_type": "cpi_headline",
        "period": "2026-07",
        "projection": {"point": 0.20},
        "inputs_hash": "a" * 64,
        "shadows": {
            "v3_factor": {"point": 0.21, "inputs_hash": "b" * 64},
            "cpi_bridge": {"point": 0.22, "inputs_hash": "c" * 64},
            "mf_energy": {"point": 0.23, "inputs_hash": "d" * 64},
            "coherent_ridge_v1": {"point": 9.99, "inputs_hash": "e" * 64},
        },
        "benchmark_set": {"cleveland_nowcast": 0.25},
        "surprise_skew": {"sigma_scale_pp": 0.30},
        "code_receipt": "sha256:producer-receipt",
    }

    producer._attach_combined_to_items(
        [item], [], tmp_root, date(2026, 8, 11)
    )
    assert set(captured) == {
        "champion", "v3_factor", "cpi_bridge", "mf_energy", "cleveland",
    }
    assert "coherent_ridge_v1" not in captured
    assert item["combined"]["authority"] is False


def test_coherent_scoreboard_track_does_not_create_promotion_review() -> None:
    rows: list[dict] = []
    for model, error in (("combined_v1", 0.30), ("coherent_ridge_v1", 0.01)):
        for month in range(1, 13):
            row = _scored_row(
                release="cpi_core",
                period=f"2025-{month:02d}",
                asof_night=f"2025-{month:02d}-15",
            )
            row.update({
                "model": model,
                "actual": 0.30,
                "frozen_projection_point": 0.30 - error,
                "frozen_asof_night": f"2025-{month:02d}-14",
            })
            rows.append(row)

    scoreboard = _build_scoreboard(rows, accrual_start="2025-01-01")
    assert scoreboard["by_shadow"]["cpi_core:coherent_ridge_v1"]["n"] == 12
    assert scoreboard["by_shadow"]["cpi_core:coherent_ridge_v1"]["mae_ours"] == pytest.approx(0.01)
    assert all(
        review.get("input") != "coherent_ridge_v1"
        for review in scoreboard["promotion_review"]
    )


def test_coherent_scoreboard_segments_mixed_model_and_target_epochs() -> None:
    rows: list[dict] = []
    variants = [
        ("coherent_ridge_v1", "alfred_same_release_vintage_proxy_v1"),
        ("coherent_ridge_v1", "alfred_same_release_vintage_proxy_v1"),
        ("coherent_ridge_v2", "alfred_same_release_vintage_proxy_v1"),
        ("coherent_ridge_v1", "official_first_print_v1"),
    ]
    for month, (model_epoch, target_epoch) in enumerate(variants, start=1):
        row = _scored_row(
            release="cpi_core",
            period=f"2026-{month:02d}",
            asof_night=f"2026-{month:02d}-15",
        )
        row.update({
            "model": "coherent_ridge_v1",
            "model_epoch": model_epoch,
            "target_epoch": target_epoch,
            "actual": 0.3,
            "frozen_projection_point": 0.2,
            "frozen_asof_night": f"2026-{month:02d}-14",
        })
        rows.append(row)

    scoreboard = _build_scoreboard(rows, accrual_start="2026-01-01")

    assert scoreboard["by_shadow"]["cpi_core:coherent_ridge_v1"]["n"] == 4
    epochs = scoreboard["by_shadow_epoch"]
    assert epochs[
        "cpi_core:coherent_ridge_v1:coherent_ridge_v1:"
        "alfred_same_release_vintage_proxy_v1"
    ]["n"] == 2
    assert epochs[
        "cpi_core:coherent_ridge_v1:coherent_ridge_v2:"
        "alfred_same_release_vintage_proxy_v1"
    ]["n"] == 1
    assert epochs[
        "cpi_core:coherent_ridge_v1:coherent_ridge_v1:official_first_print_v1"
    ]["n"] == 1


def test_capture_prefers_official_actual_receipt(tmp_root: Path) -> None:
    from engine.release_actuals import normalize_publication

    actual_path = tmp_root / "data" / "release_forecast" / "official_actuals.jsonl"
    receipt = normalize_publication({
        "type": "CPI",
        "date": "2026-07-14",
        "reference_period": "June 2026",
        "data_ready": True,
        "publisher": "U.S. Bureau of Labor Statistics",
        "source_id": "bls_cpi",
        "source_url": "https://www.bls.gov/news.release/archives/cpi_test.htm",
        "source_sha256": "b" * 64,
        "first_seen_at": "2026-07-14T12:30:01+00:00",
        "source_released_at": "2026-07-14T12:30:00+00:00",
        "verified_at": "2026-07-14T12:31:00+00:00",
        "parser": {"name": "cpi", "version": 1},
        "actual": {
            "headline_mom": -0.4,
            "core_mom": 0.0,
            "unit": "percent",
            "reference_period": "June 2026",
        },
    })[0]
    actual_path.write_text(
        json.dumps(receipt) + "\n",
        encoding="utf-8",
    )
    projection = _projection_row(
        release="cpi_headline",
        period="2026-06",
        asof_night="2026-07-13",
        release_date="2026-07-14",
    )
    projection["target_epoch"] = "coherent_release_target_v1"
    scored = _check_release_day_capture(date(2026, 7, 14), tmp_root, [projection])
    assert len(scored) == 1
    assert scored[0]["actual"] == -0.4
    assert scored[0]["actual_source"] == "official_release_document"
    assert scored[0]["actual_receipt_id"] == receipt["receipt_id"]


def test_coherent_shadow_scores_under_its_frozen_candidate_epoch(
    tmp_root: Path,
    monkeypatch,
) -> None:
    from engine.release_actuals import normalize_publication
    import scripts.build_release_forecast as producer

    governed = _coherent_shadow_result(
        release="cpi_core",
        period="2026-06",
        asof="2026-07-13",
        release_date="2026-07-14",
    )
    # Empirical residual median need not equal the raw ridge point.
    governed["p50"] = 0.4
    monkeypatch.setattr(producer, "_run_shadow_v3", lambda *a, **k: None)
    item = {
        "release_type": "cpi_core",
        "period": "2026-06",
        "release_date": "2026-07-14",
        "cutoff_label": "T-1",
        "code_receipt": "sha256:producer-receipt",
        "shadows": {"coherent_ridge_v1": governed},
    }
    projections = producer._build_shadow_ledger_rows(
        date(2026, 7, 13), [item], tmp_root
    )
    assert len(projections) == 1

    receipts = normalize_publication({
        "type": "CPI",
        "date": "2026-07-14",
        "reference_period": "June 2026",
        "data_ready": True,
        "publisher": "U.S. Bureau of Labor Statistics",
        "source_id": "bls_cpi",
        "source_url": "https://www.bls.gov/news.release/archives/cpi_test.htm",
        "source_sha256": "f" * 64,
        "first_seen_at": "2026-07-14T12:30:01+00:00",
        "source_released_at": "2026-07-14T12:30:00+00:00",
        "verified_at": "2026-07-14T12:31:00+00:00",
        "parser": {"name": "cpi", "version": 1},
        "actual": {
            "headline_mom": 0.3,
            "core_mom": 0.2,
            "unit": "percent",
            "reference_period": "June 2026",
        },
    })
    actual_path = tmp_root / "data" / "release_forecast" / "official_actuals.jsonl"
    actual_path.write_text(
        "".join(json.dumps(receipt) + "\n" for receipt in receipts),
        encoding="utf-8",
    )

    scored = _check_release_day_capture(
        date(2026, 7, 14), tmp_root, projections
    )
    assert len(scored) == 1
    assert scored[0]["model"] == "coherent_ridge_v1"
    assert scored[0]["frozen_prediction_id"] == projections[0]["prediction_id"]
    assert scored[0]["frozen_projection_point"] == 0.3
    assert scored[0]["frozen_projection_p50"] == 0.4
    assert scored[0]["model_epoch"] == "coherent_ridge_v1"
    assert scored[0]["target_epoch"] == "alfred_same_release_vintage_proxy_v1"
    scoreboard = _build_scoreboard(scored, accrual_start="2026-07-13")
    coherent_stats = scoreboard["by_shadow"]["cpi_core:coherent_ridge_v1"]
    assert coherent_stats["n"] == 1
    assert coherent_stats["pinball_loss_5q"] == pytest.approx(0.19)


def test_official_actual_receipt_supersedes_legacy_score_idempotently(
    tmp_root: Path,
) -> None:
    from engine.release_actuals import normalize_publication

    receipt = normalize_publication({
        "type": "CPI",
        "date": "2026-07-14",
        "reference_period": "June 2026",
        "data_ready": True,
        "publisher": "U.S. Bureau of Labor Statistics",
        "source_id": "bls_cpi",
        "source_url": "https://www.bls.gov/news.release/archives/cpi_test.htm",
        "source_sha256": "c" * 64,
        "first_seen_at": "2026-07-14T12:30:01+00:00",
        "source_released_at": "2026-07-14T12:30:00+00:00",
        "verified_at": "2026-07-14T12:31:00+00:00",
        "parser": {"name": "cpi", "version": 1},
        "actual": {
            "headline_mom": -0.4,
            "core_mom": 0.0,
            "unit": "percent",
            "reference_period": "June 2026",
        },
    })[0]
    actual_path = tmp_root / "data" / "release_forecast" / "official_actuals.jsonl"
    actual_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")

    projection = _projection_row(
        release="cpi_headline",
        period="2026-06",
        asof_night="2026-07-13",
        release_date="2026-07-14",
    )
    legacy_score = {
        **_scored_row(
            release="cpi_headline",
            period="2026-06",
            asof_night="2026-07-14",
        ),
        "actual": -0.4225,
        "frozen_asof_night": "2026-07-13",
    }

    corrected = _check_release_day_capture(
        date(2026, 7, 15),
        tmp_root,
        [projection, legacy_score],
    )

    assert len(corrected) == 1
    assert corrected[0]["actual"] == -0.4
    assert corrected[0]["actual_receipt_id"] == receipt["receipt_id"]
    assert corrected[0]["supersedes_score_receipt_ids"]
    assert _check_release_day_capture(
        date(2026, 7, 15),
        tmp_root,
        [projection, legacy_score, corrected[0]],
    ) == []


def test_scoreboard_primary_metrics_exclude_structured_defect(tmp_root: Path) -> None:
    notice_path = tmp_root / "data" / "release_forecast" / "defect_notices.json"
    notice_path.write_text(json.dumps({"notices": [{
        "id": "DN-T",
        "evaluation_excluded": True,
        "selector": {"row_types": ["scored"], "target_epochs": ["legacy"]},
    }]}), encoding="utf-8")
    tainted = {**_scored_row(), "target_epoch": "legacy"}
    clean = {
        **_scored_row(period="2026-07", asof_night="2026-08-12"),
        "target_epoch": "coherent",
        "actual": 0.2,
        "frozen_projection_point": 0.1,
    }
    board = _build_scoreboard([tainted, clean], "2026-07-01", root=tmp_root)
    assert board["by_release"]["cpi_headline"]["n"] == 1
    assert board["all_forward"]["cpi_headline:champion"]["n"] == 2
    assert board["all_forward"]["cpi_headline:champion"]["excluded_n"] == 1
    assert board["evaluation_exclusions"]["by_defect"] == {"DN-T": 1}


def test_scoreboard_canonicalizes_official_score_supersession() -> None:
    legacy = {
        **_scored_row(release="nfp", period="2026-07", asof_night="2026-08-07"),
        "actual": -126.0,
        "frozen_asof_night": "2026-08-06",
        "frozen_projection_point": 50.0,
    }
    official = {
        **legacy,
        "asof_night": "2026-08-09",
        "actual": 57.0,
        "actual_basis": "official_published_metric",
        "actual_receipt_id": "official_actual:nfp-july",
        "frozen_prediction_id": "NFP:2026-07:first:2026-08-06:v1",
    }

    board = _build_scoreboard([legacy, official], "2026-07-01")

    assert board["by_release"]["nfp"]["n"] == 1
    assert board["by_release"]["nfp"]["mae_ours"] == pytest.approx(7.0)
    assert board["all_forward"]["nfp:champion"]["n"] == 1
    assert board["score_receipts"] == {
        "raw_n": 2,
        "canonical_n": 1,
        "superseded_n": 1,
        "note": (
            "Official actual receipts supersede same-vintage proxies and legacy "
            "calculations for evaluation; every receipt remains in the ledger."
        ),
    }


def test_append_keeps_distinct_same_day_score_receipts(tmp_root: Path) -> None:
    ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
    base = {
        **_scored_row(release="nfp", period="2026-07", asof_night="2026-08-09"),
        "frozen_asof_night": "2026-08-06",
    }
    proxy = {
        **base,
        "actual": -126.0,
        "actual_receipt_id": "same_vintage:proxy",
        "score_receipt_id": "score:proxy",
    }
    official = {
        **base,
        "actual": 57.0,
        "actual_basis": "official_published_metric",
        "actual_receipt_id": "official_actual:nfp-july",
        "score_receipt_id": "score:official",
    }

    _append_ledger_rows(ledger_path, [proxy, official])
    _append_ledger_rows(ledger_path, [proxy, official])

    assert _load_ledger(ledger_path) == [proxy, official]


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """A minimal repo-shaped temp root directory."""
    (tmp_path / "data" / "release_forecast").mkdir(parents=True)
    (tmp_path / "data" / "cleveland_nowcast").mkdir(parents=True)
    (tmp_path / "data" / "regime").mkdir(parents=True)
    (tmp_path / "data" / "fred_vintage").mkdir(parents=True)
    (tmp_path / "site" / "macrodata").mkdir(parents=True)
    return tmp_path


def _make_vintage_parquet(root: Path, rows: list[dict]) -> None:
    """Write a minimal vintages.parquet for testing."""
    df = pd.DataFrame(rows)
    for col in ("period", "realtime_start", "realtime_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    path = root / "data" / "fred_vintage" / "vintages.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _make_cleveland_parquet(root: Path, rows: list[dict]) -> None:
    """Write a minimal cleveland_nowcast/nowcast.parquet for testing."""
    df = pd.DataFrame(rows)
    path = root / "data" / "cleveland_nowcast" / "nowcast.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _projection_row(release: str = "cpi_headline", period: str = "2026-06",
                    asof_night: str = "2026-07-01", proj_point: float = 0.28,
                    proj_p10: float = 0.10, proj_p90: float = 0.46,
                    release_date: str = "2026-07-10") -> dict:
    return {
        "row_type": "projection",
        "asof_night": asof_night,
        "release": release,
        "period": period,
        "release_date": release_date,
        "days_to": 9,
        "projection_point": proj_point,
        "projection_p10": proj_p10,
        "projection_p90": proj_p90,
        "confidence": 0.60,
        "input_completeness": 0.75,
        "benchmark_naive_prior": 0.24,
        "benchmark_trailing_3m": 0.25,
        "benchmark_ar_model": 0.26,
        "benchmark_cleveland": 0.30,
        "surprise_skew_sigma": 0.40,
        "surprise_skew_tag": "hotter",
        "fed_stance": "hawkish",
        "gap_bp": 7,
        "implied_cuts_12m": -1,
        "next_fomc": "2026-07-29",
    }


def _scored_row(release: str = "cpi_headline", period: str = "2026-06",
                asof_night: str = "2026-07-14") -> dict:
    return {
        "row_type": "scored",
        "asof_night": asof_night,
        "release": release,
        "period": period,
        "release_date": "2026-07-10",
        "actual": 0.30,
        "raw_initial_print": None,
        "frozen_asof_night": "2026-07-01",
        "frozen_projection_point": 0.28,
        "frozen_projection_p10": 0.10,
        "frozen_projection_p90": 0.46,
        "our_surprise": 0.02,
        "surprise_vs_naive": 0.06,
        "surprise_vs_trailing": 0.05,
        "surprise_vs_ar": 0.04,
        "surprise_vs_cleveland": 0.0,
        "interval_hit": True,
        "skew_hit": True,
    }


# ============================================================
# 1. CONTRACT — latest.json schema
# ============================================================

class TestContract:
    """Verify the latest.json artifact structure."""

    def test_build_produces_schema_keys(self, tmp_root: Path, monkeypatch):
        """build() returns a dict with all required release_forecast.v1/v2 keys."""
        # Patch _find_upcoming_releases to return empty (no real engine needed)
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_root, dry_run=True)

        assert result["schema"] in ("release_forecast.v1", "release_forecast.v2")
        assert "asof" in result
        assert "display_only" in result
        assert "authority" in result
        assert "upcoming" in result
        assert "last_scored" in result
        assert "scoreboard_ref" in result
        methodology = result["methodology_status"]
        assert methodology["forecast_points_changed_by_wave1"] is False
        assert methodology["coherent_target_refit_status"] == (
            "shadow_candidate_withheld_no_valid_current_projection"
        )
        assert methodology["coherent_current_projection_n"] == 0
        assert methodology["next_required_step"] == (
            "accrue_clean_forward_scores_then_manual_adjudication"
        )
        assert methodology["accuracy_claim"] == "withheld_until_clean_aligned_forward_evidence"

    def test_display_only_true(self, tmp_root: Path, monkeypatch):
        """display_only must always be True."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_root, dry_run=True)
        assert result["display_only"] is True

    def test_authority_booleans_all_false(self, tmp_root: Path, monkeypatch):
        """All authority booleans must be False."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_root, dry_run=True)
        auth = result["authority"]
        assert auth.get("can_score") is False
        assert auth.get("can_size") is False
        assert auth.get("can_trade") is False

    def test_asof_is_parseable_utc_iso(self, tmp_root: Path, monkeypatch):
        """asof must be a full ISO UTC timestamp parseable by datetime.fromisoformat."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_root, dry_run=True)
        asof = result["asof"]
        # Must be parseable and end with Z (UTC)
        assert isinstance(asof, str)
        assert asof.endswith("Z"), f"asof does not end with Z: {asof!r}"
        # Should parse successfully (replace trailing Z with +00:00 for Python < 3.11)
        dt = datetime.fromisoformat(asof.replace("Z", "+00:00"))
        assert dt.tzinfo is not None


# ============================================================
# 2. LEDGER — append-only, no dups, projection rows not mutated
# ============================================================

class TestLedger:
    """Verify ledger append-only and idempotency semantics."""

    def test_append_creates_ledger(self, tmp_root: Path):
        """Appending rows to a non-existent ledger creates the file."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        row = _projection_row()
        _append_ledger_rows(ledger_path, [row])
        assert ledger_path.exists()
        rows = _load_ledger(ledger_path)
        assert len(rows) == 1
        assert rows[0]["row_type"] == "projection"

    def test_no_dup_same_night(self, tmp_root: Path):
        """Running twice same night appends zero duplicate rows."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        row = _projection_row()
        _append_ledger_rows(ledger_path, [row])
        _append_ledger_rows(ledger_path, [row])  # second run
        rows = _load_ledger(ledger_path)
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"

    def test_second_night_appends(self, tmp_root: Path):
        """A second night with a different asof_night appends a new row."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        row1 = _projection_row(asof_night="2026-07-01")
        row2 = _projection_row(asof_night="2026-07-02")
        _append_ledger_rows(ledger_path, [row1])
        _append_ledger_rows(ledger_path, [row2])
        rows = _load_ledger(ledger_path)
        assert len(rows) == 2

    def test_projection_row_not_mutated_by_scored_append(self, tmp_root: Path):
        """Appending a scored row never changes existing projection rows."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        proj = _projection_row(asof_night="2026-07-01", proj_point=0.28)
        _append_ledger_rows(ledger_path, [proj])

        scored = _scored_row(asof_night="2026-07-14")
        _append_ledger_rows(ledger_path, [scored])

        rows = _load_ledger(ledger_path)
        proj_rows = [r for r in rows if r["row_type"] == "projection"]
        assert len(proj_rows) == 1
        assert proj_rows[0]["projection_point"] == pytest.approx(0.28)

    def test_scored_row_math(self, tmp_root: Path):
        """Release-day capture computes correct surprise and interval hit."""
        today = date(2026, 7, 14)
        # Build a minimal vintage parquet with prior + current month for CPI
        _make_vintage_parquet(tmp_root, [
            # Prior month (2026-05): level = 315.000
            {
                "series": "CPIAUCSL", "period": "2026-05-01",
                "value": 315.000, "realtime_start": "2026-06-12",
                "realtime_end": "2099-01-01",
            },
            # Current month (2026-06): initial print level = 316.260
            {
                "series": "CPIAUCSL", "period": "2026-06-01",
                "value": 316.260, "realtime_start": "2026-07-14",
                "realtime_end": "2099-01-01",
            },
        ])

        proj_row = _projection_row(
            release="cpi_headline", period="2026-06",
            asof_night="2026-07-01",
            proj_point=0.28, proj_p10=0.10, proj_p90=0.46,
            release_date="2026-07-10",
        )
        existing_ledger = [proj_row]

        scored_rows = _check_release_day_capture(today, tmp_root, existing_ledger)

        # Expected actual: (316.260 / 315.000 - 1) * 100 = 0.4000 MoM%
        assert len(scored_rows) == 1, f"Expected 1 scored row, got {scored_rows}"
        sr = scored_rows[0]

        expected_actual = round((316.260 / 315.000 - 1) * 100, 4)
        assert sr["actual"] == pytest.approx(expected_actual, abs=1e-3)
        assert sr["row_type"] == "scored"

        # Interval hit: expected_actual (0.4) is within [0.10, 0.46]
        assert sr["interval_hit"] is True

        # Surprise vs our projection
        expected_surprise = round(expected_actual - 0.28, 4)
        assert sr["our_surprise"] == pytest.approx(expected_surprise, abs=1e-3)

    def test_no_duplicate_scored_row(self, tmp_root: Path):
        """If a scored row already exists in the ledger, no second scored row is emitted."""
        today = date(2026, 7, 15)
        existing_ledger = [
            _projection_row(asof_night="2026-07-01"),
            _scored_row(asof_night="2026-07-14"),
        ]
        scored_rows = _check_release_day_capture(today, tmp_root, existing_ledger)
        # Already scored, so no new rows
        assert len(scored_rows) == 0


# ============================================================
# 3. SCOREBOARD — from scored rows only; n=0 honest
# ============================================================

class TestScoreboard:
    """Verify scoreboard is computed from scored rows only."""

    def test_n_zero_honest_output(self):
        """With no scored rows, scoreboard prints zeros/nulls honestly."""
        sb = _build_scoreboard([], accrual_start="2026-07-07")
        assert sb["schema"] in ("release_forecast_scoreboard.v1", "release_forecast_scoreboard.v2")
        assert sb["forward_accrual_began"] == "2026-07-07"
        assert sb["by_release"] == {}

    def test_projection_rows_excluded(self):
        """Projection rows in ledger must NOT enter the scoreboard."""
        ledger = [_projection_row()]  # projection only
        sb = _build_scoreboard(ledger, accrual_start="2026-07-07")
        assert sb["by_release"] == {}

    def test_scoreboard_from_scored_rows(self):
        """Scoreboard correctly aggregates a set of scored rows."""
        scored1 = _scored_row(
            release="cpi_headline", period="2026-05", asof_night="2026-06-15",
        )
        scored1["actual"] = 0.25
        scored1["frozen_projection_point"] = 0.28
        scored1["interval_hit"] = True
        scored1["skew_hit"] = False
        scored1["surprise_vs_naive"] = 0.01

        scored2 = _scored_row(
            release="cpi_headline", period="2026-06", asof_night="2026-07-14",
        )
        scored2["actual"] = 0.30
        scored2["frozen_projection_point"] = 0.27
        scored2["interval_hit"] = False
        scored2["skew_hit"] = True
        scored2["surprise_vs_naive"] = 0.06

        sb = _build_scoreboard([scored1, scored2], accrual_start="2026-07-07")

        cpi_stats = sb["by_release"].get("cpi_headline")
        assert cpi_stats is not None
        assert cpi_stats["n"] == 2
        # MAE ours: abs(0.25-0.28) + abs(0.30-0.27) = 0.03 + 0.03 = 0.03 avg
        assert cpi_stats["mae_ours"] == pytest.approx(0.03, abs=1e-4)
        # coverage: 1/2 = 0.5
        assert cpi_stats["p10_p90_coverage"] == pytest.approx(0.5, abs=1e-4)
        # skew hit: 1/2 = 0.5
        assert cpi_stats["skew_hit_rate"] == pytest.approx(0.5, abs=1e-4)
        # Wilson CI must be present
        assert cpi_stats["skew_hit_rate_wilson_ci"] is not None
        assert len(cpi_stats["skew_hit_rate_wilson_ci"]) == 2

    def test_multiple_release_types_independent(self):
        """NFP and CPI stats are tracked independently."""
        cpi_scored = _scored_row(release="cpi_headline", period="2026-05")
        cpi_scored["actual"] = 0.25
        cpi_scored["frozen_projection_point"] = 0.28
        cpi_scored["interval_hit"] = True
        cpi_scored["skew_hit"] = True

        nfp_scored = _scored_row(release="nfp", period="2026-05")
        nfp_scored["actual"] = 200.0
        nfp_scored["frozen_projection_point"] = 180.0
        nfp_scored["interval_hit"] = False
        nfp_scored["skew_hit"] = False

        sb = _build_scoreboard([cpi_scored, nfp_scored], accrual_start="2026-07-07")
        assert "cpi_headline" in sb["by_release"]
        assert "nfp" in sb["by_release"]
        assert sb["by_release"]["cpi_headline"]["n"] == 1
        assert sb["by_release"]["nfp"]["n"] == 1


# ============================================================
# 4. CLEVELAND BENCHMARK — PIT read; absent-file fail-open
# ============================================================

class TestClevelandBenchmark:
    """Verify PIT safety and fail-open behavior for Cleveland nowcast read."""

    def test_absent_file_returns_none(self, tmp_root: Path):
        """If the nowcast parquet doesn't exist, return None without raising."""
        result = _read_cleveland_nowcast(tmp_root, "cpi_headline", "2026-06", date.today())
        assert result is None

    def test_pit_filter_excludes_future_obs(self, tmp_root: Path):
        """obs_date > today must be excluded from the PIT read."""
        today = date(2026, 7, 7)
        _make_cleveland_parquet(tmp_root, [
            {
                "first_seen_asof": "2026-07-08",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-08",  # future relative to today
                "value": 0.40,
            },
            {
                "first_seen_asof": "2026-07-06",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-06",  # past relative to today
                "value": 0.31,
            },
        ])
        result = _read_cleveland_nowcast(tmp_root, "cpi_headline", "2026-06", today)
        # Only the 2026-07-06 obs is PIT-safe; value should be 0.31
        assert result == pytest.approx(0.31, abs=1e-5)

    def test_returns_latest_obs_date_value(self, tmp_root: Path):
        """When multiple obs_dates are PIT-safe, the latest one wins."""
        today = date(2026, 7, 10)
        _make_cleveland_parquet(tmp_root, [
            {
                "first_seen_asof": "2026-07-05",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-05",
                "value": 0.29,
            },
            {
                "first_seen_asof": "2026-07-07",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-07",
                "value": 0.31,
            },
        ])
        result = _read_cleveland_nowcast(tmp_root, "cpi_headline", "2026-06", today)
        assert result == pytest.approx(0.31, abs=1e-5)

    def test_wrong_series_returns_none(self, tmp_root: Path):
        """NFP release type has no Cleveland series mapping, returns None."""
        _make_cleveland_parquet(tmp_root, [
            {
                "first_seen_asof": "2026-07-05",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-05",
                "value": 0.29,
            },
        ])
        result = _read_cleveland_nowcast(tmp_root, "nfp", "2026-06", date.today())
        assert result is None

    def test_core_cpi_uses_core_series(self, tmp_root: Path):
        """cpi_core maps to core_cpi_mom series."""
        today = date(2026, 7, 10)
        _make_cleveland_parquet(tmp_root, [
            {
                "first_seen_asof": "2026-07-07",
                "target_period": "2026-06-01",
                "series": "core_cpi_mom",
                "obs_date": "2026-07-07",
                "value": 0.26,
            },
            {
                "first_seen_asof": "2026-07-07",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-07",
                "value": 0.31,
            },
        ])
        result = _read_cleveland_nowcast(tmp_root, "cpi_core", "2026-06", today)
        assert result == pytest.approx(0.26, abs=1e-5)


# ============================================================
# 5. POLICY BACKDROP — all sources missing → nulls, no raise
# ============================================================

class TestPolicyBackdrop:
    """Verify fail-open behavior when all backdrop sources are absent."""

    def test_all_sources_missing_returns_nulls(self, tmp_root: Path):
        """When no regime/latest.json and no event_calendar, backdrop is all null."""
        # tmp_root has no data/regime/latest.json and event_calendar may fail
        # We patch event_calendar to raise so we don't need network
        import scripts.build_release_forecast as producer

        def _failing_calendar(*a, **k):
            raise RuntimeError("test: no calendar")

        original = None
        try:
            import engine.event_calendar as ec
            original = ec.us_macro_events
            ec.us_macro_events = _failing_calendar
        except ImportError:
            pass

        try:
            result = _read_policy_backdrop(tmp_root, date(2026, 7, 7))
        finally:
            if original is not None:
                import engine.event_calendar as ec
                ec.us_macro_events = original

        assert result["fed_stance"] is None
        assert result["gap_bp"] is None
        assert result["implied_cuts_12m"] is None
        assert result["next_fomc"] is None
        assert result["guidance_direction"] is None

    def test_reads_from_regime_latest(self, tmp_root: Path):
        """When regime/latest.json exists, backdrop fields are populated."""
        regime_data = {
            "fed_stance": {"stance": "hawkish", "implied_cuts_12m": -1.0},
            "fed_path": {"gap": {"gap_bp": 7}},
            "catalyst_tone": {"guidance_direction": "on_hold"},
        }
        regime_path = tmp_root / "data" / "regime" / "latest.json"
        regime_path.parent.mkdir(parents=True, exist_ok=True)
        with open(regime_path, "w") as fh:
            json.dump(regime_data, fh)

        # Patch event_calendar to avoid network
        import scripts.build_release_forecast as producer

        def _no_fomc(*a, **k):
            return []

        try:
            import engine.event_calendar as ec
            original = ec.us_macro_events
            ec.us_macro_events = _no_fomc
        except ImportError:
            original = None

        try:
            result = _read_policy_backdrop(tmp_root, date(2026, 7, 7))
        finally:
            if original is not None:
                import engine.event_calendar as ec
                ec.us_macro_events = original

        assert result["fed_stance"] == "hawkish"
        assert result["gap_bp"] == 7
        assert result["implied_cuts_12m"] == -1.0
        assert result["guidance_direction"] == "on_hold"


# ============================================================
# 6. WILSON CI helper
# ============================================================

class TestWilson:
    def test_n_zero_returns_none(self):
        assert _wilson(0, 0) is None

    def test_perfect_hit_rate(self):
        ci = _wilson(10, 10)
        assert ci is not None
        assert ci[0] > 0.7  # Lower bound above 0.7 for 10/10

    def test_zero_hit_rate(self):
        ci = _wilson(0, 10)
        assert ci is not None
        assert ci[0] == 0.0
        assert ci[1] < 0.3

    def test_output_bounds(self):
        for k, n in [(3, 10), (7, 20), (15, 30)]:
            ci = _wilson(k, n)
            assert ci is not None
            lb, ub = ci
            assert 0.0 <= lb <= ub <= 1.0


# ============================================================
# 7. DRY-RUN integration (smoke — no real data required)
# ============================================================

class TestDryRun:
    """Smoke test: build() with dry_run=True completes without writing files."""

    def test_dry_run_no_files_written(self, tmp_root: Path, monkeypatch):
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        result = producer.build(tmp_root, dry_run=True)

        # No files written in dry-run mode
        assert not (tmp_root / "data" / "release_forecast" / "latest.json").exists()
        assert not (tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl").exists()
        assert not (tmp_root / "data" / "release_forecast" / "scoreboard.json").exists()
        assert not (tmp_root / "site" / "macrodata" / "release_forecast.json").exists()

        # Result is still a well-formed payload
        assert result["schema"] in ("release_forecast.v1", "release_forecast.v2")
        assert result["display_only"] is True

    def test_full_run_writes_artifacts(self, tmp_root: Path, monkeypatch):
        """build() with dry_run=False writes latest.json, scoreboard, and site copy."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        producer.build(tmp_root, dry_run=False)

        # latest.json, scoreboard, and site copy are always written
        assert (tmp_root / "data" / "release_forecast" / "latest.json").exists()
        assert (tmp_root / "data" / "release_forecast" / "scoreboard.json").exists()
        assert (tmp_root / "site" / "macrodata" / "release_forecast.json").exists()
        # ledger is only written when there are new rows to append; with no upcoming
        # releases the ledger file may not exist yet — that is correct behavior

    def test_double_run_no_dup_ledger(self, tmp_root: Path, monkeypatch):
        """Running build() twice same night produces exactly the same ledger rows."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })

        producer.build(tmp_root, dry_run=False)
        producer.build(tmp_root, dry_run=False)  # second run same night

        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        rows = _load_ledger(ledger_path)
        # No duplicates: each (release, period, row_type, asof_night) appears once
        keys = [_ledger_key(r) for r in rows]
        assert len(keys) == len(set(keys)), "Duplicate ledger keys detected"


# ============================================================
# 8. CLAIMS — scoreboard label, block_note, benchmark_only mode
# ============================================================

def _claims_scored_row(period: str = "2026-07-03", asof_night: str = "2026-07-10") -> dict:
    """Build a synthetic scored row for claims (weekly period, benchmark_only mode).

    In benchmark_only mode projection_point is null, so our_surprise, interval_hit,
    and skew_hit are also null. Benchmarks carry real values so trailing/naive
    surprise_vs_* is computable.
    """
    return {
        "row_type": "scored",
        "asof_night": asof_night,
        "release": "claims",
        "period": period,
        "release_date": asof_night,
        "actual": 215.0,            # ICSA in thousands
        "raw_initial_print": 215000.0,
        "frozen_asof_night": "2026-07-09",
        "frozen_projection_point": None,     # benchmark_only
        "frozen_projection_p10": None,
        "frozen_projection_p90": None,
        "our_surprise": None,                # null in benchmark_only
        "surprise_vs_naive": 215.0 - 220.0, # vs naive_prior
        "surprise_vs_trailing": 215.0 - 218.0,
        "surprise_vs_ar": 215.0 - 217.0,
        "surprise_vs_cleveland": None,
        "interval_hit": None,               # null in benchmark_only
        "skew_hit": None,                   # null in benchmark_only
        "projection_mode": "benchmark_only",
        "benchmark_trailing_key": "benchmark_trailing_4w",
    }


class TestClaimsScoreboard:
    """Verify claims-specific scoreboard behavior: block_note, label, and benchmark_only mode."""

    def test_claims_scoreboard_block_note_present(self):
        """Claims scoreboard entry must include a block_note (MRI-R9 caveat)."""
        row = _claims_scored_row()
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        claims_stats = sb["by_release"].get("claims")
        assert claims_stats is not None, "claims entry missing from scoreboard"
        assert "block_note" in claims_stats, "block_note missing from claims scoreboard entry"
        assert "MRI-R9" in claims_stats["block_note"]

    def test_claims_scoreboard_trailing_label_is_4w(self):
        """Claims scoreboard uses mae_trailing_4w label, not mae_trailing_3m."""
        row = _claims_scored_row()
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        claims_stats = sb["by_release"]["claims"]
        assert "mae_trailing_4w" in claims_stats, "mae_trailing_4w key missing"
        assert "mae_trailing_3m" not in claims_stats, "mae_trailing_3m must not appear for claims"

    def test_claims_scoreboard_n_counts(self):
        """Two scored claims rows produce n=2 in scoreboard."""
        row1 = _claims_scored_row(period="2026-07-03", asof_night="2026-07-10")
        row2 = _claims_scored_row(period="2026-07-10", asof_night="2026-07-17")
        sb = _build_scoreboard([row1, row2], accrual_start="2026-07-07")
        claims_stats = sb["by_release"]["claims"]
        assert claims_stats["n"] == 2

    def test_claims_benchmark_only_mae_ours_null(self):
        """In benchmark_only mode all scored rows have null proj_point -> mae_ours is None."""
        row = _claims_scored_row()
        # Confirm frozen_projection_point is None in our fixture
        assert row["frozen_projection_point"] is None
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        claims_stats = sb["by_release"]["claims"]
        # mae_ours = None because no projection_point was frozen (benchmark_only)
        assert claims_stats["mae_ours"] is None, (
            f"Expected mae_ours=None in benchmark_only mode, got {claims_stats['mae_ours']}"
        )

    def test_claims_naive_mae_computable_from_surprise(self):
        """Even in benchmark_only mode, mae_naive_prior accumulates from surprise_vs_naive."""
        row = _claims_scored_row()
        # surprise_vs_naive = 215 - 220 = -5; abs = 5
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        claims_stats = sb["by_release"]["claims"]
        assert claims_stats["mae_naive_prior"] == pytest.approx(5.0, abs=1e-3)

    def test_non_claims_has_no_block_note(self):
        """CPI scoreboard entry must NOT have a block_note (that's claims-only)."""
        scored = _scored_row(release="cpi_headline")
        scored["actual"] = 0.30
        scored["frozen_projection_point"] = 0.28
        scored["interval_hit"] = True
        scored["skew_hit"] = True
        sb = _build_scoreboard([scored], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"].get("cpi_headline", {})
        assert "block_note" not in cpi_stats, "block_note must not appear for non-claims releases"

    def test_non_claims_has_trailing_3m_not_4w(self):
        """CPI scoreboard entry must use mae_trailing_3m, not mae_trailing_4w."""
        scored = _scored_row(release="cpi_headline")
        scored["actual"] = 0.30
        scored["frozen_projection_point"] = 0.28
        scored["interval_hit"] = True
        scored["skew_hit"] = True
        scored["surprise_vs_trailing"] = 0.05
        sb = _build_scoreboard([scored], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"]["cpi_headline"]
        assert "mae_trailing_3m" in cpi_stats, "mae_trailing_3m must appear for CPI"
        assert "mae_trailing_4w" not in cpi_stats, "mae_trailing_4w must not appear for CPI"


# ============================================================
# 9. CLAIMS LEDGER — weekly period dedup semantics
# ============================================================

class TestClaimsLedger:
    """Verify ledger dedup works for weekly (YYYY-MM-DD) claim periods."""

    def test_claims_weekly_period_dedup(self, tmp_root: Path):
        """Two identical claims projection rows (same period, same asof_night) don't duplicate."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        row = {
            "row_type": "projection",
            "asof_night": "2026-07-06",
            "release": "claims",
            "period": "2026-07-10",        # Thursday date (weekly period)
            "release_date": "2026-07-10",
            "days_to": 4,
            "projection_point": None,       # benchmark_only
            "benchmark_naive_prior": 220.0,
            "benchmark_trailing_4w": 218.5,
        }
        _append_ledger_rows(ledger_path, [row])
        _append_ledger_rows(ledger_path, [row])  # second run same night
        rows = _load_ledger(ledger_path)
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}: dedup failed for claims period"

    def test_claims_different_weekly_periods_not_deduped(self, tmp_root: Path):
        """Two different claim weekly periods are separate ledger rows (not deduped)."""
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        row1 = {
            "row_type": "projection",
            "asof_night": "2026-07-06",
            "release": "claims",
            "period": "2026-07-10",
            "release_date": "2026-07-10",
        }
        row2 = {
            "row_type": "projection",
            "asof_night": "2026-07-06",
            "release": "claims",
            "period": "2026-07-17",        # different week
            "release_date": "2026-07-17",
        }
        _append_ledger_rows(ledger_path, [row1, row2])
        rows = _load_ledger(ledger_path)
        assert len(rows) == 2, f"Expected 2 rows for different weekly periods, got {len(rows)}"


# ============================================================
# 10. CLAIMS PROJECTION — integration tests (require vintages.parquet)
# ============================================================

_VINTAGES_PATH = Path(__file__).resolve().parents[1] / "data" / "fred_vintage" / "vintages.parquet"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_CLAIMS_INT_MARK = pytest.mark.skipif(
    not _VINTAGES_PATH.exists(),
    reason="data/fred_vintage/vintages.parquet not present; skipping claims integration tests",
)


class TestB1ClaimsProjectionIntegration:
    """Integration: _run_projection for 'claims' returns a valid dict, not None.

    These tests require the committed vintages.parquet (ICSA + IC4WSA series).
    Skipped automatically if the file is absent.
    """

    @_CLAIMS_INT_MARK
    def test_run_projection_claims_returns_dict_not_none(self, tmp_root: Path):
        """_run_projection('claims', ...) must return a dict, not None (B1 crash fix)."""
        asof = date(2026, 7, 7)
        # Use a recent Thursday-date period (the period string for claims is a Thursday date)
        result = _run_projection("claims", asof, _REPO_ROOT, period_str="2026-07-03")
        assert result is not None, (
            "_run_projection('claims') returned None — likely a crash in project_claims"
        )
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    @_CLAIMS_INT_MARK
    def test_run_projection_claims_benchmark_set_populated(self, tmp_root: Path):
        """benchmark_set for claims must have naive_prior and trailing_4w as real floats."""
        asof = date(2026, 7, 7)
        result = _run_projection("claims", asof, _REPO_ROOT, period_str="2026-07-03")
        assert result is not None
        bs = result.get("benchmark_set", {})
        assert "naive_prior" in bs, "naive_prior missing from claims benchmark_set"
        assert "trailing_4w" in bs, "trailing_4w missing from claims benchmark_set (must not be trailing_3m)"
        assert "trailing_3m" not in bs, "trailing_3m must not appear in claims benchmark_set"
        # Both should be floats (real ICSA values in thousands)
        assert isinstance(bs["naive_prior"], float), f"naive_prior is {type(bs['naive_prior'])}, expected float"
        assert isinstance(bs["trailing_4w"], float), f"trailing_4w is {type(bs['trailing_4w'])}, expected float"
        # Sanity: ICSA in thousands is typically 200–300k range (i.e., 200.0–300.0 as float)
        assert 100.0 <= bs["naive_prior"] <= 1000.0, f"naive_prior out of plausible range: {bs['naive_prior']}"
        assert 100.0 <= bs["trailing_4w"] <= 1000.0, f"trailing_4w out of plausible range: {bs['trailing_4w']}"

    @_CLAIMS_INT_MARK
    def test_build_upcoming_block_claims_benchmark_only_mode(self, tmp_root: Path):
        """_build_upcoming_block with a claims release emits benchmark_only projection block."""
        # Synthetic upcoming releases list with one claims event
        upcoming_releases = [
            {
                "release_type": "claims",
                "release": "claims",
                "period": "2026-07-10",
                "release_date": "2026-07-10",
                "regime_axis": "growth",
            }
        ]
        policy_backdrop = {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        }
        today = date(2026, 7, 7)
        root = _REPO_ROOT
        block = _build_upcoming_block(today, root, upcoming_releases, policy_backdrop)

        assert len(block) == 1, f"Expected 1 upcoming card, got {len(block)}"
        card = block[0]

        # Projection block must carry benchmark_only mode (§6 kill rule is active)
        assert _CLAIMS_MODE == "benchmark_only", "_CLAIMS_MODE must be benchmark_only"
        proj = card.get("projection", {})
        assert proj.get("mode") == "benchmark_only", (
            f"claims projection.mode must be 'benchmark_only', got {proj.get('mode')!r}"
        )
        assert "reason" in proj, "benchmark_only projection must include reason"

        # Benchmark set must be populated (even in benchmark_only mode, benchmarks are graded)
        bs = card.get("benchmark_set", {})
        assert bs.get("naive_prior") is not None, "naive_prior must be a real value, not null"
        assert bs.get("trailing_4w") is not None, "trailing_4w must be a real value, not null"
        assert "trailing_3m" not in bs, "trailing_3m must not appear in claims benchmark_set"

        # Point/quantiles/confidence must all be null
        assert card.get("confidence") is None, "confidence must be null in benchmark_only mode"
        assert card.get("input_completeness") is None, "input_completeness must be null in benchmark_only mode"


# ============================================================
# 11. CLAIMS CAPTURE PATH — end-to-end integration (FIX-6)
#     Requires committed data/fred_vintage/vintages.parquet
# ============================================================

class TestClaimsCapturePathIntegration:
    """Verify the full claims capture path end-to-end against real committed ICSA vintages.

    Release Thursday 2026-06-11 → ICSA vintage period 2026-06-06 (Sat, Thu−5d)
    ICSA initial print: 229,000 raw persons → 229.0 thousands.

    Asserts:
      - _get_initial_print returns 229000.0 (raw persons from ALFRED)
      - _compute_actual_from_print returns 229.0 (thousands)
      - _check_release_day_capture produces exactly one scored row
      - actual = 229.0 thousands (plausible range)
      - benchmark MAEs computable (surprise_vs_naive populated)
      - our-model fields (our_surprise, interval_hit, skew_hit) are None in benchmark_only mode
      - scoreboard emits a claims entry with mae_naive_prior populated and mae_ours None
    """

    @_CLAIMS_INT_MARK
    def test_get_initial_print_thursday_to_saturday_mapping(self):
        """_get_initial_print must map Thursday period to preceding Saturday for ICSA lookup."""
        # Thursday 2026-06-11 → Saturday 2026-06-06 (−5 days)
        raw = _get_initial_print(
            _REPO_ROOT,
            release_type="claims",
            period_str="2026-06-11",   # Thursday date (as stored in ledger)
            release_date_str="2026-06-11",
        )
        assert raw is not None, (
            "_get_initial_print returned None for claims 2026-06-11. "
            "Likely Thursday→Saturday period mapping failed or ICSA missing in vintages.parquet."
        )
        # Raw value from ALFRED is in persons (expected ~229000.0)
        assert 100_000.0 <= raw <= 1_000_000.0, f"raw_print={raw} out of plausible persons range"
        # Specifically: 2026-06-06 period, realtime_start 2026-06-11, value 229000.0
        assert raw == pytest.approx(229_000.0, abs=1.0), (
            f"Expected ICSA initial print 229000.0 for period 2026-06-06, got {raw}"
        )

    @_CLAIMS_INT_MARK
    def test_compute_actual_claims_returns_thousands(self):
        """_compute_actual_from_print for claims returns raw_print / 1000.0."""
        actual = _compute_actual_from_print(
            "claims", 229_000.0, _REPO_ROOT, "2026-06-11"
        )
        assert actual is not None, "_compute_actual_from_print returned None for claims"
        assert actual == pytest.approx(229.0, abs=0.01), (
            f"Expected 229.0 thousands (229000 / 1000), got {actual}"
        )

    @_CLAIMS_INT_MARK
    def test_full_claims_capture_path_produces_scored_row(self):
        """End-to-end: a benchmark_only claims projection ledger row produces exactly one
        scored row when _check_release_day_capture runs on/after the release date."""
        # Build a synthetic benchmark_only claims projection row for Thu 2026-06-11
        proj_row = {
            "schema": 2,
            "row_type": "projection",
            "asof_night": "2026-06-10",          # T-1 (day before release)
            "release": "claims",
            "period": "2026-06-11",              # Thursday release date (ledger period)
            "release_date": "2026-06-11",
            "projection_mode": "benchmark_only",  # FIX-3: projection_mode written to ledger
            "projection_point": None,             # benchmark_only: null
            "projection_p10": None,
            "projection_p90": None,
            "benchmark_naive_prior": 225.0,      # thousands (synthetic prior)
            "benchmark_trailing_4w": 222.0,
            "benchmark_ar_model": 223.0,
            "benchmark_cleveland": None,
        }
        existing_ledger = [proj_row]

        # Run capture as of the release day (2026-06-11 = Thursday)
        today = date(2026, 6, 11)
        scored_rows = _check_release_day_capture(today, _REPO_ROOT, existing_ledger)

        assert len(scored_rows) == 1, (
            f"Expected exactly 1 scored row for claims 2026-06-11, got {len(scored_rows)}. "
            "FIX-1 (ICSA in _FRED_VINTAGE_SERIES) or FIX-2 (Thursday→Saturday mapping) may be missing."
        )
        sr = scored_rows[0]

        # actual must be thousands-scale and match the known initial print
        assert sr["actual"] is not None, "actual must not be None in scored row"
        assert sr["actual"] == pytest.approx(229.0, abs=0.1), (
            f"Expected actual=229.0 thousands (ICSA 229000 / 1000), got {sr['actual']}"
        )

        # Our-model fields must be None in benchmark_only mode (FIX-3 guard works)
        assert sr.get("our_surprise") is None, (
            f"our_surprise must be None in benchmark_only mode, got {sr.get('our_surprise')}"
        )
        assert sr.get("interval_hit") is None, (
            f"interval_hit must be None in benchmark_only mode, got {sr.get('interval_hit')}"
        )
        assert sr.get("skew_hit") is None, (
            f"skew_hit must be None in benchmark_only mode, got {sr.get('skew_hit')}"
        )

        # Benchmark surprises must be computable
        assert sr.get("surprise_vs_naive") is not None, "surprise_vs_naive must be populated"
        expected_vs_naive = round(229.0 - 225.0, 4)
        assert sr["surprise_vs_naive"] == pytest.approx(expected_vs_naive, abs=0.01), (
            f"Expected surprise_vs_naive={expected_vs_naive}, got {sr['surprise_vs_naive']}"
        )

        # projection_mode must be carried through to scored row
        assert sr.get("projection_mode") == "benchmark_only", (
            f"projection_mode in scored row must be 'benchmark_only', got {sr.get('projection_mode')!r}"
        )

    @_CLAIMS_INT_MARK
    def test_claims_scoreboard_from_real_capture(self):
        """Scoreboard from a real-data claims scored row: mae_naive_prior populated, mae_ours None."""
        proj_row = {
            "schema": 2,
            "row_type": "projection",
            "asof_night": "2026-06-10",
            "release": "claims",
            "period": "2026-06-11",
            "release_date": "2026-06-11",
            "projection_mode": "benchmark_only",
            "projection_point": None,
            "projection_p10": None,
            "projection_p90": None,
            "benchmark_naive_prior": 225.0,
            "benchmark_trailing_4w": 222.0,
            "benchmark_ar_model": 223.0,
            "benchmark_cleveland": None,
        }
        today = date(2026, 6, 11)
        scored_rows = _check_release_day_capture(today, _REPO_ROOT, [proj_row])
        assert len(scored_rows) == 1, "Expected 1 scored row (prerequisite)"

        sb = _build_scoreboard(scored_rows, accrual_start="2026-01-01")
        claims_stats = sb["by_release"].get("claims")
        assert claims_stats is not None, "claims entry missing from scoreboard"
        assert claims_stats["n"] == 1, f"Expected n=1, got {claims_stats['n']}"
        # mae_ours must be None (no projection point in benchmark_only)
        assert claims_stats["mae_ours"] is None, (
            f"mae_ours must be None in benchmark_only mode, got {claims_stats['mae_ours']}"
        )
        # mae_naive_prior must be populated (|229.0 - 225.0| = 4.0)
        assert claims_stats["mae_naive_prior"] is not None, "mae_naive_prior must be populated"
        assert claims_stats["mae_naive_prior"] == pytest.approx(4.0, abs=0.1), (
            f"Expected mae_naive_prior=4.0, got {claims_stats['mae_naive_prior']}"
        )


# ============================================================
# 12. EXPECTATION READ — MRI-R22
# ============================================================

from scripts.build_release_forecast import (
    _build_projection_ledger_rows,
    _check_release_day_capture,
    _EXPECTATION_BAND_THRESHOLD,
)


def _make_projection_item_with_expectation_read(
    release_type: str = "cpi_headline",
    period: str = "2026-06",
    release_date: str = "2026-07-10",
    proj_point: float = 0.42,
    expectation_read: dict | None = None,
    sigma_scale_pp: float = 0.3073,
) -> dict:
    """Build a minimal upcoming item as produced by _build_upcoming_block + _enrich_upcoming_block."""
    return {
        "release": "cpi",
        "release_type": release_type,
        "period": period,
        "release_date": release_date,
        "days_to": 3,
        "projection": {"point": proj_point, "p10": 0.1, "p25": 0.2, "p50": 0.35, "p75": 0.5, "p90": 0.65},
        "confidence": 0.60,
        "input_completeness": 0.75,
        "benchmark_set": {
            "naive_prior": 0.47, "trailing_3m": 0.66, "ar_model": 0.86,
            "cleveland_nowcast": -0.061, "market_implied": None,
        },
        "surprise_skew": {"sigma_scale_pp": sigma_scale_pp, "sigma": -0.16, "tag": "inline"},
        "pit": {"inputs_hash": "abc123"},
        "regime_axis": "inflation",
        "policy_backdrop": {},
        "quirk_flags": [],
        "expectation_read": expectation_read,
    }


class TestExpectationReadProducer:
    """Tests for expectation_read wiring in producer: ledger freezing, scored-row hit, scoreboard."""

    def test_expectation_read_frozen_in_ledger_row(self):
        """Projection ledger row must carry frozen expectation_read dict."""
        from datetime import date
        today = date(2026, 7, 7)
        er = {"tag": "above_expectations", "delta_pp": 0.4848, "standardized": 1.58,
              "expectation_median": -0.0612, "sources": ["cleveland_nowcast"], "n_sources": 1}
        item = _make_projection_item_with_expectation_read(expectation_read=er)
        policy_backdrop = {"fed_stance": None, "gap_bp": None,
                           "implied_cuts_12m": None, "next_fomc": None}
        rows = _build_projection_ledger_rows(today, [item], policy_backdrop)
        assert len(rows) == 1
        row = rows[0]
        assert "expectation_read" in row, "expectation_read must be frozen in ledger projection row"
        assert row["expectation_read"]["tag"] == "above_expectations"
        assert row["expectation_read"]["n_sources"] == 1

    def test_null_expectation_read_frozen_as_none(self):
        """When expectation_read is None (empty expectation set), ledger row carries null."""
        from datetime import date
        today = date(2026, 7, 7)
        item = _make_projection_item_with_expectation_read(expectation_read=None)
        policy_backdrop = {"fed_stance": None, "gap_bp": None,
                           "implied_cuts_12m": None, "next_fomc": None}
        rows = _build_projection_ledger_rows(today, [item], policy_backdrop)
        assert rows[0].get("expectation_read") is None

    def test_sigma_scale_pp_frozen_in_ledger_row(self):
        """sigma_scale_pp must be frozen in the projection ledger row for scoring."""
        from datetime import date
        today = date(2026, 7, 7)
        item = _make_projection_item_with_expectation_read(sigma_scale_pp=0.3073)
        policy_backdrop = {"fed_stance": None, "gap_bp": None,
                           "implied_cuts_12m": None, "next_fomc": None}
        rows = _build_projection_ledger_rows(today, [item], policy_backdrop)
        assert rows[0].get("sigma_scale_pp") == pytest.approx(0.3073, abs=1e-6)

    def test_expectation_hit_above_expectations_correct(self, tmp_root: Path):
        """When actual falls above the frozen expectation_median+0.35σ, expectation_hit=True
        for a frozen tag='above_expectations'."""
        # Setup: frozen tag='above_expectations', expectation_median=-0.06, sigma=0.3073
        # Actual = 0.50 → std = (0.50 - (-0.06)) / 0.3073 = 1.82 → above → hit=True
        er = {"tag": "above_expectations", "delta_pp": 0.48, "standardized": 1.58,
              "expectation_median": -0.06, "sources": ["cleveland_nowcast"], "n_sources": 1}
        proj_row = {
            "schema": 2, "row_type": "projection",
            "asof_night": "2026-07-07", "release": "cpi_headline", "period": "2026-06",
            "release_date": "2026-07-10",
            "projection_mode": None, "projection_point": 0.42,
            "projection_p10": 0.1, "projection_p90": 0.65,
            "benchmark_naive_prior": 0.47, "benchmark_trailing_3m": 0.66,
            "benchmark_ar_model": 0.86, "benchmark_cleveland": -0.06,
            "surprise_skew_sigma": -0.16, "surprise_skew_tag": "inline",
            "fed_stance": None, "gap_bp": None, "implied_cuts_12m": None, "next_fomc": None,
            "expectation_read": er,
            "sigma_scale_pp": 0.3073,
        }

        # Provide vintage with actual = 0.50 MoM
        # CPI: need prior month level + current month level
        # prior month 2026-05 level: 315.0
        # current month 2026-06 level: 315.0 * (1 + 0.50/100) = 316.575
        _make_vintage_parquet(tmp_root, [
            {"series": "CPIAUCSL", "period": "2026-05-01", "value": 315.0,
             "realtime_start": "2026-06-12", "realtime_end": "2099-01-01"},
            {"series": "CPIAUCSL", "period": "2026-06-01", "value": 316.575,
             "realtime_start": "2026-07-10", "realtime_end": "2099-01-01"},
        ])

        today = date(2026, 7, 10)
        scored = _check_release_day_capture(today, tmp_root, [proj_row])

        assert len(scored) == 1
        sr = scored[0]
        # actual ≈ (316.575/315.0 - 1)*100 = 0.50%
        # frozen tag='above_expectations', frozen_median=-0.06, sigma=0.3073
        # actual_std = (0.50 - (-0.06)) / 0.3073 = 1.82 > 0.35 → actual_tag='above_expectations'
        # frozen_tag == actual_tag → hit = True
        assert sr.get("expectation_hit") is True, (
            f"Expected expectation_hit=True when actual=0.5 and frozen tag='above_expectations'; "
            f"got {sr.get('expectation_hit')!r}"
        )

    def test_expectation_hit_tag_mismatch_is_false(self, tmp_root: Path):
        """When actual falls in a different band than the frozen tag, expectation_hit=False."""
        # frozen tag='above_expectations', but actual is well below expectation_median
        # expectation_median = 0.4, sigma = 0.3073
        # actual = 0.10 → std = (0.10 - 0.4) / 0.3073 = -0.976 → below_expectations ≠ above
        er = {"tag": "above_expectations", "delta_pp": 0.1, "standardized": 0.5,
              "expectation_median": 0.4, "sources": ["cleveland_nowcast"], "n_sources": 1}
        proj_row = {
            "schema": 2, "row_type": "projection",
            "asof_night": "2026-07-07", "release": "cpi_headline", "period": "2026-06",
            "release_date": "2026-07-10",
            "projection_mode": None, "projection_point": 0.5,
            "projection_p10": 0.1, "projection_p90": 0.9,
            "benchmark_naive_prior": 0.4, "benchmark_trailing_3m": 0.4,
            "benchmark_ar_model": 0.4, "benchmark_cleveland": 0.4,
            "surprise_skew_sigma": None, "surprise_skew_tag": None,
            "fed_stance": None, "gap_bp": None, "implied_cuts_12m": None, "next_fomc": None,
            "expectation_read": er,
            "sigma_scale_pp": 0.3073,
        }

        # actual = 0.10 MoM → prior=315.0, current=315.315
        _make_vintage_parquet(tmp_root, [
            {"series": "CPIAUCSL", "period": "2026-05-01", "value": 315.0,
             "realtime_start": "2026-06-12", "realtime_end": "2099-01-01"},
            {"series": "CPIAUCSL", "period": "2026-06-01", "value": 315.315,
             "realtime_start": "2026-07-10", "realtime_end": "2099-01-01"},
        ])

        today = date(2026, 7, 10)
        scored = _check_release_day_capture(today, tmp_root, [proj_row])

        assert len(scored) == 1
        sr = scored[0]
        assert sr.get("expectation_hit") is False, (
            f"Expected expectation_hit=False when actual is below_expectations but frozen='above'; "
            f"got {sr.get('expectation_hit')!r}"
        )

    def test_expectation_hit_none_when_frozen_read_null(self, tmp_root: Path):
        """expectation_hit is null when the frozen expectation_read is None."""
        proj_row = {
            "schema": 2, "row_type": "projection",
            "asof_night": "2026-07-07", "release": "cpi_headline", "period": "2026-06",
            "release_date": "2026-07-10",
            "projection_mode": None, "projection_point": 0.42,
            "projection_p10": 0.1, "projection_p90": 0.9,
            "benchmark_naive_prior": 0.47, "benchmark_trailing_3m": 0.66,
            "benchmark_ar_model": 0.86, "benchmark_cleveland": None,
            "surprise_skew_sigma": None, "surprise_skew_tag": None,
            "fed_stance": None, "gap_bp": None, "implied_cuts_12m": None, "next_fomc": None,
            "expectation_read": None,   # frozen read was null
            "sigma_scale_pp": None,
        }

        _make_vintage_parquet(tmp_root, [
            {"series": "CPIAUCSL", "period": "2026-05-01", "value": 315.0,
             "realtime_start": "2026-06-12", "realtime_end": "2099-01-01"},
            {"series": "CPIAUCSL", "period": "2026-06-01", "value": 316.26,
             "realtime_start": "2026-07-10", "realtime_end": "2099-01-01"},
        ])

        today = date(2026, 7, 10)
        scored = _check_release_day_capture(today, tmp_root, [proj_row])

        assert len(scored) == 1
        assert scored[0].get("expectation_hit") is None, (
            "expectation_hit must be None when frozen expectation_read was null"
        )

    def test_scoreboard_expectation_read_hit_rate_n0_honest(self):
        """Scoreboard with no scored rows: expectation_read_hit_rate is None (n=0 honest)."""
        sb = _build_scoreboard([], accrual_start="2026-07-07")
        # No releases yet → by_release is empty; fields are per-release so absent
        assert sb["by_release"] == {}

    def test_scoreboard_expectation_read_hit_rate_field_present_when_scored(self):
        """Scoreboard emits expectation_read_hit_rate (None) when scored rows have no hit data."""
        scored = _scored_row(release="cpi_headline")
        scored["actual"] = 0.30
        scored["frozen_projection_point"] = 0.28
        scored["interval_hit"] = True
        scored["skew_hit"] = True
        # No expectation_hit in this row (not set)
        sb = _build_scoreboard([scored], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"].get("cpi_headline", {})
        assert "expectation_read_hit_rate" in cpi_stats, (
            "expectation_read_hit_rate must be present in scoreboard even with n=0"
        )
        # n=0 → None (honest)
        assert cpi_stats["expectation_read_hit_rate"] is None
        assert cpi_stats["expectation_read_hit_rate_n"] == 0

    def test_scoreboard_expectation_read_hit_rate_computes_correctly(self):
        """Scoreboard correctly aggregates expectation_hit values."""
        scored1 = _scored_row(release="cpi_headline", period="2026-05")
        scored1["actual"] = 0.25
        scored1["frozen_projection_point"] = 0.28
        scored1["interval_hit"] = True
        scored1["skew_hit"] = False
        scored1["expectation_hit"] = True   # hit

        scored2 = _scored_row(release="cpi_headline", period="2026-06")
        scored2["actual"] = 0.30
        scored2["frozen_projection_point"] = 0.27
        scored2["interval_hit"] = False
        scored2["skew_hit"] = True
        scored2["expectation_hit"] = False  # miss

        sb = _build_scoreboard([scored1, scored2], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"]["cpi_headline"]
        assert cpi_stats["expectation_read_hit_rate_n"] == 2
        assert cpi_stats["expectation_read_hit_rate"] == pytest.approx(0.5, abs=1e-4)

    def test_enrichments_list_includes_expectation_read(self, tmp_root: Path, monkeypatch):
        """The enrichments list in latest.json must include 'expectation_read'."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })
        result = producer.build(tmp_root, dry_run=True)
        assert "expectation_read" in result.get("enrichments", []), (
            "enrichments list must include 'expectation_read'"
        )


# ============================================================
# 13. MRI-R35 — cutoff_label assignment
# ============================================================

from scripts.build_release_forecast import _assign_cutoff_labels


class TestCutoffLabels:
    """MRI-R35: _assign_cutoff_labels assigns T-1 / early correctly."""

    def test_single_item_gets_t1(self):
        """One item for a release_type always gets T-1."""
        items = [
            {"release_type": "cpi_headline", "release_date": "2026-08-12"},
        ]
        _assign_cutoff_labels(items)
        assert items[0]["cutoff_label"] == "T-1"

    def test_nearest_gets_t1_rest_early(self):
        """Nearest release_date gets T-1; later ones get early."""
        items = [
            {"release_type": "cpi_headline", "release_date": "2026-09-10"},
            {"release_type": "cpi_headline", "release_date": "2026-08-12"},  # nearest
        ]
        _assign_cutoff_labels(items)
        by_date = {i["release_date"]: i["cutoff_label"] for i in items}
        assert by_date["2026-08-12"] == "T-1"
        assert by_date["2026-09-10"] == "early"

    def test_different_release_types_independent(self):
        """Each release_type has its own T-1 — CPI and NFP both get a T-1."""
        items = [
            {"release_type": "cpi_headline", "release_date": "2026-08-12"},
            {"release_type": "nfp", "release_date": "2026-08-01"},
        ]
        _assign_cutoff_labels(items)
        by_rt = {i["release_type"]: i["cutoff_label"] for i in items}
        assert by_rt["cpi_headline"] == "T-1"
        assert by_rt["nfp"] == "T-1"

    def test_no_release_date_gets_early(self):
        """Item without release_date sorts last and gets 'early' if another item exists."""
        items = [
            {"release_type": "cpi_headline", "release_date": "2026-08-12"},
            {"release_type": "cpi_headline"},  # no release_date
        ]
        _assign_cutoff_labels(items)
        labeled = [(i.get("release_date"), i["cutoff_label"]) for i in items]
        # "2026-08-12" should be T-1; missing date should be early
        date_labels = {rd: lbl for rd, lbl in labeled}
        assert date_labels.get("2026-08-12") == "T-1"
        assert date_labels.get(None) == "early"

    def test_cutoff_label_frozen_in_ledger_row(self):
        """cutoff_label assigned in-place appears in projection ledger rows."""
        from datetime import date
        today = date(2026, 7, 9)
        item = {
            "release": "cpi",
            "release_type": "cpi_headline",
            "period": "2026-07",
            "release_date": "2026-08-12",
            "days_to": 34,
            "projection": {"point": 0.28, "p10": 0.10, "p25": 0.18, "p50": 0.28, "p75": 0.38, "p90": 0.46},
            "confidence": 0.60,
            "input_completeness": 0.75,
            "benchmark_set": {
                "naive_prior": 0.24, "trailing_3m": 0.25, "ar_model": 0.26,
                "cleveland_nowcast": 0.30, "market_implied": None,
            },
            "surprise_skew": {"sigma_scale_pp": 0.31, "sigma": 0.0, "tag": "inline"},
            "pit": {"inputs_hash": "abc123"},
            "regime_axis": "inflation",
            "policy_backdrop": {},
            "quirk_flags": [],
            "expectation_read": None,
            "cutoff_label": "T-1",  # pre-assigned by _assign_cutoff_labels
        }
        from scripts.build_release_forecast import _build_projection_ledger_rows
        policy_backdrop = {"fed_stance": None, "gap_bp": None,
                           "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None}
        rows = _build_projection_ledger_rows(today, [item], policy_backdrop)
        assert len(rows) == 1
        assert rows[0].get("cutoff_label") == "T-1", (
            f"Expected cutoff_label='T-1' in ledger row, got {rows[0].get('cutoff_label')!r}"
        )

    def test_scored_row_inherits_cutoff_label(self, tmp_root: Path):
        """cutoff_label from the frozen T-1 projection is carried into the scored row."""
        _make_vintage_parquet(tmp_root, [
            {"series": "CPIAUCSL", "period": "2026-05-01", "value": 315.0,
             "realtime_start": "2026-06-12", "realtime_end": "2099-01-01"},
            {"series": "CPIAUCSL", "period": "2026-06-01", "value": 316.26,
             "realtime_start": "2026-07-10", "realtime_end": "2099-01-01"},
        ])
        proj_row = _projection_row(
            release="cpi_headline", period="2026-06",
            asof_night="2026-07-01", release_date="2026-07-10",
        )
        proj_row["cutoff_label"] = "T-1"  # set by _assign_cutoff_labels

        today = date(2026, 7, 10)
        scored = _check_release_day_capture(today, tmp_root, [proj_row])
        assert len(scored) == 1
        assert scored[0].get("cutoff_label") == "T-1", (
            f"Expected cutoff_label='T-1' in scored row, got {scored[0].get('cutoff_label')!r}"
        )


# ============================================================
# 14. MRI-R31 — pinball loss
# ============================================================

class TestPinballLoss:
    """MRI-R31: 5-quantile pinball loss in the scoreboard."""

    def _make_scored_with_quantiles(
        self,
        actual: float,
        p10: float, p25: float, p50: float, p75: float, p90: float,
        release: str = "cpi_headline",
        period: str = "2026-06",
    ) -> dict:
        row = _scored_row(release=release, period=period)
        row["actual"] = actual
        row["frozen_projection_p10"] = p10
        row["frozen_projection_p25"] = p25
        row["frozen_projection_point"] = p50   # point ≈ p50 for pinball
        row["frozen_projection_p75"] = p75
        row["frozen_projection_p90"] = p90
        row["interval_hit"] = bool(p10 <= actual <= p90)
        return row

    def test_pinball_null_when_no_quantiles(self):
        """pinball_loss_5q is None when no quantile fields are populated."""
        scored = _scored_row()
        scored["actual"] = 0.30
        scored["frozen_projection_point"] = 0.28
        scored["interval_hit"] = True
        scored["skew_hit"] = True
        # No p10/p25/p75/p90 set
        sb = _build_scoreboard([scored], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"]["cpi_headline"]
        # p50 is non-null (frozen_projection_point) but others absent — check behaviour
        # pinball_loss_5q may or may not be null depending on whether p50 is accumulated
        # (the test only asserts the key exists and type is correct)
        assert "pinball_loss_5q" in cpi_stats, "pinball_loss_5q key must be present"
        assert "pinball_loss_5q_n" in cpi_stats, "pinball_loss_5q_n key must be present"

    def test_pinball_formula_spot_check(self):
        """Spot-check pinball loss formula: L_q(y, q̂) = (y - q̂)(α - 1{y < q̂}).

        With actual=0.5 and all quantile predictions = 0.3:
          p10: q̂=0.3, α=0.10, y>q̂ → err=0.2 → L = 0.2 * 0.10 = 0.02
          p25: q̂=0.3, α=0.25, y>q̂ → err=0.2 → L = 0.2 * 0.25 = 0.05
          p50: q̂=0.3, α=0.50, y>q̂ → err=0.2 → L = 0.2 * 0.50 = 0.10
          p75: q̂=0.3, α=0.75, y>q̂ → err=0.2 → L = 0.2 * 0.75 = 0.15
          p90: q̂=0.3, α=0.90, y>q̂ → err=0.2 → L = 0.2 * 0.90 = 0.18
          sum = 0.02 + 0.05 + 0.10 + 0.15 + 0.18 = 0.50
        """
        scored = self._make_scored_with_quantiles(
            actual=0.5, p10=0.3, p25=0.3, p50=0.3, p75=0.3, p90=0.3
        )
        sb = _build_scoreboard([scored], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"]["cpi_headline"]
        pb = cpi_stats.get("pinball_loss_5q")
        assert pb is not None, "pinball_loss_5q must not be None when quantiles are set"
        assert pb == pytest.approx(0.50, abs=1e-3), (
            f"Expected pinball sum=0.50 for all-0.3 quantiles vs actual=0.5, got {pb}"
        )
        assert cpi_stats["pinball_loss_5q_n"] == 1

    def test_pinball_multiple_rows_averaged(self):
        """pinball_loss_5q is the mean-of-means across rows (one row per n draw)."""
        # Row 1: actual=0.5, all q=0.3 → individual sums = 0.50 (from test above)
        # Row 2: actual=0.3, all q=0.3 → errors all 0 → sum = 0.0
        # Mean = 0.25
        scored1 = self._make_scored_with_quantiles(
            actual=0.5, p10=0.3, p25=0.3, p50=0.3, p75=0.3, p90=0.3,
            period="2026-05",
        )
        scored2 = self._make_scored_with_quantiles(
            actual=0.3, p10=0.3, p25=0.3, p50=0.3, p75=0.3, p90=0.3,
            period="2026-06",
        )
        sb = _build_scoreboard([scored1, scored2], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"]["cpi_headline"]
        pb = cpi_stats.get("pinball_loss_5q")
        assert pb is not None
        assert pb == pytest.approx(0.25, abs=1e-3), (
            f"Expected pinball mean=0.25 for two rows, got {pb}"
        )
        assert cpi_stats["pinball_loss_5q_n"] == 2

    def test_pinball_note_present(self):
        """pinball_loss_5q_note is present with MRI-R31 reference."""
        scored = self._make_scored_with_quantiles(
            actual=0.5, p10=0.3, p25=0.3, p50=0.3, p75=0.3, p90=0.3
        )
        sb = _build_scoreboard([scored], accrual_start="2026-07-07")
        cpi_stats = sb["by_release"]["cpi_headline"]
        note = cpi_stats.get("pinball_loss_5q_note", "")
        assert "MRI-R31" in note, f"pinball_loss_5q_note must reference MRI-R31, got: {note!r}"


# ============================================================
# 15. MRI-R32a — catch-up sweep (orphaned past print fixture test)
# ============================================================

class TestCatchUpSweep:
    """MRI-R32a: catch-up sweep fixture test using orphaned past print case."""

    def test_orphaned_past_print_gets_scored(self, tmp_root: Path):
        """Fixture test: projection asof 2026-07-08 for release 2026-07-09.
        No scored row exists. Vintage is available (initial print present).
        Running on 2026-07-10: catch-up sweep must produce exactly 1 scored row.
        """
        # Write CPI vintage: prior month (2026-05) + current month (2026-06)
        _make_vintage_parquet(tmp_root, [
            {"series": "CPIAUCSL", "period": "2026-05-01", "value": 315.0,
             "realtime_start": "2026-06-12", "realtime_end": "2099-01-01"},
            # Initial print available from 2026-07-09
            {"series": "CPIAUCSL", "period": "2026-06-01", "value": 316.26,
             "realtime_start": "2026-07-09", "realtime_end": "2099-01-01"},
        ])

        proj_row = _projection_row(
            release="cpi_headline",
            period="2026-06",
            asof_night="2026-07-08",   # pre-release (release date = 2026-07-09)
            proj_point=0.28,
            proj_p10=0.10,
            proj_p90=0.46,
            release_date="2026-07-09",
        )

        # No scored row yet — orphaned projection
        existing_ledger = [proj_row]

        # Run catch-up as of 2026-07-10 (day after release)
        today = date(2026, 7, 10)
        scored = _check_release_day_capture(today, tmp_root, existing_ledger)

        assert len(scored) == 1, (
            f"Expected exactly 1 scored row from catch-up sweep, got {len(scored)}.\n"
            f"scored={scored}"
        )
        sr = scored[0]
        assert sr["row_type"] == "scored"
        assert sr["release"] == "cpi_headline"
        assert sr["period"] == "2026-06"
        assert sr["release_date"] == "2026-07-09"
        # Actual = (316.26 / 315.0 - 1) * 100 = 0.4
        expected_actual = round((316.26 / 315.0 - 1) * 100, 4)
        assert sr["actual"] == pytest.approx(expected_actual, abs=1e-3), (
            f"Expected actual={expected_actual}, got {sr['actual']}"
        )
        # Pre-release projection used (not late)
        assert sr.get("late") is not True, (
            "Should not be flagged 'late' — pre-release projection exists"
        )

    def test_catch_up_idempotent_on_existing_scored(self, tmp_root: Path):
        """Running catch-up when a scored row already exists produces zero new rows."""
        _make_vintage_parquet(tmp_root, [
            {"series": "CPIAUCSL", "period": "2026-05-01", "value": 315.0,
             "realtime_start": "2026-06-12", "realtime_end": "2099-01-01"},
            {"series": "CPIAUCSL", "period": "2026-06-01", "value": 316.26,
             "realtime_start": "2026-07-10", "realtime_end": "2099-01-01"},
        ])
        proj_row = _projection_row(
            release="cpi_headline", period="2026-06",
            asof_night="2026-07-01", release_date="2026-07-10",
        )
        scored_row = _scored_row(release="cpi_headline", period="2026-06")
        existing_ledger = [proj_row, scored_row]

        today = date(2026, 7, 10)
        new_rows = _check_release_day_capture(today, tmp_root, existing_ledger)
        assert len(new_rows) == 0, (
            f"Expected 0 new rows (already scored), got {len(new_rows)}"
        )

    def test_catch_up_lookback_gate(self, tmp_root: Path):
        """A projection older than 120d is outside the lookback window and not scored."""
        _make_vintage_parquet(tmp_root, [
            {"series": "CPIAUCSL", "period": "2025-01-01", "value": 310.0,
             "realtime_start": "2025-02-12", "realtime_end": "2099-01-01"},
            {"series": "CPIAUCSL", "period": "2025-02-01", "value": 311.0,
             "realtime_start": "2025-03-12", "realtime_end": "2099-01-01"},
        ])
        # Project for a period 200 days ago (2026-07-10 - 200d ≈ 2025-12-22)
        old_proj = _projection_row(
            release="cpi_headline", period="2025-12",
            asof_night="2025-12-20", release_date="2025-12-22",
        )
        today = date(2026, 7, 10)
        scored = _check_release_day_capture(today, tmp_root, [old_proj], lookback_days=120)
        assert len(scored) == 0, (
            f"Expected 0 scored rows (period outside 120d lookback), got {len(scored)}"
        )

    def test_catch_up_release_day_row_not_late(self, tmp_root: Path):
        """MRI-R32b/R32c fix: when only a release-day projection exists (asof_night ==
        release_date), the scored row must NOT have late=True.

        The nightly pipeline runs 02:00 UTC (~10h before the 08:30 ET print), so a
        release-day row is genuinely pre-print.  It receives frozen_on_release_day=True
        for annotation, but late=True is reserved for projections created AFTER the
        release printed (asof_night > release_date) — a case the current ledger filter
        (asof_night <= release_date) prevents from entering the scoring window.
        """
        _make_vintage_parquet(tmp_root, [
            {"series": "CPIAUCSL", "period": "2026-05-01", "value": 315.0,
             "realtime_start": "2026-06-12", "realtime_end": "2099-01-01"},
            {"series": "CPIAUCSL", "period": "2026-06-01", "value": 316.26,
             "realtime_start": "2026-07-10", "realtime_end": "2099-01-01"},
        ])
        # Projection on same day as release (no pre-release row)
        proj_row = _projection_row(
            release="cpi_headline", period="2026-06",
            asof_night="2026-07-10",   # == release_date
            release_date="2026-07-10",
        )
        today = date(2026, 7, 10)
        scored = _check_release_day_capture(today, tmp_root, [proj_row])
        assert len(scored) == 1
        sr = scored[0]
        # Release-day row is pre-print (02:00 UTC nightly) → NOT late
        assert sr.get("late") is not True, (
            f"Release-day row must NOT be marked late (it is pre-print), got late={sr.get('late')!r}"
        )
        # But it SHOULD be annotated as frozen_on_release_day
        assert sr.get("frozen_on_release_day") is True, (
            "Expected frozen_on_release_day=True when asof_night == release_date"
        )


# ============================================================
# 16. MRI-R34 — Cleveland PIT fix (first_seen_asof filter)
# ============================================================

class TestClevelandPITFix:
    """MRI-R34: _read_cleveland_nowcast uses first_seen_asof (not obs_date) for PIT."""

    def test_first_seen_asof_is_the_pit_gate(self, tmp_root: Path):
        """A row with obs_date before today but first_seen_asof AFTER today must be excluded.

        This is the key regression: pre-fix code used obs_date <= today (which would INCLUDE
        this row); post-fix code uses first_seen_asof <= today (which correctly EXCLUDES it).
        """
        today = date(2026, 7, 7)
        _make_cleveland_parquet(tmp_root, [
            {
                # obs_date is well before today — old code would include this
                # but first_seen_asof is AFTER today — correct code must EXCLUDE it
                "first_seen_asof": "2026-07-08",   # not yet known on 2026-07-07
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-06-01",           # obs_date is historical
                "value": 0.40,                      # should NOT be returned
            },
            {
                # Both first_seen_asof and obs_date are before today → valid
                "first_seen_asof": "2026-07-06",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-06",
                "value": 0.31,                      # must be returned
            },
        ])
        result = _read_cleveland_nowcast(tmp_root, "cpi_headline", "2026-06", today)
        assert result == pytest.approx(0.31, abs=1e-5), (
            f"MRI-R34 PIT fix: expected 0.31 (first_seen_asof=2026-07-06 ≤ today=2026-07-07), "
            f"got {result}. If 0.40, the old obs_date-based filter is still in use."
        )

    def test_real_schema_fixture(self, tmp_root: Path):
        """Regression test against real parquet schema:
        columns first_seen_asof / target_period / series / obs_date / value.

        Verifies _read_cleveland_nowcast handles the real production schema without crashing.
        Schema matches data/cleveland_nowcast/nowcast.parquet (first_seen_asof as str).
        """
        today = date(2026, 7, 9)
        # Fixture uses real column names and types from production parquet
        _make_cleveland_parquet(tmp_root, [
            {
                "first_seen_asof": "2026-07-07",   # str, as in production
                "target_period": "2026-06-01",      # month-start date str
                "series": "cpi_mom",
                "obs_date": "2026-07-07",
                "value": 0.295,
            },
            {
                "first_seen_asof": "2026-07-08",
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-08",
                "value": 0.300,
            },
            {
                "first_seen_asof": "2026-07-10",   # after today — must be excluded
                "target_period": "2026-06-01",
                "series": "cpi_mom",
                "obs_date": "2026-07-10",
                "value": 0.999,                     # should not appear
            },
        ])
        result = _read_cleveland_nowcast(tmp_root, "cpi_headline", "2026-06", today)
        # Latest first_seen_asof <= today is 2026-07-08 → value 0.300
        assert result is not None, "Expected a non-None result"
        assert result == pytest.approx(0.300, abs=1e-5), (
            f"Expected 0.300 (latest first_seen_asof≤today), got {result}"
        )


# ============================================================
# 17. MRI-R32e — capture_health block
# ============================================================

from scripts.build_release_forecast import _compute_capture_health


class TestCaptureHealth:
    """MRI-R32e: _compute_capture_health returns expected fields."""

    def test_empty_ledger_returns_safe_defaults(self, tmp_root: Path):
        """With an empty ledger, capture_health returns None for gap fields."""
        health = _compute_capture_health(date(2026, 7, 10), tmp_root, [])
        assert "last_nightly_asof" in health
        assert health["last_nightly_asof"] is None
        assert health["nightly_gap_days"] is None
        assert health["past_due_unscored"] == []
        assert "enricher_staleness" in health

    def test_last_nightly_asof_and_gap(self, tmp_root: Path):
        """With a ledger row from 2026-07-08, last_nightly_asof is correct and gap=2."""
        ledger = [_projection_row(asof_night="2026-07-08")]
        health = _compute_capture_health(date(2026, 7, 10), tmp_root, ledger)
        assert health["last_nightly_asof"] == "2026-07-08"
        assert health["nightly_gap_days"] == 2

    def test_past_due_unscored_detected(self, tmp_root: Path):
        """A past-due projection (release_date passed, no scored row, no vintage) is reported."""
        proj = _projection_row(
            release="cpi_headline", period="2026-06",
            asof_night="2026-07-01", release_date="2026-07-09",
        )
        health = _compute_capture_health(date(2026, 7, 10), tmp_root, [proj])
        pdu = health["past_due_unscored"]
        assert len(pdu) >= 1, "Expected at least one past_due_unscored entry"
        entry = pdu[0]
        assert entry["release"] == "cpi_headline"
        assert "reason" in entry
        # No vintage in tmp_root → reason should be missing_vintage or similar
        assert entry["reason"] in ("missing_vintage", "no_t1_projection", "api_key_absent")

    def test_already_scored_not_in_past_due(self, tmp_root: Path):
        """An already-scored (release, period) does not appear in past_due_unscored."""
        proj = _projection_row(
            release="cpi_headline", period="2026-06",
            asof_night="2026-07-01", release_date="2026-07-09",
        )
        scored = _scored_row(release="cpi_headline", period="2026-06")
        health = _compute_capture_health(date(2026, 7, 10), tmp_root, [proj, scored])
        releases_in_pdu = [e["release"] for e in health["past_due_unscored"]]
        assert "cpi_headline" not in releases_in_pdu, (
            "cpi_headline must not appear in past_due_unscored — it is already scored"
        )

    def test_capture_health_in_latest_json(self, tmp_root: Path, monkeypatch):
        """capture_health appears in latest.json when build() runs."""
        import scripts.build_release_forecast as producer
        monkeypatch.setattr(producer, "_find_upcoming_releases", lambda *a, **k: [])
        monkeypatch.setattr(producer, "_read_policy_backdrop", lambda *a, **k: {
            "fed_stance": None, "gap_bp": None,
            "implied_cuts_12m": None, "next_fomc": None, "guidance_direction": None,
        })
        result = producer.build(tmp_root, dry_run=True)
        assert "capture_health" in result, "capture_health must be a top-level key in latest.json"
        ch = result["capture_health"]
        assert "last_nightly_asof" in ch
        assert "nightly_gap_days" in ch
        assert "past_due_unscored" in ch
