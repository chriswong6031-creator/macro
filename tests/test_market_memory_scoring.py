"""W2B1 synthetic-only baseline bundle and per-event scoring contracts."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
from decimal import Context, localcontext
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from engine.neuralweb import market_memory as mm
from engine.neuralweb import market_memory_forward as forward
from engine.neuralweb import market_memory_scoring as scoring
from tests.test_market_memory import _as_known_at as _w0_packet
from tests.test_market_memory import _observe_snapshot, _source_for_feature

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "market_memory"
W2B1_CI_PATHS = (
    "engine/neuralweb/market_memory_scoring.py",
    "contracts/market_memory/baseline_forecast_bundle.v1.schema.json",
    "contracts/market_memory/event_score_record.v1.schema.json",
    "tests/test_market_memory_scoring.py",
    "research/KONSEKI_CLEAN_ROOM_MARKET_MEMORY_AND_COGNITIVE_ARCHITECTURE_FOR_FABLE_2026-08-08.md",
)


def _context_bytes() -> bytes:
    packet = _w0_packet()
    sources = copy.deepcopy(packet["source_receipts"])
    features = copy.deepcopy(packet["feature_receipts"])
    for index, feature_id in enumerate(
        ("macro.regime_state", "rates_credit.curve_state")
    ):
        marker = ("d", "e")[index]
        source = _source_for_feature(feature_id)
        receipt_id = "mmsrc_" + marker * 64
        source.update(
            {
                "receipt_id": receipt_id,
                "artifact_sha256": marker * 64,
                "vintage_id": "mmv_" + marker * 64,
                "revision_id": "mmr_" + marker * 64,
            }
        )
        sources.append(source)
        _observe_snapshot(features, feature_id, receipt_id)
    exact = _w0_packet(
        source_receipts=sources,
        identity_receipt=copy.deepcopy(packet["identity_receipt"]),
        feature_receipts=features,
    )
    return forward.canonical_json_bytes(exact)


def _state(exact: bytes) -> dict[str, Any]:
    return forward.build_state_snapshot(
        exact_context_bytes=exact,
        store_id="mmstore_" + "1" * 64,
        generation_id="mmgeneration_" + "2" * 64,
        generation_sha256="3" * 64,
        domain_states=forward._project_w1_domain_states(json.loads(exact)),
    )


def _trial(
    *,
    kind: str = "scalar",
    proper_score: str = "squared_error",
    baselines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if kind == "categorical":
        target = {
            "target_id": "spy.direction",
            "formula": "sign(outcome_close / input_close - 1)",
            "formula_version": "synthetic.v1",
            "value_type": "string",
            "unit": "category",
            "categories": ["down", "flat", "up"],
        }
        distribution = {
            "kind": "categorical",
            "quantile_levels": [],
            "categories": ["down", "flat", "up"],
        }
    elif kind == "quantiles":
        target = {
            "target_id": "spy.close.return",
            "formula": "outcome_close / input_close - 1",
            "formula_version": "synthetic.v1",
            "value_type": "number",
            "unit": "ratio",
            "categories": [],
        }
        distribution = {
            "kind": "quantiles",
            "quantile_levels": [0.25, 0.75],
            "categories": [],
        }
    else:
        target = {
            "target_id": "spy.close.return",
            "formula": "outcome_close / input_close - 1",
            "formula_version": "synthetic.v1",
            "value_type": "number",
            "unit": "ratio",
            "categories": [],
        }
        distribution = {"kind": "scalar", "quantile_levels": [], "categories": []}
    return forward.build_trial_registration(
        trial_key=f"synthetic.spy.{kind}.{proper_score}.v1",
        registered_at="2026-08-01T12:00:00.000000Z",
        state_requirements={
            "state_schema": forward.STATE_SNAPSHOT_SCHEMA,
            "context_schema": mm.AS_KNOWN_AT_SCHEMA,
            "minimum_observed_domains": 2,
            "required_observed_domains": list(forward.CANONICAL_DOMAINS[:2]),
        },
        target=target,
        marks={
            "input_mark": "close",
            "outcome_mark": "close",
            "cost_convention": "none",
            "benchmark": "frozen_baselines",
        },
        horizon={
            "anchor": "decision_cutoff",
            "start_offset_seconds": 86_400,
            "end_offset_seconds": 172_800,
            "evaluation_offset_seconds": 172_800,
        },
        distribution=distribution,
        proper_score={"name": proper_score, "orientation": "lower_is_better"},
        baselines=baselines
        or [
            {
                "baseline_id": "baseline.zero",
                "baseline_version": "synthetic.v1",
                "config_sha256": "4" * 64,
            }
        ],
        splits={
            "development_start": "2020-01-01T00:00:00.000000Z",
            "development_end": "2022-01-01T00:00:00.000000Z",
            "test_start": "2022-01-01T00:00:00.000000Z",
            "test_end": "2024-01-01T00:00:00.000000Z",
            "live_forward_start": "2026-08-02T00:00:00.000000Z",
        },
        purge={"enabled": True, "before_seconds": 172_800, "after_seconds": 0},
        embargo={"enabled": True, "duration_seconds": 172_800},
        dependence={
            "keys": ["context_id", "subject_id"],
            "clustering": "effective_event_cluster",
            "cluster_version": "synthetic.v1",
        },
        trial_budget={
            "max_trials": 10,
            "max_variants": 2,
            "family_trials_already_registered": 0,
        },
        abstention={
            "required": True,
            "minimum_observed_domains": 2,
            "allowed_reasons": [
                "insufficient_domains",
                "model_unavailable",
                "policy_expired",
                "required_domain_missing",
            ],
        },
        expiry={"expires_at": "2027-01-01T00:00:00.000000Z", "action": "abstain"},
        demotion={
            "enabled": True,
            "triggers": ["baseline_underperformance", "broken_lineage"],
        },
        implementation={
            "model_sha256": "5" * 64,
            "code_sha256": "6" * 64,
            "config_sha256": "7" * 64,
        },
    )


def _distribution(kind: str) -> dict[str, Any]:
    if kind == "quantiles":
        return {
            "kind": "quantiles",
            "point": None,
            "quantiles": [
                {"level": 0.25, "value": 0},
                {"level": 0.75, "value": 2},
            ],
            "probabilities": [],
        }
    if kind == "categorical":
        return {
            "kind": "categorical",
            "point": None,
            "quantiles": [],
            "probabilities": [
                {"category": "down", "probability": 0.1},
                {"category": "flat", "probability": 0.6},
                {"category": "up", "probability": 0.3},
            ],
        }
    return {"kind": "scalar", "point": 0.02, "quantiles": [], "probabilities": []}


def _forecast(
    *,
    trial: dict[str, Any],
    state: dict[str, Any],
    exact: bytes,
    disposition: str = "issued",
    distribution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return forward.build_forecast_record(
        trial_registration=trial,
        state_snapshot=state,
        exact_context_bytes=exact,
        sealed_at="2026-08-07T20:05:30.000000Z",
        disposition=disposition,
        abstention_reason="model_unavailable" if disposition == "abstained" else None,
        model_sha256="5" * 64,
        code_sha256="6" * 64,
        config_sha256="7" * 64,
        predictive_distribution=(
            distribution or _distribution(trial["distribution"]["kind"])
            if disposition == "issued"
            else None
        ),
    )


def _outcome(
    forecast: dict[str, Any],
    trial: dict[str, Any],
    *,
    status: str = "complete",
    revision_number: int = 1,
    revision_of: str | None = None,
    value: object | None = None,
) -> dict[str, Any]:
    if trial["target"]["value_type"] == "string":
        default_value: object = "up"
    else:
        default_value = 0.015
    outcome_value = (
        {
            "value_type": trial["target"]["value_type"],
            "value": default_value if value is None else value,
            "unit": trial["target"]["unit"],
        }
        if status == "complete"
        else None
    )
    reasons = {
        "complete": None,
        "censored": "source_window_incomplete",
        "missing": "source_unavailable",
    }
    later = revision_number > 1
    return forward.build_outcome_record(
        outcome_event_id=forecast["outcome_event_id"],
        context_id=forecast["context_id"],
        target_sha256=forecast["target_sha256"],
        outcome_definition_sha256=forecast["outcome_definition_sha256"],
        horizon_start=forecast["horizon_start"],
        horizon_end=forecast["horizon_end"],
        evaluation_at=forecast["evaluation_at"],
        status=status,
        outcome_value=outcome_value,
        reason=reasons[status],
        effective_at=forecast["evaluation_at"],
        source_available_at=(
            "2026-08-09T21:06:00.000000Z" if later else "2026-08-09T20:06:00.000000Z"
        ),
        known_at=(
            "2026-08-09T21:07:00.000000Z" if later else "2026-08-09T20:07:00.000000Z"
        ),
        observed_at=(
            "2026-08-09T21:08:00.000000Z" if later else "2026-08-09T20:08:00.000000Z"
        ),
        recorded_at=(
            "2026-08-09T21:09:00.000000Z" if later else "2026-08-09T20:09:00.000000Z"
        ),
        source_receipts=[
            {
                "receipt_id": "synthetic.outcome.v1",
                "artifact_sha256": "8" * 64,
                "source_schema": "synthetic.price.v1",
                "source_version": "synthetic.v1",
            }
        ],
        revision_number=revision_number,
        revision_of=revision_of,
        revision_reason="source_revision" if later else None,
    )


def _baseline_rows(
    trial: dict[str, Any], *, unavailable: bool = False
) -> list[dict[str, Any]]:
    distribution = _distribution(trial["distribution"]["kind"])
    if distribution["kind"] == "scalar":
        distribution["point"] = 0
    rows = []
    for ref in trial["baselines"]:
        rows.append(
            {
                **ref,
                "producer_code_sha256": "9" * 64,
                "fit": {"kind": "fixed_rule", "cutoff": None, "artifact_sha256": None},
                "disposition": "unavailable" if unavailable else "issued",
                "unavailable_reason": "baseline_input_unavailable"
                if unavailable
                else None,
                "predictive_distribution": None
                if unavailable
                else copy.deepcopy(distribution),
            }
        )
    return rows


def _fixture(
    *,
    kind: str = "scalar",
    proper_score: str = "squared_error",
    forecast_disposition: str = "issued",
    outcome_status: str = "complete",
    baseline_unavailable: bool = False,
) -> tuple[
    bytes,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    exact = _context_bytes()
    state = _state(exact)
    trial = _trial(kind=kind, proper_score=proper_score)
    forecast = _forecast(
        trial=trial, state=state, exact=exact, disposition=forecast_disposition
    )
    outcome = _outcome(forecast, trial, status=outcome_status)
    bundle = scoring.build_baseline_forecast_bundle(
        trial_registration=trial,
        state_snapshot=state,
        forecast_record=forecast,
        exact_context_bytes=exact,
        baseline_rows=_baseline_rows(trial, unavailable=baseline_unavailable),
    )
    return exact, state, trial, forecast, outcome, bundle


def _score(
    exact: bytes,
    state: dict[str, Any],
    trial: dict[str, Any],
    forecast: dict[str, Any],
    outcome: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    return scoring.build_event_score_record(
        trial_registration=trial,
        state_snapshot=state,
        forecast_record=forecast,
        exact_context_bytes=exact,
        outcome_record=outcome,
        baseline_forecast_bundle=bundle,
        evaluated_at="2026-08-09T22:00:00.000000Z",
        evaluator_code_sha256="a" * 64,
        evaluator_config_sha256="b" * 64,
    )


def _schemas() -> dict[str, dict[str, Any]]:
    names = (
        "state_snapshot.v1.schema.json",
        "baseline_forecast_bundle.v1.schema.json",
        "event_score_record.v1.schema.json",
    )
    return {name: json.loads((SCHEMA_DIR / name).read_text()) for name in names}


def _validators() -> dict[str, Draft202012Validator]:
    schemas = _schemas()
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    return {
        name: Draft202012Validator(
            schema, registry=registry, format_checker=FormatChecker()
        )
        for name, schema in schemas.items()
    }


def _rehash(record: dict[str, Any], *, field: str, prefix: str) -> None:
    core = copy.deepcopy(record)
    core[field] = ""
    record[field] = (
        prefix + hashlib.sha256(forward.canonical_json_bytes(core)).hexdigest()
    )


def test_schemas_are_strict_and_match_runtime_golden_records() -> None:
    schemas = _schemas()
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
        assert schema["minProperties"] == schema["maxProperties"]
    exact, state, trial, forecast, outcome, bundle = _fixture()
    score = _score(exact, state, trial, forecast, outcome, bundle)
    validators = _validators()
    validators["baseline_forecast_bundle.v1.schema.json"].validate(bundle)
    validators["event_score_record.v1.schema.json"].validate(score)
    assert scoring.validate_baseline_forecast_bundle_record(bundle) == bundle
    assert scoring.validate_event_score_record(score) == score


@pytest.mark.parametrize(
    ("proper_score", "expected"),
    [
        ("squared_error", "0.040000000000000000"),
        ("absolute_error", "0.200000000000000000"),
    ],
)
def test_scalar_formulas_are_exact_decimal_and_deterministic(
    proper_score: str, expected: str
) -> None:
    trial = _trial(proper_score=proper_score)
    result = scoring.score_predictive_distribution(
        trial_registration=trial,
        predictive_distribution={
            "kind": "scalar",
            "point": 0.1,
            "quantiles": [],
            "probabilities": [],
        },
        outcome_value={"value_type": "number", "value": 0.3, "unit": "ratio"},
    )
    assert result["score_value"] == {"kind": "finite", "decimal": expected}
    assert result == scoring.score_predictive_distribution(
        trial_registration=copy.deepcopy(trial),
        predictive_distribution={
            "kind": "scalar",
            "point": 0.1,
            "quantiles": [],
            "probabilities": [],
        },
        outcome_value={"value_type": "number", "value": 0.3, "unit": "ratio"},
    )


def test_mean_pinball_loss_uses_frozen_grid_and_mean_without_hidden_factor() -> None:
    trial = _trial(kind="quantiles", proper_score="pinball_loss")
    result = scoring.score_predictive_distribution(
        trial_registration=trial,
        predictive_distribution=_distribution("quantiles"),
        outcome_value={"value_type": "number", "value": 1, "unit": "ratio"},
    )
    assert result == {
        "formula": "mean_pinball_loss",
        "formula_version": "mean_pinball_loss.v1",
        "numeric_convention": "decimal64_half_even_q18/v1",
        "orientation": "lower_is_better",
        "score_value": {"kind": "finite", "decimal": "0.250000000000000000"},
    }


def test_multiclass_log_loss_is_unclipped_and_zero_probability_is_infinity() -> None:
    trial = _trial(kind="categorical", proper_score="log_loss")
    finite = scoring.score_predictive_distribution(
        trial_registration=trial,
        predictive_distribution=_distribution("categorical"),
        outcome_value={"value_type": "string", "value": "flat", "unit": "category"},
    )
    assert finite["formula_version"] == "multiclass_log_loss.v1"
    assert finite["score_value"]["kind"] == "finite"
    assert finite["score_value"]["decimal"] == "0.510825623765990683"
    zero = _distribution("categorical")
    zero["probabilities"] = [
        {"category": "down", "probability": 0.5},
        {"category": "flat", "probability": 0},
        {"category": "up", "probability": 0.5},
    ]
    assert scoring.score_predictive_distribution(
        trial_registration=trial,
        predictive_distribution=zero,
        outcome_value={"value_type": "string", "value": "flat", "unit": "category"},
    )["score_value"] == {"kind": "positive_infinity", "decimal": None}


def test_multiclass_brier_is_sum_not_mean_or_binary_projection() -> None:
    trial = _trial(kind="categorical", proper_score="brier_score")
    result = scoring.score_predictive_distribution(
        trial_registration=trial,
        predictive_distribution=_distribution("categorical"),
        outcome_value={"value_type": "string", "value": "flat", "unit": "category"},
    )
    assert result["formula_version"] == "multiclass_brier_sum.v1"
    assert result["score_value"] == {
        "kind": "finite",
        "decimal": "0.260000000000000000",
    }


def test_categorical_probabilities_require_exact_decimal_mass_without_repair() -> None:
    trial = _trial(kind="categorical", proper_score="brier_score")
    near_one = _distribution("categorical")
    near_one["probabilities"] = [
        {"category": "down", "probability": 0.1},
        {"category": "flat", "probability": 0.6},
        {"category": "up", "probability": 0.2999999999995},
    ]
    with pytest.raises(scoring.MarketMemoryScoringContractError, match="sum to one"):
        scoring.score_predictive_distribution(
            trial_registration=trial,
            predictive_distribution=near_one,
            outcome_value={
                "value_type": "string",
                "value": "flat",
                "unit": "category",
            },
        )

    exact = _context_bytes()
    with pytest.raises(forward.MarketMemoryForwardContractError, match="sum to one"):
        _forecast(
            trial=trial,
            state=_state(exact),
            exact=exact,
            distribution=near_one,
        )

    tiny_tail = _distribution("categorical")
    tiny_tail["probabilities"] = [
        {"category": "down", "probability": 0},
        {"category": "flat", "probability": 1},
        {"category": "up", "probability": 1e-100},
    ]
    with localcontext(Context(prec=1)):
        with pytest.raises(
            scoring.MarketMemoryScoringContractError, match="sum to one"
        ):
            scoring.score_predictive_distribution(
                trial_registration=trial,
                predictive_distribution=tiny_tail,
                outcome_value={
                    "value_type": "string",
                    "value": "flat",
                    "unit": "category",
                },
            )
        with pytest.raises(
            forward.MarketMemoryForwardContractError, match="sum to one"
        ):
            _forecast(
                trial=trial,
                state=_state(exact),
                exact=exact,
                distribution=tiny_tail,
            )
        valid = scoring.score_predictive_distribution(
            trial_registration=trial,
            predictive_distribution=_distribution("categorical"),
            outcome_value={
                "value_type": "string",
                "value": "flat",
                "unit": "category",
            },
        )
    assert valid["score_value"]["decimal"] == "0.260000000000000000"


def test_distribution_and_outcome_semantics_are_exactly_preregistered() -> None:
    quantile_trial = _trial(kind="quantiles", proper_score="pinball_loss")
    drifted = _distribution("quantiles")
    drifted["quantiles"][0]["level"] = 0.2
    with pytest.raises(scoring.MarketMemoryScoringContractError):
        scoring.score_predictive_distribution(
            trial_registration=quantile_trial,
            predictive_distribution=drifted,
            outcome_value={"value_type": "number", "value": 0.01, "unit": "ratio"},
        )
    categorical = _trial(kind="categorical", proper_score="log_loss")
    for hostile in (
        {"value_type": "string", "value": "sideways", "unit": "category"},
        {"value_type": "string", "value": "up", "unit": "ratio"},
        {"value_type": "number", "value": 1, "unit": "category"},
    ):
        with pytest.raises(scoring.MarketMemoryScoringContractError):
            scoring.score_predictive_distribution(
                trial_registration=categorical,
                predictive_distribution=_distribution("categorical"),
                outcome_value=hostile,
            )


def test_missing_reordered_duplicate_and_crossed_distribution_grids_are_not_repaired() -> (
    None
):
    quantile_trial = _trial(kind="quantiles", proper_score="pinball_loss")
    quantile_hostiles: list[dict[str, Any]] = []
    missing = _distribution("quantiles")
    missing["quantiles"] = missing["quantiles"][:-1]
    quantile_hostiles.append(missing)
    reordered = _distribution("quantiles")
    reordered["quantiles"] = list(reversed(reordered["quantiles"]))
    quantile_hostiles.append(reordered)
    crossed = _distribution("quantiles")
    crossed["quantiles"][0]["value"] = 3
    quantile_hostiles.append(crossed)
    for distribution in quantile_hostiles:
        with pytest.raises(scoring.MarketMemoryScoringContractError):
            scoring.score_predictive_distribution(
                trial_registration=quantile_trial,
                predictive_distribution=distribution,
                outcome_value={"value_type": "number", "value": 1, "unit": "ratio"},
            )

    categorical_trial = _trial(kind="categorical", proper_score="brier_score")
    categorical_hostiles: list[dict[str, Any]] = []
    missing_category = _distribution("categorical")
    missing_category["probabilities"] = missing_category["probabilities"][:-1]
    missing_category["probabilities"][0]["probability"] = 0.4
    categorical_hostiles.append(missing_category)
    duplicate = _distribution("categorical")
    duplicate["probabilities"][2]["category"] = "flat"
    categorical_hostiles.append(duplicate)
    permuted = _distribution("categorical")
    permuted["probabilities"] = list(reversed(permuted["probabilities"]))
    categorical_hostiles.append(permuted)
    extra = _distribution("categorical")
    extra["probabilities"] = [
        {"category": "down", "probability": 0.1},
        {"category": "flat", "probability": 0.5},
        {"category": "sideways", "probability": 0.1},
        {"category": "up", "probability": 0.3},
    ]
    categorical_hostiles.append(extra)
    for distribution in categorical_hostiles:
        with pytest.raises(scoring.MarketMemoryScoringContractError):
            scoring.score_predictive_distribution(
                trial_registration=categorical_trial,
                predictive_distribution=distribution,
                outcome_value={
                    "value_type": "string",
                    "value": "flat",
                    "unit": "category",
                },
            )


def test_bundle_exactly_covers_preregistered_baselines_and_fit_is_predecision() -> None:
    baselines = [
        {
            "baseline_id": "baseline.alpha",
            "baseline_version": "v1",
            "config_sha256": "c" * 64,
        },
        {
            "baseline_id": "baseline.beta",
            "baseline_version": "v1",
            "config_sha256": "d" * 64,
        },
    ]
    exact = _context_bytes()
    state = _state(exact)
    trial = _trial(baselines=baselines)
    forecast = _forecast(trial=trial, state=state, exact=exact)
    rows = _baseline_rows(trial)
    rows[1]["fit"] = {
        "kind": "predecision_fit",
        "cutoff": forecast["decision_cutoff"],
        "artifact_sha256": "e" * 64,
    }
    bundle = scoring.build_baseline_forecast_bundle(
        trial_registration=trial,
        state_snapshot=state,
        forecast_record=forecast,
        exact_context_bytes=exact,
        baseline_rows=rows,
    )
    assert [row["baseline_id"] for row in bundle["baseline_rows"]] == [
        "baseline.alpha",
        "baseline.beta",
    ]
    assert bundle["sealed_at"] == forecast["sealed_at"]
    assert bundle["claims"] == dict(scoring.CLAIMS)
    for hostile in (rows[:-1], rows + [copy.deepcopy(rows[-1])], list(reversed(rows))):
        with pytest.raises(scoring.MarketMemoryScoringContractError):
            scoring.build_baseline_forecast_bundle(
                trial_registration=trial,
                state_snapshot=state,
                forecast_record=forecast,
                exact_context_bytes=exact,
                baseline_rows=hostile,
            )
    late = copy.deepcopy(rows)
    late[1]["fit"]["cutoff"] = "2026-08-07T20:05:31.000000Z"
    with pytest.raises(scoring.MarketMemoryScoringContractError, match="later"):
        scoring.build_baseline_forecast_bundle(
            trial_registration=trial,
            state_snapshot=state,
            forecast_record=forecast,
            exact_context_bytes=exact,
            baseline_rows=late,
        )


@pytest.mark.parametrize(
    "forecast_disposition",
    ["issued", "abstained"],
)
@pytest.mark.parametrize("outcome_status", ["complete", "censored", "missing"])
@pytest.mark.parametrize("baseline_unavailable", [False, True])
def test_score_dispositions_preserve_abstention_unavailable_censored_and_missing(
    forecast_disposition: str,
    outcome_status: str,
    baseline_unavailable: bool,
) -> None:
    fixture = _fixture(
        forecast_disposition=forecast_disposition,
        outcome_status=outcome_status,
        baseline_unavailable=baseline_unavailable,
    )
    score = _score(*fixture)
    candidate = score["candidate_score"]
    baseline = score["baseline_scores"][0]
    candidate_reason = (
        "forecast_abstained"
        if forecast_disposition == "abstained"
        else None
        if outcome_status == "complete"
        else f"outcome_{outcome_status}"
    )
    baseline_reason = (
        "baseline_unavailable"
        if baseline_unavailable
        else None
        if outcome_status == "complete"
        else f"outcome_{outcome_status}"
    )
    assert candidate["not_scored_reason"] == candidate_reason
    assert baseline["not_scored_reason"] == baseline_reason
    assert candidate["disposition"] == ("not_scored" if candidate_reason else "scored")
    assert baseline["disposition"] == ("not_scored" if baseline_reason else "scored")
    if candidate_reason:
        assert candidate["score_value"] is None
    if baseline_reason:
        assert baseline["score_value"] is None
    _validators()["event_score_record.v1.schema.json"].validate(score)


def test_schema_runtime_parity_covers_every_disposition_and_infinity_fence() -> None:
    validator = _validators()["event_score_record.v1.schema.json"]
    for arguments in (
        {"forecast_disposition": "abstained"},
        {"outcome_status": "censored"},
        {"outcome_status": "missing"},
        {"baseline_unavailable": True},
    ):
        fixture = _fixture(**arguments)
        score = _score(*fixture)
        validator.validate(score)
        assert scoring.validate_event_score_record(score) == score

    exact = _context_bytes()
    state = _state(exact)
    trial = _trial(kind="categorical", proper_score="log_loss")
    zero = _distribution("categorical")
    zero["probabilities"] = [
        {"category": "down", "probability": 0.5},
        {"category": "flat", "probability": 0.5},
        {"category": "up", "probability": 0},
    ]
    forecast = _forecast(trial=trial, state=state, exact=exact, distribution=zero)
    outcome = _outcome(forecast, trial, value="up")
    bundle = scoring.build_baseline_forecast_bundle(
        trial_registration=trial,
        state_snapshot=state,
        forecast_record=forecast,
        exact_context_bytes=exact,
        baseline_rows=_baseline_rows(trial),
    )
    log_score = _score(exact, state, trial, forecast, outcome, bundle)
    assert log_score["candidate_score"]["score_value"] == {
        "kind": "positive_infinity",
        "decimal": None,
    }
    validator.validate(log_score)

    scalar_fixture = _fixture()
    scalar_score = _score(*scalar_fixture)
    hostile = copy.deepcopy(scalar_score)
    hostile["candidate_score"]["score_value"] = {
        "kind": "positive_infinity",
        "decimal": None,
    }
    _rehash(hostile, field="event_score_record_id", prefix="mmeventscore_")
    with pytest.raises(ValidationError):
        validator.validate(hostile)
    with pytest.raises(scoring.MarketMemoryScoringContractError, match="only valid"):
        scoring.validate_event_score_record(hostile)

    missing_score = _score(*_fixture(outcome_status="missing"))
    missing_score["outcome_reason"] = "source_window_incomplete"
    _rehash(missing_score, field="event_score_record_id", prefix="mmeventscore_")
    with pytest.raises(ValidationError):
        validator.validate(missing_score)
    with pytest.raises(scoring.MarketMemoryScoringContractError, match="missing"):
        scoring.validate_event_score_record(missing_score)


def test_outcome_correction_creates_distinct_revision_bound_score() -> None:
    exact, state, trial, forecast, first, bundle = _fixture()
    first_score = _score(exact, state, trial, forecast, first, bundle)
    corrected = _outcome(
        forecast,
        trial,
        revision_number=2,
        revision_of=first["outcome_record_id"],
        value=0.03,
    )
    corrected_score = _score(exact, state, trial, forecast, corrected, bundle)
    assert corrected_score["outcome_revision_number"] == 2
    assert corrected_score["outcome_record_id"] == corrected["outcome_record_id"]
    assert (
        corrected_score["event_score_record_id"] != first_score["event_score_record_id"]
    )
    assert (
        corrected_score["candidate_score"]["score_value"]
        != first_score["candidate_score"]["score_value"]
    )


def test_event_join_recomputes_scores_and_rejects_identity_or_value_tampering() -> None:
    exact, state, trial, forecast, outcome, bundle = _fixture()
    score = _score(exact, state, trial, forecast, outcome, bundle)
    hostile = copy.deepcopy(score)
    hostile["candidate_score"]["score_value"]["decimal"] = "0.000000000000000000"
    _rehash(hostile, field="event_score_record_id", prefix="mmeventscore_")
    assert scoring.validate_event_score_record(hostile) == hostile
    with pytest.raises(scoring.MarketMemoryScoringContractError, match="recomputed"):
        scoring.validate_event_score_record_join(
            hostile,
            trial_registration=trial,
            state_snapshot=state,
            forecast_record=forecast,
            exact_context_bytes=exact,
            outcome_record=outcome,
            baseline_forecast_bundle=bundle,
            expected_evaluator_code_sha256="a" * 64,
            expected_evaluator_config_sha256="b" * 64,
        )
    with pytest.raises(scoring.MarketMemoryScoringContractError, match="recomputed"):
        scoring.validate_event_score_record_join(
            score,
            trial_registration=trial,
            state_snapshot=state,
            forecast_record=forecast,
            exact_context_bytes=exact,
            outcome_record=outcome,
            baseline_forecast_bundle=bundle,
            expected_evaluator_code_sha256="c" * 64,
            expected_evaluator_config_sha256="b" * 64,
        )
    hostile_bundle = copy.deepcopy(bundle)
    hostile_bundle["forecast_id"] = "mmforecast_" + "f" * 64
    _rehash(
        hostile_bundle, field="baseline_forecast_bundle_id", prefix="mmbaselinebundle_"
    )
    assert (
        scoring.validate_baseline_forecast_bundle_record(hostile_bundle)
        == hostile_bundle
    )
    with pytest.raises(scoring.MarketMemoryScoringContractError, match="forecast_id"):
        scoring.validate_baseline_forecast_bundle_join(
            hostile_bundle,
            trial_registration=trial,
            state_snapshot=state,
            forecast_record=forecast,
            exact_context_bytes=exact,
        )


def test_evaluation_clock_cannot_precede_active_outcome_revision() -> None:
    exact, state, trial, forecast, outcome, bundle = _fixture()
    with pytest.raises(scoring.MarketMemoryScoringContractError, match="precede"):
        scoring.build_event_score_record(
            trial_registration=trial,
            state_snapshot=state,
            forecast_record=forecast,
            exact_context_bytes=exact,
            outcome_record=outcome,
            baseline_forecast_bundle=bundle,
            evaluated_at="2026-08-09T20:08:59.000000Z",
            evaluator_code_sha256="a" * 64,
            evaluator_config_sha256="b" * 64,
        )


def test_strict_loaders_round_trip_and_reject_noncanonical_or_hostile_json() -> None:
    exact, state, trial, forecast, outcome, bundle = _fixture()
    score = _score(exact, state, trial, forecast, outcome, bundle)
    bundle_body = forward.canonical_json_bytes(bundle)
    score_body = forward.canonical_json_bytes(score)
    assert (
        scoring.load_baseline_forecast_bundle_join_json(
            bundle_body,
            trial_registration=trial,
            state_snapshot=state,
            forecast_record=forecast,
            exact_context_bytes=exact,
        )
        == bundle
    )
    assert (
        scoring.load_event_score_record_join_json(
            score_body,
            trial_registration=trial,
            state_snapshot=state,
            forecast_record=forecast,
            exact_context_bytes=exact,
            outcome_record=outcome,
            baseline_forecast_bundle=bundle,
            expected_evaluator_code_sha256="a" * 64,
            expected_evaluator_config_sha256="b" * 64,
        )
        == score
    )
    hostiles = [
        b"\xef\xbb\xbf" + score_body,
        json.dumps(score, indent=2).encode(),
        b'{"schema":"x","schema":"y"}',
        b'{"value":NaN}',
        b"[1,2,3]",
        b"{" + b'"x":' + b"[" * 40 + b"0" + b"]" * 40 + b"}",
        b" " * (256 * 1024 + 1),
    ]
    for body in hostiles:
        with pytest.raises(scoring.MarketMemoryScoringContractError):
            scoring.load_event_score_record_join_json(
                body,
                trial_registration=trial,
                state_snapshot=state,
                forecast_record=forecast,
                exact_context_bytes=exact,
                outcome_record=outcome,
                baseline_forecast_bundle=bundle,
                expected_evaluator_code_sha256="a" * 64,
                expected_evaluator_config_sha256="b" * 64,
            )


def test_runtime_and_schemas_reject_extensions_authority_and_false_claims() -> None:
    exact, state, trial, forecast, outcome, bundle = _fixture()
    score = _score(exact, state, trial, forecast, outcome, bundle)
    validators = _validators()
    mutations = (
        ("bundle", bundle, "aggregate_score", 1),
        ("bundle", bundle, "skill", True),
        ("score", score, "winner", "candidate"),
        ("score", score, "delta_vs_baseline", -1),
    )
    for kind, original, field, value in mutations:
        hostile = copy.deepcopy(original)
        hostile[field] = value
        validator = validators[
            "baseline_forecast_bundle.v1.schema.json"
            if kind == "bundle"
            else "event_score_record.v1.schema.json"
        ]
        with pytest.raises(ValidationError):
            validator.validate(hostile)
        runtime = (
            scoring.validate_baseline_forecast_bundle_record
            if kind == "bundle"
            else scoring.validate_event_score_record
        )
        with pytest.raises(scoring.MarketMemoryScoringContractError):
            runtime(hostile)
    for field in scoring.CLAIMS:
        hostile = copy.deepcopy(score)
        hostile["claims"][field] = True
        _rehash(hostile, field="event_score_record_id", prefix="mmeventscore_")
        with pytest.raises(ValidationError):
            validators["event_score_record.v1.schema.json"].validate(hostile)
        with pytest.raises(scoring.MarketMemoryScoringContractError):
            scoring.validate_event_score_record(hostile)
    hostile = copy.deepcopy(bundle)
    hostile["authority"]["may_rank"] = True
    _rehash(hostile, field="baseline_forecast_bundle_id", prefix="mmbaselinebundle_")
    with pytest.raises(scoring.MarketMemoryScoringContractError):
        scoring.validate_baseline_forecast_bundle_record(hostile)


def test_builders_detach_inputs_and_never_mutate_w2a_records() -> None:
    exact, state, trial, forecast, outcome, bundle = _fixture()
    originals = copy.deepcopy((state, trial, forecast, outcome, bundle))
    score = _score(exact, state, trial, forecast, outcome, bundle)
    assert (state, trial, forecast, outcome, bundle) == tuple(originals)
    score["claims"]["aggregate_eligible"] = True
    rebuilt = _score(exact, state, trial, forecast, outcome, bundle)
    assert rebuilt["claims"] == dict(scoring.CLAIMS)


def test_public_api_is_frozen_and_module_has_no_operational_dependencies() -> None:
    expected = {
        "MarketMemoryScoringContractError",
        "build_baseline_forecast_bundle",
        "validate_baseline_forecast_bundle_record",
        "validate_baseline_forecast_bundle_join",
        "load_baseline_forecast_bundle_join_json",
        "score_predictive_distribution",
        "build_event_score_record",
        "validate_event_score_record",
        "validate_event_score_record_join",
        "load_event_score_record_join_json",
    }
    assert expected <= set(scoring.__all__)
    tree = ast.parse(inspect.getsource(scoring))
    forbidden_import_roots = {
        "os",
        "pathlib",
        "socket",
        "subprocess",
        "urllib",
        "requests",
        "httpx",
        "fastapi",
    }
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert not (forbidden_import_roots & imported)
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not ({"now", "utcnow", "time", "open", "write_text", "write_bytes"} & calls)
    source = inspect.getsource(scoring).casefold()
    for forbidden in (
        "skill_delta",
        "winner_id",
        "aggregate_record",
        "opportunity_writer",
        "default_root",
    ):
        assert forbidden not in source


def test_w2b1_contract_and_test_share_the_market_memory_ci_gate() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    jobs = (ROOT / ".github/ci/legacy-jobs.yml").read_text(encoding="utf-8")
    lane = jobs.split("  market-memory-contract:", 1)[1].split("\n  group-pulse:", 1)[0]

    for path in W2B1_CI_PATHS:
        assert f'      - "{path}"' in workflow, f"missing W2B1 CI trigger: {path}"
    assert "tests/test_market_memory_scoring.py" in lane


def test_bool_numbers_nonfinite_and_noncanonical_score_decimals_are_rejected() -> None:
    trial = _trial()
    for point in (True, float("nan"), float("inf"), 10**16):
        distribution = _distribution("scalar")
        distribution["point"] = point
        with pytest.raises(scoring.MarketMemoryScoringContractError):
            scoring.score_predictive_distribution(
                trial_registration=trial,
                predictive_distribution=distribution,
                outcome_value={"value_type": "number", "value": 0, "unit": "ratio"},
            )
    exact, state, trial, forecast, outcome, bundle = _fixture()
    score = _score(exact, state, trial, forecast, outcome, bundle)
    for text in (
        "-0.000000000000000000",
        "00.000000000000000000",
        "1.0",
        "1e-3",
        "0.000",
    ):
        hostile = copy.deepcopy(score)
        hostile["candidate_score"]["score_value"] = {"kind": "finite", "decimal": text}
        _rehash(hostile, field="event_score_record_id", prefix="mmeventscore_")
        with pytest.raises(scoring.MarketMemoryScoringContractError):
            scoring.validate_event_score_record(hostile)


def test_numeric_boundary_negative_zero_and_dictionary_order_are_deterministic() -> (
    None
):
    trial = _trial(proper_score="squared_error")
    boundary = scoring.score_predictive_distribution(
        trial_registration=trial,
        predictive_distribution={
            "kind": "scalar",
            "point": 10**15,
            "quantiles": [],
            "probabilities": [],
        },
        outcome_value={
            "value_type": "number",
            "value": -(10**15),
            "unit": "ratio",
        },
    )
    assert boundary["score_value"] == {
        "kind": "finite",
        "decimal": "4000000000000000000000000000000.000000000000000000",
    }
    negative_zero = scoring.score_predictive_distribution(
        trial_registration=trial,
        predictive_distribution={
            "probabilities": [],
            "quantiles": [],
            "point": -0.0,
            "kind": "scalar",
        },
        outcome_value={"unit": "ratio", "value": 0, "value_type": "number"},
    )
    assert negative_zero["score_value"]["decimal"] == "0.000000000000000000"
    reordered = scoring.score_predictive_distribution(
        trial_registration=dict(reversed(list(trial.items()))),
        predictive_distribution={
            "point": -0.0,
            "kind": "scalar",
            "probabilities": [],
            "quantiles": [],
        },
        outcome_value={"value": 0, "value_type": "number", "unit": "ratio"},
    )
    assert reordered == negative_zero


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        (0.5e-18, "0.000000000000000000"),
        (1.5e-18, "0.000000000000000002"),
        (2.5e-18, "0.000000000000000002"),
    ],
)
def test_final_q18_quantization_uses_half_even_ties(
    point: float, expected: str
) -> None:
    trial = _trial(proper_score="absolute_error")
    result = scoring.score_predictive_distribution(
        trial_registration=trial,
        predictive_distribution={
            "kind": "scalar",
            "point": point,
            "quantiles": [],
            "probabilities": [],
        },
        outcome_value={"value_type": "number", "value": 0, "unit": "ratio"},
    )
    assert result["score_value"] == {"kind": "finite", "decimal": expected}
