"""W2A state, preregistration, sealed forecast, and later-outcome contracts."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from engine.neuralweb import market_memory as mm
from engine.neuralweb import market_memory_forward as forward
from tests.test_market_memory import (
    _as_known_at as _w0_packet,
)
from tests.test_market_memory import (
    _observe_snapshot,
    _source_for_feature,
)
from tests.test_market_memory_pit import _packet as _w1_packet

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "market_memory"
W2A_CI_PATHS = (
    "engine/neuralweb/market_memory_forward.py",
    "engine/neuralweb/market_memory_forward_store.py",
    "contracts/market_memory/state_snapshot.v1.schema.json",
    "contracts/market_memory/trial_registration.v1.schema.json",
    "contracts/market_memory/forecast_record.v1.schema.json",
    "contracts/market_memory/outcome_record.v1.schema.json",
    "tests/test_market_memory_forward.py",
    "tests/test_market_memory_forward_store.py",
    "research/KONSEKI_CLEAN_ROOM_MARKET_MEMORY_AND_COGNITIVE_ARCHITECTURE_FOR_FABLE_2026-08-08.md",
)


def _synthetic_w1_packet(*, observed_count: int = 2) -> dict[str, Any]:
    packet = _w0_packet()
    sources = copy.deepcopy(packet["source_receipts"])
    features = copy.deepcopy(packet["feature_receipts"])
    feature_ids = ("macro.regime_state", "rates_credit.curve_state")
    for index, feature_id in enumerate(feature_ids[:observed_count]):
        marker = ("d", "e")[index]
        source = _source_for_feature(feature_id)
        logical_receipt_id = "mmsrc_" + marker * 64
        source.update(
            {
                "receipt_id": logical_receipt_id,
                "artifact_sha256": marker * 64,
                "vintage_id": "mmv_" + marker * 64,
                "revision_id": "mmr_" + marker * 64,
            }
        )
        sources.append(source)
        _observe_snapshot(features, feature_id, logical_receipt_id)
    return _w0_packet(
        source_receipts=sources,
        identity_receipt=copy.deepcopy(packet["identity_receipt"]),
        feature_receipts=features,
    )


def _packet_with_observed_feature(feature_id: str) -> dict[str, Any]:
    packet = _w0_packet()
    if feature_id == "price.ret_20d":
        return packet
    sources = copy.deepcopy(packet["source_receipts"])
    features = copy.deepcopy(packet["feature_receipts"])
    source = _source_for_feature(feature_id)
    logical_receipt_id = "mmsrc_" + "d" * 64
    source.update(
        {
            "receipt_id": logical_receipt_id,
            "artifact_sha256": "d" * 64,
            "vintage_id": "mmv_" + "d" * 64,
            "revision_id": "mmr_" + "d" * 64,
        }
    )
    sources.append(source)
    _observe_snapshot(features, feature_id, logical_receipt_id)
    return _w0_packet(
        source_receipts=sources,
        identity_receipt=copy.deepcopy(packet["identity_receipt"]),
        feature_receipts=features,
    )


def _context_bytes(*, observed_count: int = 2) -> bytes:
    return forward.canonical_json_bytes(
        _synthetic_w1_packet(observed_count=observed_count)
    )


def _domains(exact_context_bytes: bytes) -> list[dict[str, Any]]:
    packet = json.loads(exact_context_bytes)
    return forward._project_w1_domain_states(packet)


def _state(
    *,
    context_bytes: bytes | None = None,
    observed_count: int = 2,
) -> dict[str, Any]:
    exact = context_bytes or _context_bytes(observed_count=observed_count)
    return forward.build_state_snapshot(
        exact_context_bytes=exact,
        store_id="mmstore_" + "1" * 64,
        generation_id="mmgeneration_" + "2" * 64,
        generation_sha256="3" * 64,
        domain_states=_domains(exact),
    )


def _trial(
    *,
    trial_key: str = "synthetic.spy.close.v1",
    outcome_mark: str = "close",
    distribution: dict[str, Any] | None = None,
    proper_score: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return forward.build_trial_registration(
        trial_key=trial_key,
        registered_at="2026-08-01T12:00:00.000000Z",
        state_requirements={
            "state_schema": forward.STATE_SNAPSHOT_SCHEMA,
            "context_schema": mm.AS_KNOWN_AT_SCHEMA,
            "minimum_observed_domains": 2,
            "required_observed_domains": list(forward.CANONICAL_DOMAINS[:2]),
        },
        target={
            "target_id": "spy.close.return",
            "formula": "outcome_close / input_close - 1",
            "formula_version": "synthetic.v1",
            "value_type": "number",
            "unit": "ratio",
            "categories": [],
        },
        marks={
            "input_mark": "close",
            "outcome_mark": outcome_mark,
            "cost_convention": "none",
            "benchmark": "zero_return",
        },
        horizon={
            "anchor": "decision_cutoff",
            "start_offset_seconds": 86_400,
            "end_offset_seconds": 172_800,
            "evaluation_offset_seconds": 172_800,
        },
        distribution=distribution
        or {"kind": "scalar", "quantile_levels": [], "categories": []},
        proper_score=proper_score
        or {"name": "squared_error", "orientation": "lower_is_better"},
        baselines=[
            {
                "baseline_id": "zero_return",
                "baseline_version": "synthetic.v1",
                "config_sha256": "4" * 64,
            }
        ],
        splits={
            "development_start": "2020-01-01T00:00:00.000000Z",
            "development_end": "2022-01-01T00:00:00.000000Z",
            "test_start": "2022-01-01T00:00:00.000000Z",
            "test_end": "2024-01-01T00:00:00.000000Z",
            "live_forward_start": "2024-01-01T00:00:00.000000Z",
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
                "policy_expired",
                "required_domain_missing",
            ],
        },
        expiry={"expires_at": "2027-01-01T00:00:00.000000Z", "action": "abstain"},
        demotion={
            "enabled": True,
            "triggers": [
                "baseline_underperformance",
                "broken_lineage",
                "calibration_decay",
            ],
        },
        implementation={
            "model_sha256": "5" * 64,
            "code_sha256": "6" * 64,
            "config_sha256": "7" * 64,
        },
    )


def _forecast(
    *,
    state: dict[str, Any] | None = None,
    trial: dict[str, Any] | None = None,
    context_bytes: bytes | None = None,
    disposition: str = "issued",
    reason: str | None = None,
) -> dict[str, Any]:
    exact = context_bytes or _context_bytes()
    clean_state = state or _state(context_bytes=exact)
    clean_trial = trial or _trial()
    distribution = (
        {"kind": "scalar", "point": 0.02, "quantiles": [], "probabilities": []}
        if disposition == "issued"
        else None
    )
    return forward.build_forecast_record(
        trial_registration=clean_trial,
        state_snapshot=clean_state,
        exact_context_bytes=exact,
        sealed_at="2026-08-07T20:05:30.000000Z",
        disposition=disposition,
        abstention_reason=reason,
        model_sha256="5" * 64,
        code_sha256="6" * 64,
        config_sha256="7" * 64,
        predictive_distribution=distribution,
    )


def _outcome(
    forecast: dict[str, Any],
    *,
    status: str = "complete",
    revision_number: int = 1,
    revision_of: str | None = None,
) -> dict[str, Any]:
    values = {
        "complete": ({"value_type": "number", "value": 0.015, "unit": "ratio"}, None),
        "censored": (None, "source_window_incomplete"),
        "missing": (None, "source_unavailable"),
    }
    outcome_value, reason = values[status]
    correction = revision_number > 1
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
        reason=reason,
        effective_at=forecast["evaluation_at"],
        source_available_at=(
            "2026-08-09T21:06:00.000000Z"
            if correction
            else "2026-08-09T20:06:00.000000Z"
        ),
        known_at=(
            "2026-08-09T21:07:00.000000Z"
            if correction
            else "2026-08-09T20:07:00.000000Z"
        ),
        observed_at=(
            "2026-08-09T21:08:00.000000Z"
            if correction
            else "2026-08-09T20:08:00.000000Z"
        ),
        recorded_at=(
            "2026-08-09T21:09:00.000000Z"
            if correction
            else "2026-08-09T20:09:00.000000Z"
        ),
        source_receipts=[
            {
                "receipt_id": "synthetic.outcome.source.v1",
                "artifact_sha256": "8" * 64,
                "source_schema": "synthetic.price.v1",
                "source_version": "synthetic.v1",
            }
        ],
        revision_number=revision_number,
        revision_of=revision_of,
        revision_reason="source_revision" if revision_number > 1 else None,
    )


def _schemas() -> dict[str, dict[str, Any]]:
    names = (
        "state_snapshot.v1.schema.json",
        "trial_registration.v1.schema.json",
        "forecast_record.v1.schema.json",
        "outcome_record.v1.schema.json",
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


def _rehash(value: dict[str, Any], *, field: str, prefix: str) -> None:
    core = copy.deepcopy(value)
    core[field] = ""
    value[field] = (
        prefix + hashlib.sha256(forward.canonical_json_bytes(core)).hexdigest()
    )


def test_four_schemas_are_strict_and_validate_runtime_golden_records() -> None:
    schemas = _schemas()
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
        assert schema["minProperties"] == schema["maxProperties"]

    state = _state()
    trial = _trial()
    forecast = _forecast(state=state, trial=trial)
    outcome = _outcome(forecast)
    validators = _validators()
    validators["state_snapshot.v1.schema.json"].validate(state)
    validators["trial_registration.v1.schema.json"].validate(trial)
    validators["forecast_record.v1.schema.json"].validate(forecast)
    validators["outcome_record.v1.schema.json"].validate(outcome)
    validators["outcome_record.v1.schema.json"].validate(
        _outcome(forecast, status="censored")
    )
    validators["outcome_record.v1.schema.json"].validate(
        _outcome(forecast, status="missing")
    )
    integer_state = copy.deepcopy(state)
    integer_state["domain_states"][0]["observations"][0]["value_type"] = "integer"
    integer_state["domain_states"][0]["observations"][0]["value"] = 1
    _rehash(integer_state, field="state_snapshot_id", prefix="mmstate_")
    assert forward.validate_state_snapshot_record(integer_state) == integer_state
    validators["state_snapshot.v1.schema.json"].validate(integer_state)


def test_state_binds_exact_owner_valid_w1_bytes_without_backwriting_context() -> None:
    exact = _context_bytes()
    packet = json.loads(exact)
    assert packet["clocks"]["as_known_at"].endswith(":00Z")
    state = _state(context_bytes=exact)

    assert state["context_id"] == packet["context_id"]
    assert state["as_known_at"] == "2026-08-07T20:05:00.000000Z"
    assert (
        state["context_manifest"]["context_sha256"] == hashlib.sha256(exact).hexdigest()
    )
    assert state["context_manifest"]["context_bytes"] == len(exact)
    assert state["context_manifest"]["state_snapshot_ref"] is None
    assert packet["state_snapshot_ref"] is None
    assert forward.validate_state_snapshot_record(state) == state
    assert forward.validate_state_snapshot(state, exact_context_bytes=exact) == state

    altered = bytearray(exact)
    altered[-2] = ord(" ")
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_state_snapshot(state, exact_context_bytes=bytes(altered))

    fabricated = copy.deepcopy(state)
    fabricated["domain_states"][0]["observations"][0]["source_receipt_ids"] = [
        "mmsrc_" + "f" * 64
    ]
    _rehash(fabricated, field="state_snapshot_id", prefix="mmstate_")
    assert forward.validate_state_snapshot_record(fabricated) == fabricated
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_state_snapshot(fabricated, exact_context_bytes=exact)


def test_state_coverage_is_derived_and_multi_domain_requires_two_observed_planes() -> (
    None
):
    single = _state(observed_count=1)
    multiple = _state(observed_count=2)
    assert single["coverage"]["multi_domain"] is False
    assert multiple["coverage"]["multi_domain"] is True
    assert multiple["coverage"]["n_observed_domains"] == 2
    assert multiple["coverage"]["n_partial_domains"] == 1
    assert multiple["coverage"]["n_missing_domains"] == 11

    forged = copy.deepcopy(single)
    forged["coverage"]["multi_domain"] = True
    _rehash(forged, field="state_snapshot_id", prefix="mmstate_")
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_state_snapshot_record(forged)


@pytest.mark.parametrize("feature_id", sorted(mm.CANONICAL_FEATURE_REGISTRY))
def test_state_projection_accepts_every_owner_valid_w1_feature_id(
    feature_id: str,
) -> None:
    packet = _packet_with_observed_feature(feature_id)
    assert mm.validate_as_known_at_context(packet) == packet
    states = forward._project_w1_domain_states(packet)
    domain = mm.CANONICAL_FEATURE_REGISTRY[feature_id].domain
    projected = next(row for row in states if row["domain"] == domain)
    assert feature_id in {
        observation["feature_id"] for observation in projected["observations"]
    }


def test_state_projection_rejects_imputed_w1_value_without_rejecting_context() -> None:
    packet = _w0_packet()
    sources = copy.deepcopy(packet["source_receipts"])
    features = copy.deepcopy(packet["feature_receipts"])
    price = next(row for row in features if row["feature_id"] == "price.ret_20d")
    source_id = price["source_receipt_ids"][0]
    source = next(row for row in sources if row["receipt_id"] == source_id)
    degraded = {
        "status": "degraded",
        "flags": ["vendor_gap"],
        "staleness_seconds": 300,
        "imputed": True,
    }
    source["quality"] = {**degraded, "staleness_seconds": 3}
    price["quality"] = degraded
    imputed_packet = _w0_packet(
        source_receipts=sources,
        identity_receipt=copy.deepcopy(packet["identity_receipt"]),
        feature_receipts=features,
    )
    assert mm.validate_as_known_at_context(imputed_packet) == imputed_packet

    exact = forward.canonical_json_bytes(imputed_packet)
    projected_states = forward._project_w1_domain_states(imputed_packet)
    technicals = next(row for row in projected_states if row["domain"] == "technicals")
    assert technicals == {
        "domain": "technicals",
        "status": "missing",
        "observations": [],
        "missing_reason": "quality_rejected",
    }
    state = forward.build_state_snapshot(
        exact_context_bytes=exact,
        store_id="mmstore_" + "1" * 64,
        generation_id="mmgeneration_" + "2" * 64,
        generation_sha256="3" * 64,
        domain_states=projected_states,
    )
    assert state["coverage"]["n_missing_domains"] == len(forward.CANONICAL_DOMAINS)
    assert forward.validate_state_snapshot(state, exact_context_bytes=exact) == state

    mixed_sources = copy.deepcopy(imputed_packet["source_receipts"])
    mixed_features = copy.deepcopy(imputed_packet["feature_receipts"])
    technical_source = _source_for_feature("technicals.point_in_time_state")
    technical_receipt_id = "mmsrc_" + "e" * 64
    technical_source.update(
        {
            "receipt_id": technical_receipt_id,
            "artifact_sha256": "e" * 64,
            "vintage_id": "mmv_" + "e" * 64,
            "revision_id": "mmr_" + "e" * 64,
        }
    )
    mixed_sources.append(technical_source)
    _observe_snapshot(
        mixed_features, "technicals.point_in_time_state", technical_receipt_id
    )
    mixed_packet = _w0_packet(
        source_receipts=mixed_sources,
        identity_receipt=copy.deepcopy(imputed_packet["identity_receipt"]),
        feature_receipts=mixed_features,
    )
    mixed_technicals = next(
        row
        for row in forward._project_w1_domain_states(mixed_packet)
        if row["domain"] == "technicals"
    )
    assert mixed_technicals["status"] == "partial"
    assert mixed_technicals["missing_reason"] == "quality_rejected"
    assert [row["feature_id"] for row in mixed_technicals["observations"]] == [
        "technicals.point_in_time_state"
    ]


def test_state_cannot_upgrade_w1_missing_features_with_unrelated_receipts() -> None:
    exact = forward.canonical_json_bytes(_w1_packet())
    state = forward.build_state_snapshot(
        exact_context_bytes=exact,
        store_id="mmstore_" + "1" * 64,
        generation_id="mmgeneration_" + "2" * 64,
        generation_sha256="3" * 64,
        domain_states=_domains(exact),
    )
    forged = copy.deepcopy(state)
    receipt_id = json.loads(exact)["source_receipts"][0]["receipt_id"]
    forged["domain_states"][0] = {
        "domain": "macro",
        "status": "observed",
        "observations": [
            {
                "feature_id": "macro.regime_state",
                "value_type": "number",
                "value": 999,
                "unit": "snapshot_ref",
                "observed_at": "2026-08-07T20:05:00.000000Z",
                "pit_basis": "live_captured",
                "transform_version": "market_memory.macro_regime_transform.v1",
                "source_receipt_ids": [receipt_id],
                "quality": {"status": "ok", "imputed": False},
            }
        ],
        "missing_reason": None,
    }
    forged["coverage"] = forward._coverage(forged["domain_states"])
    _rehash(forged, field="state_snapshot_id", prefix="mmstate_")
    assert forward.validate_state_snapshot_record(forged) == forged
    with pytest.raises(
        forward.MarketMemoryForwardContractError, match="W1 feature receipts"
    ):
        forward.validate_state_snapshot(forged, exact_context_bytes=exact)


@pytest.mark.parametrize(
    "hostile",
    [
        "learnedEmbedding",
        "forecastScore",
        "forecasting",
        "fore-cast",
        "sco.re",
        "scoring",
        "embedder",
        "embed.ding",
        "predictive",
        "futureLabel",
        "labelled",
        "outcomeValue",
        "tradePermission",
        "trading",
        "sizing",
        "gate",
        "gates",
        "gated",
        "gating",
        "ungated",
        "gatekeeper",
        "gatekeepers",
        "gatekeeping",
        "riskGatekeeper",
        "executing",
    ],
)
def test_state_rejects_learned_postevent_and_action_semantic_variants(
    hostile: str,
) -> None:
    candidate = _state()
    candidate["domain_states"][0]["observations"][0]["feature_id"] = hostile
    _rehash(candidate, field="state_snapshot_id", prefix="mmstate_")
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_state_snapshot_record(candidate)


def test_trial_preregistration_freezes_every_governance_surface_and_zero_authority() -> (
    None
):
    trial = _trial()
    assert (
        trial["target"]["target_sha256"]
        == hashlib.sha256(
            forward.canonical_json_bytes({**trial["target"], "target_sha256": ""})
        ).hexdigest()
    )
    assert trial["purge"]["enabled"] is True
    assert trial["embargo"]["enabled"] is True
    assert trial["dependence"]["keys"] == ["context_id", "subject_id"]
    assert trial["trial_budget"]["max_trials"] == 10
    assert trial["abstention"]["required"] is True
    assert trial["expiry"]["action"] == "abstain"
    assert trial["demotion"]["enabled"] is True
    assert trial["implementation"] == {
        "model_sha256": "5" * 64,
        "code_sha256": "6" * 64,
        "config_sha256": "7" * 64,
    }
    assert trial["emission_enabled"] is False
    assert trial["authority"] == dict(forward.AUTHORITY)
    assert not any(
        value is True
        for key, value in trial["authority"].items()
        if key.startswith("may_")
    )


def test_trial_required_domains_accept_canonical_not_lexical_order() -> None:
    trial = _trial()
    trial["state_requirements"]["minimum_observed_domains"] = 3
    trial["state_requirements"]["required_observed_domains"] = [
        "macro",
        "breadth_factors",
        "options",
    ]
    trial["abstention"]["minimum_observed_domains"] = 3
    _rehash(trial, field="trial_registration_id", prefix="mmtrial_")
    assert forward.validate_trial_registration(trial) == trial


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "horizon",
            {
                "anchor": "decision_cutoff",
                "start_offset_seconds": True,
                "end_offset_seconds": 2,
                "evaluation_offset_seconds": 2,
            },
        ),
        ("purge", {"enabled": True, "before_seconds": 1, "after_seconds": 0}),
        ("embargo", {"enabled": False, "duration_seconds": 1}),
        (
            "trial_budget",
            {"max_trials": 1, "max_variants": 1, "family_trials_already_registered": 1},
        ),
    ],
)
def test_trial_rejects_bool_int_and_unfrozen_leakage_or_budget_controls(
    field: str, value: dict[str, Any]
) -> None:
    trial = _trial()
    trial[field] = value
    _rehash(trial, field="trial_registration_id", prefix="mmtrial_")
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_trial_registration(trial)


def test_forecast_is_deterministic_sealed_join_and_has_no_postevent_fields() -> None:
    exact = _context_bytes()
    state = _state(context_bytes=exact)
    trial = _trial()
    first = _forecast(state=state, trial=trial, context_bytes=exact)
    second = _forecast(state=state, trial=trial, context_bytes=exact)
    assert first == second
    assert first["as_known_at"] == first["decision_cutoff"]
    assert first["decision_cutoff"] <= first["sealed_at"] < first["horizon_start"]
    assert first["horizon_end"] == first["evaluation_at"]
    assert first["baseline_refs"] == trial["baselines"]
    assert (
        first["plan_sha256"]
        == hashlib.sha256(forward.canonical_json_bytes(trial)).hexdigest()
    )
    assert first["target_sha256"] == trial["target"]["target_sha256"]
    assert first["emission_enabled"] is False
    assert not ({"outcome", "score", "postmortem", "labels"} & set(first))
    assert forward.validate_forecast_record(first) == first
    assert (
        forward.validate_forecast_record_join(
            first,
            trial_registration=trial,
            state_snapshot=state,
            exact_context_bytes=exact,
        )
        == first
    )


def test_outcome_event_identity_binds_frozen_marks_across_trials() -> None:
    exact = _context_bytes()
    state = _state(context_bytes=exact)
    close_trial = _trial()
    adjusted_trial = _trial(
        trial_key="synthetic.spy.adjusted_close.v1",
        outcome_mark="adjusted_close",
    )
    close_forecast = _forecast(state=state, trial=close_trial, context_bytes=exact)
    adjusted_forecast = _forecast(
        state=state, trial=adjusted_trial, context_bytes=exact
    )
    assert (
        close_trial["outcome_definition_sha256"]
        != adjusted_trial["outcome_definition_sha256"]
    )
    assert close_forecast["outcome_event_id"] != adjusted_forecast["outcome_event_id"]
    close_outcome = _outcome(close_forecast)
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_outcome_record_join(
            close_outcome,
            forecast_record=adjusted_forecast,
            trial_registration=adjusted_trial,
        )


def test_forecast_records_explicit_abstention_and_rejects_silent_opportunity_loss() -> (
    None
):
    exact = _context_bytes(observed_count=1)
    state = _state(context_bytes=exact, observed_count=1)
    trial = _trial()
    abstained = _forecast(
        state=state,
        trial=trial,
        context_bytes=exact,
        disposition="abstained",
        reason="insufficient_domains",
    )
    assert abstained["disposition"] == "abstained"
    assert abstained["predictive_distribution"] is None
    assert abstained["abstention_reason"] == "insufficient_domains"

    with pytest.raises(forward.MarketMemoryForwardContractError):
        _forecast(state=state, trial=trial, context_bytes=exact)

    complete_exact = _context_bytes()
    with pytest.raises(forward.MarketMemoryForwardContractError):
        _forecast(
            state=_state(context_bytes=complete_exact),
            trial=trial,
            context_bytes=complete_exact,
            disposition="abstained",
            reason="insufficient_domains",
        )


def test_quantile_forecast_rejects_crossed_distribution() -> None:
    exact = _context_bytes()
    state = _state(context_bytes=exact)
    trial = _trial(
        distribution={
            "kind": "quantiles",
            "quantile_levels": [0.1, 0.9],
            "categories": [],
        },
        proper_score={"name": "pinball_loss", "orientation": "lower_is_better"},
    )
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.build_forecast_record(
            trial_registration=trial,
            state_snapshot=state,
            exact_context_bytes=exact,
            sealed_at="2026-08-07T20:05:30.000000Z",
            disposition="issued",
            abstention_reason=None,
            model_sha256="5" * 64,
            code_sha256="6" * 64,
            config_sha256="7" * 64,
            predictive_distribution={
                "kind": "quantiles",
                "point": None,
                "quantiles": [
                    {"level": 0.1, "value": 0.1},
                    {"level": 0.9, "value": -0.1},
                ],
                "probabilities": [],
            },
        )


def test_forecast_join_rejects_plan_state_target_baseline_and_cutoff_drift() -> None:
    exact = _context_bytes()
    state = _state(context_bytes=exact)
    trial = _trial()
    forecast = _forecast(state=state, trial=trial, context_bytes=exact)
    for field, replacement in (
        ("plan_sha256", "a" * 64),
        ("target_sha256", "b" * 64),
        ("outcome_definition_sha256", "f" * 64),
        ("model_sha256", "c" * 64),
        ("code_sha256", "d" * 64),
        ("config_sha256", "e" * 64),
        ("context_id", "mmctx_" + "c" * 64),
        ("as_known_at", "2026-08-07T20:04:59.000000Z"),
    ):
        candidate = copy.deepcopy(forecast)
        candidate[field] = replacement
        if field in {"target_sha256", "outcome_definition_sha256", "context_id"}:
            candidate["outcome_event_id"] = forward._outcome_event_id(
                context_id=candidate["context_id"],
                outcome_definition_sha256=candidate["outcome_definition_sha256"],
                horizon_start=candidate["horizon_start"],
                horizon_end=candidate["horizon_end"],
                evaluation_at=candidate["evaluation_at"],
            )
            candidate["forecast_key"] = forward._forecast_key(
                trial_registration_id=candidate["trial_registration_id"],
                state_snapshot_id=candidate["state_snapshot_id"],
                outcome_event_id=candidate["outcome_event_id"],
            )
        _rehash(candidate, field="forecast_id", prefix="mmforecast_")
        with pytest.raises(forward.MarketMemoryForwardContractError):
            forward.validate_forecast_record_join(
                candidate,
                trial_registration=trial,
                state_snapshot=state,
                exact_context_bytes=exact,
            )


def test_outcome_is_separate_event_fact_with_complete_censored_missing_and_revisions() -> (
    None
):
    forecast = _forecast()
    complete = _outcome(forecast)
    censored = _outcome(forecast, status="censored")
    missing = _outcome(forecast, status="missing")
    correction = _outcome(
        forecast,
        revision_number=2,
        revision_of=complete["outcome_record_id"],
    )
    assert complete["outcome_event_id"] == forecast["outcome_event_id"]
    assert complete["effective_at"] == forecast["evaluation_at"]
    assert complete["status"] == "complete" and complete["outcome_value"] is not None
    assert censored["outcome_value"] is None
    assert missing["outcome_value"] is None
    assert correction["revision_of"] == complete["outcome_record_id"]
    assert correction["outcome_record_id"] != complete["outcome_record_id"]
    assert "forecast_id" not in complete and "score" not in complete
    assert forward.validate_outcome_record(correction) == correction
    assert (
        forward.validate_outcome_record_revision(correction, previous_outcome=complete)
        == correction
    )
    assert (
        forward.validate_outcome_record_join(
            complete,
            forecast_record=forecast,
            trial_registration=_trial(),
        )
        == complete
    )


def test_outcome_rejects_prematurity_clock_reversal_and_false_revision_lineage() -> (
    None
):
    forecast = _forecast()
    complete = _outcome(forecast)
    reversed_clock = copy.deepcopy(complete)
    reversed_clock["known_at"] = "2026-08-09T20:05:00.000000Z"
    _rehash(reversed_clock, field="outcome_record_id", prefix="mmoutcome_")
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_outcome_record(reversed_clock)

    premature = copy.deepcopy(complete)
    premature["effective_at"] = forecast["horizon_start"]
    _rehash(premature, field="outcome_record_id", prefix="mmoutcome_")
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_outcome_record(premature)

    false_revision = copy.deepcopy(complete)
    false_revision["revision_of"] = "mmoutcome_" + "9" * 64
    _rehash(false_revision, field="outcome_record_id", prefix="mmoutcome_")
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_outcome_record(false_revision)

    correction = _outcome(
        forecast,
        revision_number=2,
        revision_of="mmoutcome_" + "9" * 64,
    )
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_outcome_record_revision(correction, previous_outcome=complete)


def test_outcome_join_rejects_value_type_and_unit_drift_from_frozen_target() -> None:
    trial = _trial()
    forecast = _forecast(trial=trial)
    outcome = _outcome(forecast)
    outcome["outcome_value"]["unit"] = "percent"
    _rehash(outcome, field="outcome_record_id", prefix="mmoutcome_")
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_outcome_record_join(
            outcome,
            forecast_record=forecast,
            trial_registration=trial,
        )


@pytest.mark.parametrize(
    "mutation",
    ["trial_key", "plan_sha256", "baseline_refs", "model_sha256"],
)
def test_outcome_join_rejects_forecast_drift_from_preregistration(
    mutation: str,
) -> None:
    trial = _trial()
    forecast = _forecast(trial=trial)
    outcome = _outcome(forecast)
    forged = copy.deepcopy(forecast)
    if mutation == "trial_key":
        forged[mutation] = "synthetic.forged.v1"
    elif mutation == "baseline_refs":
        forged[mutation][0]["config_sha256"] = "9" * 64
    else:
        forged[mutation] = "9" * 64
    _rehash(forged, field="forecast_id", prefix="mmforecast_")
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_outcome_record_join(
            outcome,
            forecast_record=forged,
            trial_registration=trial,
        )


@pytest.mark.parametrize(
    ("loader", "record"),
    [
        (forward.load_state_snapshot_record_json, _state),
        (forward.load_trial_registration_json, _trial),
        (forward.load_forecast_record_json, _forecast),
    ],
)
def test_strict_loaders_round_trip_canonical_bytes_and_reject_duplicate_keys(
    loader: Any, record: Any
) -> None:
    value = record()
    body = forward.canonical_json_bytes(value)
    assert loader(body) == value
    duplicate = b'{"schema":"x","schema":"y"}'
    with pytest.raises(forward.MarketMemoryForwardContractError):
        loader(duplicate)


def test_outcome_loader_and_all_json_guards_reject_bom_nonfinite_depth_and_cycles() -> (
    None
):
    outcome = _outcome(_forecast())
    body = forward.canonical_json_bytes(outcome)
    assert forward.load_outcome_record_json(body) == outcome
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.load_outcome_record_json(b"\xef\xbb\xbf" + body)
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.load_outcome_record_json(json.dumps(outcome, indent=2).encode())
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.load_outcome_record_json(body.replace(b"0.015", b"NaN"))
    deep: Any = "leaf"
    for _ in range(25):
        deep = [deep]
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.canonical_json_bytes(deep)
    cycle: list[Any] = []
    cycle.append(cycle)
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.canonical_json_bytes(cycle)


def test_schema_and_runtime_reject_recursive_extension_and_authority_drift() -> None:
    validators = _validators()
    state = _state()
    hostile = copy.deepcopy(state)
    hostile["domain_states"][0]["observations"][0]["authorityOverride"] = {
        "may_trade": True
    }
    with pytest.raises(ValidationError):
        validators["state_snapshot.v1.schema.json"].validate(hostile)
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_state_snapshot_record(hostile)

    trial = _trial()
    trial["authority"]["may_rank"] = True
    _rehash(trial, field="trial_registration_id", prefix="mmtrial_")
    with pytest.raises(ValidationError):
        validators["trial_registration.v1.schema.json"].validate(trial)
    with pytest.raises(forward.MarketMemoryForwardContractError):
        forward.validate_trial_registration(trial)


def test_public_api_is_frozen_and_module_is_pure_contract_code() -> None:
    expected = {
        "build_state_snapshot",
        "validate_state_snapshot",
        "validate_state_snapshot_record",
        "load_state_snapshot_json",
        "load_state_snapshot_record_json",
        "build_trial_registration",
        "validate_trial_registration",
        "load_trial_registration_json",
        "build_forecast_record",
        "validate_forecast_record",
        "validate_forecast_record_join",
        "load_forecast_record_json",
        "load_forecast_record_join_json",
        "build_outcome_record",
        "validate_outcome_record",
        "validate_outcome_record_join",
        "validate_outcome_record_revision",
        "load_outcome_record_json",
        "canonical_json_bytes",
    }
    assert expected <= set(forward.__all__)

    tree = ast.parse(inspect.getsource(forward))
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


def test_w2a_contract_store_and_tests_share_the_market_memory_ci_gate() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    jobs = (ROOT / ".github/ci/legacy-jobs.yml").read_text(encoding="utf-8")
    lane = jobs.split("  market-memory-contract:", 1)[1].split("\n  group-pulse:", 1)[0]

    for path in W2A_CI_PATHS:
        assert f'      - "{path}"' in workflow, f"missing W2A CI trigger: {path}"
    assert "tests/test_market_memory_forward.py" in lane
    assert "tests/test_market_memory_forward_store.py" in lane
