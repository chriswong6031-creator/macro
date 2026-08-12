"""Governance contract for the Wave 2B coherent-target CPI ridge shadow.

This suite intentionally tests the frozen registry, preregistration, producer
boundary, provenance graph and CI ownership together.  A model that computes a
number but escapes any one of those rails is not a valid Release Radar candidate.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "release_forecast_model_registry.yml"
PREREG_PATH = ROOT / "research" / "release_forecast" / "PREREG_COHERENT_RIDGE_V1.md"
COMBINED_PREREG_PATH = ROOT / "research" / "release_forecast" / "PREREG_COMBINED_POINT_V1.md"
BUILDER_PATH = ROOT / "scripts" / "build_release_forecast.py"
DAG_PATH = ROOT / "config" / "dag.yml"
SYNAPSE_PATH = ROOT / "config" / "synapse.yml"
CI_MANIFEST_PATH = ROOT / ".github" / "ci" / "legacy-jobs.yml"
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"

HEADLINE_FEATURES = [
    "cpi_hl_mom_lag1",
    "cpi_hl_mom_lag2",
    "cpi_hl_mom_lag3",
    "sticky_mom_lag1",
    "median_mom_lag1",
    "flex_mom_lag1",
    "gasoline_mom",
    "ppi_mom_lag1",
]
CORE_FEATURES = [
    "cpi_core_mom_lag1",
    "cpi_core_mom_lag2",
    "cpi_core_mom_lag3",
    "sticky_mom_lag1",
    "median_mom_lag1",
    "flex_mom_lag1",
    "ppi_mom_lag1",
]


def _registry() -> dict:
    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert payload["schema"] == "release_forecast_model_registry.v1"
    return payload["models"]["coherent_ridge_v1"]


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    segment = ast.get_source_segment(source, node)
    assert segment is not None
    return segment


def test_registry_freezes_identity_target_and_truth_receipt() -> None:
    model = _registry()
    assert model["model_id"] == "coherent_ridge_v1"
    assert model["model_epoch"] == "coherent_ridge_v1"
    assert model["callable"] == (
        "engine.release_cpi_coherent_shadow.project_cpi_coherent_shadow"
    )
    assert model["output_schema"] == "release_cpi_coherent_shadow.v1"
    assert model["status"] == "shadow_candidate"
    assert model["releases"] == ["cpi_headline", "cpi_core"]

    target = model["target"]
    assert target["epoch"] == "alfred_same_release_vintage_proxy_v1"
    assert target["value_field"] == "published_proxy_1dp"
    assert target["official_first_print_epoch"] == "withheld"
    assert target["require_completed_parity"] is True
    assert target["require_exact_release_calendar_lags"] is True
    assert target["cross_vintage_target_reconstruction_allowed"] is False
    assert target["truth_receipt_bindings"] == {
        "history": ["path", "sha256", "bytes", "history_hash"],
        "parity": ["path", "sha256", "bytes"],
        "completion": ["path", "sha256", "bytes", "evidence_available_at"],
    }


def test_registry_freezes_feature_order_and_pit_rules() -> None:
    model = _registry()
    assert model["feature_order"] == {
        "cpi_headline": HEADLINE_FEATURES,
        "cpi_core": CORE_FEATURES,
    }
    provenance = model["feature_provenance"]
    assert provenance["own_target_lags"] == {
        "source": "coherent_target_history",
        "value_field": "published_proxy_1dp",
        "period_rule": "exact_calendar_prior_months",
        "release_date_lte_decision_asof": True,
    }
    assert provenance["common_cutoff_rules"] == {
        "realtime_start_lte_decision_asof": True,
        "alfred_source_period_strictly_before_target": True,
    }
    assert provenance["gasoline_mom"]["source"] == "unrevised_timestamp_filtered"
    assert provenance["gasoline_mom"]["observation_timestamp_lt_decision_asof"] is True
    assert provenance["excluded_features"] == [
        "shelter_nowcast",
        "zori",
        "revision_optimistic_parquet_legs",
    ]


def test_registry_freezes_fit_rounding_and_interval_gates() -> None:
    model = _registry()
    training = model["training"]
    assert training["method"] == "expanding_ridge"
    assert training["chronological_refit_each_step"] is True
    assert training["complete_case"] is True
    assert training["column_dropping_allowed"] is False
    assert training["imputation_allowed"] is False
    assert training["baseline_fallback_allowed"] is False
    assert training["minimum_complete_prior_rows"] == 60
    assert training["ridge_lambda"] == 1.0
    assert training["standardization"] == {
        "scope": "train_only",
        "sample_std_ddof": 1,
        "zero_variance_scale": 1.0,
    }
    assert training["intercept"] == {"included": True, "penalized": False}
    assert training["decision_cutoff"] == "release_date_minus_1_calendar_day"
    assert training["missing_contract_behavior"] == "fail_closed_no_output"

    intervals = model["intervals"]
    assert intervals["method"] == "empirical_prior_oos_residual_quantiles"
    assert intervals["residual"] == "actual_raw_target_minus_raw_ridge_point"
    assert intervals["quantiles"] == [0.10, 0.25, 0.50, 0.75, 0.90]
    assert intervals["interpolation"] == "numpy_linear"
    assert intervals["strictly_prior_oos_residuals_only"] is True
    assert intervals["minimum_prior_oos_residuals"] == 24
    assert intervals["fallback_allowed"] is False
    assert intervals["published_rounding"] == {
        "p10_p25": "decimal_round_floor_1dp",
        "p50": "decimal_round_half_up_1dp",
        "p75_p90": "decimal_round_ceiling_1dp",
    }
    assert model["output"]["published_rounding"] == "decimal_round_half_up_1dp"
    assert model["output"]["point_raw_preserved"] is True


def test_registry_denies_authority_combination_and_promotion() -> None:
    model = _registry()
    output = model["output"]
    assert output["ledger_row_type"] == "shadow_projection"
    assert output["forward_evaluation_scoring"] is True
    assert output["historical_backfill_to_forward_ledger_allowed"] is False
    assert output["display_only"] is True
    assert output["authority"] is False
    assert output["promotion_authorized"] is False
    assert set(model["authority_fence"].values()) == {False}
    assert model["ensemble_exclusions"] == {
        "combined_v1_input_allowed": False,
        "combined_v1_weight": 0.0,
        "internal_ensemble_v1_input_allowed": False,
        "internal_ensemble_v1_weight": 0.0,
        "automatic_promotion_allowed": False,
        "promotion_review_allowed": False,
    }


def test_prereg_is_frozen_pre_forward_and_contains_no_observed_metric() -> None:
    model = _registry()
    prereg = model["preregistration"]
    assert prereg == {
        "path": "research/release_forecast/PREREG_COHERENT_RIDGE_V1.md",
        "attempt": 1,
        "maximum_attempts_for_epoch": 1,
        "frozen_before_forward_accrual": True,
        "observed_performance_allowed_in_spec": False,
        "amendment_requires_new_model_epoch": True,
    }
    text = PREREG_PATH.read_text(encoding="utf-8")
    assert "before the first `coherent_ridge_v1` forward-ledger row" in text
    assert "contains no observed\nperformance result" in text
    assert not re.search(
        r"\b(?:mae|rmse|coverage|hit[ _-]?rate)\s*(?:=|:)\s*[+-]?\d",
        text,
        flags=re.IGNORECASE,
    )


def test_producer_keeps_candidate_out_of_combined_v1() -> None:
    source = BUILDER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {
            "_SHADOW_COHERENT_RIDGE_TARGETS",
            "_MODEL_EPOCHS",
        }
    }
    assert assignments["_SHADOW_COHERENT_RIDGE_TARGETS"] == {
        "cpi_headline",
        "cpi_core",
    }
    assert assignments["_MODEL_EPOCHS"]["coherent_ridge_v1"] == "coherent_ridge_v1"
    assert "coherent_ridge_v1" not in _function_source(
        BUILDER_PATH, "_attach_combined_to_items"
    )
    assert "`coherent_ridge_v1`" not in COMBINED_PREREG_PATH.read_text(encoding="utf-8")


def test_dag_and_synapse_bind_the_complete_truth_substrate() -> None:
    target_paths = {
        "data/release_forecast/cpi_truth/alfred_same_release_vintage_proxy_v1.json",
        "data/release_forecast/cpi_truth/parity_report.json",
        "data/release_forecast/cpi_truth/build_completion.json",
        "config/release_forecast_model_registry.yml",
        "research/release_forecast/PREREG_COHERENT_RIDGE_V1.md",
    }
    dag = yaml.safe_load(DAG_PATH.read_text(encoding="utf-8"))
    steps = [
        step
        for lane in dag["lanes"]
        for step in lane.get("steps", [])
        if step.get("id") == "build_release_forecast"
    ]
    assert len(steps) == 1
    # dag.yml carries dependency receipts inside the human-readable step note;
    # conformance owns executable step ordering, while this guard owns the
    # declared data/provenance closure.
    for path in target_paths:
        assert path in steps[0]["note"]

    synapse = yaml.safe_load(SYNAPSE_PATH.read_text(encoding="utf-8"))["artifacts"]
    for artifact_id in (
        "release-cpi-coherent-target-history",
        "release-cpi-truth-parity",
        "release-cpi-truth-build-completion",
    ):
        assert "engine/release_cpi_coherent_shadow.py" in synapse[artifact_id]["consumers"]


def test_governance_suite_has_explicit_ci_owner_and_trigger_closure() -> None:
    manifest = yaml.safe_load(CI_MANIFEST_PATH.read_text(encoding="utf-8"))
    release_job = manifest["jobs"]["unrun-release-forecast"]
    commands = "\n".join(
        step.get("run", "") for step in release_job["steps"] if isinstance(step, dict)
    )
    assert "tests/test_release_cpi_coherent_governance.py" in commands
    assert "tests/test_release_cpi_coherent_shadow.py" in commands

    workflow = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    for path in (
        "tests/test_release_cpi_coherent_governance.py",
        "tests/test_release_cpi_coherent_shadow.py",
        "engine/release_cpi_coherent_shadow.py",
        "scripts/build_release_forecast.py",
        "config/release_forecast_model_registry.yml",
        "research/release_forecast/PREREG_COHERENT_RIDGE_V1.md",
        "data/release_forecast/cpi_truth/**",
    ):
        assert f'      - "{path}"' in workflow
