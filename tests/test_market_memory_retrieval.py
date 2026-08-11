"""W4A synthetic supplied-candidate retrieval conformance."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from engine.neuralweb import market_memory as mm
from engine.neuralweb import market_memory_forward as forward
from engine.neuralweb import market_memory_retrieval as retrieval
from tests.test_market_memory_forward import _synthetic_w1_packet, _trial

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "market_memory"
_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?Z$")


def _shift(value: Any, days: int) -> Any:
    if type(value) is dict:
        return {key: _shift(item, days) for key, item in value.items()}
    if type(value) is list:
        return [_shift(item, days) for item in value]
    if type(value) is str and _STAMP.fullmatch(value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        shifted = parsed + timedelta(days=days)
        suffix = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in value else "%Y-%m-%dT%H:%M:%SZ"
        return shifted.strftime(suffix)
    return copy.deepcopy(value)


def _context(days: int) -> bytes:
    packet = _shift(_synthetic_w1_packet(), days)
    source_id_map: dict[str, str] = {}
    for source in packet["source_receipts"]:
        old_id = source["receipt_id"]
        binding = source["identity_binding"]
        if binding is not None:
            binding["content_sha256"] = mm._identity_binding_sha256(source, binding)
        source["receipt_id"] = mm._source_receipt_id(source)
        source_id_map[old_id] = source["receipt_id"]
    for feature in packet["feature_receipts"]:
        feature["source_receipt_ids"] = [
            source_id_map[source_id] for source_id in feature["source_receipt_ids"]
        ]
    identity = packet["identity_receipt"]
    identity["membership_source_receipt_id"] = source_id_map[
        identity["membership_source_receipt_id"]
    ]
    identity["calendar_source_receipt_id"] = source_id_map[
        identity["calendar_source_receipt_id"]
    ]
    identity["source_receipt_ids"] = sorted(
        source_id_map[source_id] for source_id in identity["source_receipt_ids"]
    )
    identity["receipt_id"] = mm._identity_receipt_id(identity)
    rebuilt = mm.build_as_known_at_context(
        subject=packet["subject"],
        event_time=packet["clocks"]["event_time"],
        as_known_at=packet["clocks"]["as_known_at"],
        mode=packet["mode"],
        source_receipts=packet["source_receipts"],
        identity_receipt=packet["identity_receipt"],
        feature_receipts=packet["feature_receipts"],
        required_domains=packet["required_domains"],
    )
    return forward.canonical_json_bytes(rebuilt)


def _episode(days: int, *, trial: dict[str, Any]) -> dict[str, Any]:
    exact = _context(days)
    state = forward.build_state_snapshot(
        exact_context_bytes=exact,
        store_id="mmstore_" + "1" * 64,
        generation_id="mmgeneration_" + "2" * 64,
        generation_sha256="3" * 64,
        domain_states=forward._project_w1_domain_states(json.loads(exact)),
    )
    decision = datetime.strptime(state["as_known_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )
    forecast = forward.build_forecast_record(
        trial_registration=trial,
        state_snapshot=state,
        exact_context_bytes=exact,
        sealed_at=(decision + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        disposition="issued",
        abstention_reason=None,
        model_sha256="5" * 64,
        code_sha256="6" * 64,
        config_sha256="7" * 64,
        predictive_distribution={
            "kind": "scalar",
            "point": 0.02,
            "quantiles": [],
            "probabilities": [],
        },
    )
    return {
        "state_snapshot": state,
        "forecast_record": forecast,
        "exact_context_bytes": exact,
    }


def _registration(trial: dict[str, Any], *, maximum_results: int = 3) -> dict[str, Any]:
    return retrieval.build_retrieval_registration(
        trial_registration=trial,
        registration_key="synthetic.spy.euclidean.v1",
        registered_at="2026-08-01T18:00:00.000000Z",
        coordinate_specs=[
            {
                "coordinate_id": "alpha",
                "unit": "zscore",
                "transform_version": "synthetic.v1",
                "scale_decimal": "1.000000000000000000",
            },
            {
                "coordinate_id": "beta",
                "unit": "ratio",
                "transform_version": "synthetic.v1",
                "scale_decimal": "2.000000000000000000",
            },
        ],
        maximum_results=maximum_results,
        producer_code_sha256="8" * 64,
        producer_config_sha256="9" * 64,
    )


def _candidate(
    episode: dict[str, Any], alpha: str | None, beta: str | None
) -> dict[str, Any]:
    return {
        **episode,
        "coordinates": {"alpha": alpha, "beta": beta},
    }


def _record(
    *,
    query_days: int = 20,
    candidate_days: tuple[int, ...] = (0, 5, 10),
    candidate_coordinates: tuple[tuple[str | None, str | None], ...] = (
        ("3.000000000000000000", "8.000000000000000000"),
        ("0.000000000000000000", "6.000000000000000000"),
        ("1.000000000000000000", "0.000000000000000000"),
    ),
    query_coordinates: dict[str, str | None] | None = None,
    maximum_results: int = 3,
) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]
]:
    trial = _trial()
    registration = _registration(trial, maximum_results=maximum_results)
    query = _episode(query_days, trial=trial)
    candidates = [
        _candidate(_episode(days, trial=trial), *coordinates)
        for days, coordinates in zip(candidate_days, candidate_coordinates, strict=True)
    ]
    coordinates = query_coordinates or {
        "alpha": "0.000000000000000000",
        "beta": "0.000000000000000000",
    }
    record = retrieval.build_episodic_retrieval_record(
        retrieval_registration=registration,
        trial_registration=trial,
        query_state_snapshot=query["state_snapshot"],
        query_forecast_record=query["forecast_record"],
        query_exact_context_bytes=query["exact_context_bytes"],
        query_coordinates=coordinates,
        candidate_inputs=candidates,
        retrieved_at="2026-08-28T00:00:00.000000Z",
    )
    return record, registration, trial, query, candidates


def _registry() -> Registry:
    registry = Registry()
    for path in SCHEMA_DIR.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


def _validate_schema(name: str, value: dict[str, Any]) -> None:
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    Draft202012Validator(
        schema,
        registry=_registry(),
        format_checker=FormatChecker(),
    ).validate(value)


def _rehash(value: dict[str, Any], *, field: str, prefix: str) -> None:
    core = copy.deepcopy(value)
    core[field] = ""
    value[field] = (
        prefix + hashlib.sha256(forward.canonical_json_bytes(core)).hexdigest()
    )


def test_registration_binds_exact_trial_and_frozen_zero_claims() -> None:
    trial = _trial()
    registration = _registration(trial)

    assert (
        registration["trial_plan_sha256"]
        == hashlib.sha256(forward.canonical_json_bytes(trial)).hexdigest()
    )
    assert registration["distance"] == {
        "formula": "exact_normalized_euclidean",
        "formula_version": "exact_normalized_euclidean.v1",
        "numeric_convention": "decimal64_half_even_q18/v1",
        "normalization": "synthetic_fixed_positive_scales",
        "missingness": "complete_case_no_repair",
    }
    assert not any(registration["claims"].values())
    assert registration["authority"] == dict(forward.AUTHORITY)
    assert registration["emission_enabled"] is False
    _validate_schema("retrieval_registration.v1.schema.json", registration)


@pytest.mark.parametrize(
    ("registered_at", "message"),
    [
        ("2026-08-01T11:59:59.999999Z", "after the trial"),
        ("2026-08-02T00:00:00.000000Z", "before live forward"),
    ],
)
def test_registration_must_precede_live_forward_and_follow_trial(
    registered_at, message
) -> None:
    trial = _trial()
    kwargs = {
        "trial_registration": trial,
        "registration_key": "synthetic.spy.euclidean.v1",
        "registered_at": registered_at,
        "coordinate_specs": [
            {
                "coordinate_id": "x",
                "unit": "ratio",
                "transform_version": "v1",
                "scale_decimal": "1.000000000000000000",
            }
        ],
        "maximum_results": 1,
        "producer_code_sha256": "8" * 64,
        "producer_config_sha256": "9" * 64,
    }
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError, match=message):
        retrieval.build_retrieval_registration(**kwargs)


@pytest.mark.parametrize(
    "specs",
    [
        [
            {
                "coordinate_id": "z",
                "unit": "ratio",
                "transform_version": "v1",
                "scale_decimal": "1.000000000000000000",
            },
            {
                "coordinate_id": "a",
                "unit": "ratio",
                "transform_version": "v1",
                "scale_decimal": "1.000000000000000000",
            },
        ],
        [
            {
                "coordinate_id": "x",
                "unit": "ratio",
                "transform_version": "v1",
                "scale_decimal": "0.000000000000000000",
            }
        ],
        [
            {
                "coordinate_id": "x",
                "unit": "ratio",
                "transform_version": "v1",
                "scale_decimal": "1",
            }
        ],
    ],
)
def test_registration_rejects_unsorted_or_noncanonical_fixed_scales(specs) -> None:
    trial = _trial()
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError):
        retrieval.build_retrieval_registration(
            trial_registration=trial,
            registration_key="synthetic.spy.euclidean.v1",
            registered_at="2026-08-01T18:00:00.000000Z",
            coordinate_specs=specs,
            maximum_results=1,
            producer_code_sha256="8" * 64,
            producer_config_sha256="9" * 64,
        )


def test_decimal_distance_has_no_intermediate_quantization_and_normalizes_zero() -> (
    None
):
    registration = _registration(_trial())
    assert (
        retrieval.score_normalized_euclidean(
            retrieval_registration=registration,
            query_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
            candidate_coordinates={
                "alpha": "3.000000000000000000",
                "beta": "8.000000000000000000",
            },
        )
        == "5.000000000000000000"
    )
    assert (
        retrieval.score_normalized_euclidean(
            retrieval_registration=registration,
            query_coordinates={
                "alpha": "-0.000000000000000001",
                "beta": "0.000000000000000000",
            },
            candidate_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
        )
        == "0.000000000000000001"
    )
    assert (
        retrieval.score_normalized_euclidean(
            retrieval_registration=registration,
            query_coordinates={"alpha": None, "beta": "0.000000000000000000"},
            candidate_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
        )
        is None
    )


@pytest.mark.parametrize(
    "coordinates",
    [
        {"alpha": "0.0", "beta": "0.000000000000000000"},
        {"alpha": "-0.000000000000000000", "beta": "0.000000000000000000"},
        {"alpha": float("nan"), "beta": "0.000000000000000000"},
        {"alpha": "0.000000000000000000"},
        {
            "alpha": "0.000000000000000000",
            "beta": "0.000000000000000000",
            "gamma": None,
        },
    ],
)
def test_distance_rejects_noncanonical_missing_or_extra_coordinates(
    coordinates,
) -> None:
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError):
        retrieval.score_normalized_euclidean(
            retrieval_registration=_registration(_trial()),
            query_coordinates=coordinates,
            candidate_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
        )


def test_record_ranks_supplied_candidates_only_and_never_estimates_effective_n() -> (
    None
):
    record, registration, trial, query, candidates = _record()

    assert record["counts"] == {
        "supplied_candidates": 3,
        "distance_eligible_candidates": 3,
        "selected_nonoverlapping_candidates": 3,
    }
    by_id = {row["forecast_id"]: row for row in record["candidates"]}
    expected_order = [candidates[2], candidates[1], candidates[0]]
    assert record["selected_forecast_ids"] == [
        row["forecast_record"]["forecast_id"] for row in expected_order
    ]
    assert [
        by_id[row["forecast_record"]["forecast_id"]]["distance_rank"]
        for row in expected_order
    ] == [1, 2, 3]
    assert record["effective_n"] == {
        "status": "not_estimated",
        "value": None,
        "reason": "dependence_model_not_evidence_ready",
    }
    assert not any(record["claims"].values())
    assert "candidate_population_complete" in record["claims"]
    _validate_schema("episodic_retrieval_record.v1.schema.json", record)
    assert (
        retrieval.validate_episodic_retrieval_record_join(
            record,
            retrieval_registration=registration,
            trial_registration=trial,
            query_state_snapshot=query["state_snapshot"],
            query_forecast_record=query["forecast_record"],
            query_exact_context_bytes=query["exact_context_bytes"],
            query_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
            candidate_inputs=candidates,
        )
        == record
    )


def test_ties_break_by_forecast_id_and_rows_remain_forecast_id_sorted() -> None:
    record, *_ = _record(
        candidate_days=(0, 5),
        candidate_coordinates=(
            ("1.000000000000000000", "0.000000000000000000"),
            ("-1.000000000000000000", "0.000000000000000000"),
        ),
    )
    ids = [row["forecast_id"] for row in record["candidates"]]
    assert ids == sorted(ids)
    assert record["selected_forecast_ids"] == sorted(ids)


def test_query_and_selected_interval_overlap_are_explicit_and_half_open() -> None:
    record, *_ = _record(
        candidate_days=(0, 2, 18),
        candidate_coordinates=(
            ("1.000000000000000000", "0.000000000000000000"),
            ("2.000000000000000000", "0.000000000000000000"),
            ("0.500000000000000000", "0.000000000000000000"),
        ),
    )
    rows = {row["decision_cutoff"][:10]: row for row in record["candidates"]}
    near_query = next(
        row for row in record["candidates"] if row["reason"] == "query_interval_overlap"
    )
    assert near_query["distance_value"] is None
    selection_reject = next(
        row
        for row in record["candidates"]
        if row["reason"] == "selection_interval_overlap"
    )
    assert selection_reject["overlap_with_forecast_ids"] == [
        record["selected_forecast_ids"][0]
    ]
    assert record["counts"] == {
        "supplied_candidates": 3,
        "distance_eligible_candidates": 2,
        "selected_nonoverlapping_candidates": 1,
    }
    assert rows


def test_touching_half_open_candidate_intervals_do_not_overlap() -> None:
    record, *_ = _record(
        candidate_days=(0, 4),
        candidate_coordinates=(
            ("1.000000000000000000", "0.000000000000000000"),
            ("2.000000000000000000", "0.000000000000000000"),
        ),
    )
    assert record["counts"]["selected_nonoverlapping_candidates"] == 2
    assert all(row["disposition"] == "selected" for row in record["candidates"])


def test_query_missing_abstains_and_candidate_missing_is_only_ineligible() -> None:
    abstained, *_ = _record(
        candidate_days=(0,),
        candidate_coordinates=(("1.000000000000000000", "1.000000000000000000"),),
        query_coordinates={"alpha": None, "beta": "0.000000000000000000"},
    )
    assert abstained["retrieval_disposition"] == "abstained"
    assert abstained["selected_forecast_ids"] == []
    assert abstained["candidates"][0]["reason"] == "query_coordinate_unavailable"

    candidate_missing, *_ = _record(
        candidate_days=(0,),
        candidate_coordinates=((None, "1.000000000000000000"),),
    )
    assert candidate_missing["retrieval_disposition"] == "completed"
    assert (
        candidate_missing["candidates"][0]["reason"]
        == "candidate_coordinate_unavailable"
    )


def test_self_duplicate_late_and_maximum_results_are_deterministic() -> None:
    record, registration, trial, query, candidates = _record(
        candidate_days=(0, 5),
        candidate_coordinates=(
            ("1.000000000000000000", "0.000000000000000000"),
            ("2.000000000000000000", "0.000000000000000000"),
        ),
        maximum_results=1,
    )
    assert [row["reason"] for row in record["candidates"]].count(
        "maximum_results_reached"
    ) == 1

    duplicate = candidates + [copy.deepcopy(candidates[0])]
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError, match="repeat"):
        retrieval.build_episodic_retrieval_record(
            retrieval_registration=registration,
            trial_registration=trial,
            query_state_snapshot=query["state_snapshot"],
            query_forecast_record=query["forecast_record"],
            query_exact_context_bytes=query["exact_context_bytes"],
            query_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
            candidate_inputs=duplicate,
            retrieved_at="2026-08-28T00:00:00.000000Z",
        )

    query_candidate = {
        **query,
        "coordinates": {
            "alpha": "1.000000000000000000",
            "beta": "0.000000000000000000",
        },
    }
    late = _candidate(
        _episode(21, trial=trial),
        "2.000000000000000000",
        "0.000000000000000000",
    )
    exclusions = retrieval.build_episodic_retrieval_record(
        retrieval_registration=registration,
        trial_registration=trial,
        query_state_snapshot=query["state_snapshot"],
        query_forecast_record=query["forecast_record"],
        query_exact_context_bytes=query["exact_context_bytes"],
        query_coordinates={
            "alpha": "0.000000000000000000",
            "beta": "0.000000000000000000",
        },
        candidate_inputs=[query_candidate, late],
        retrieved_at="2026-08-29T00:00:00.000000Z",
    )
    assert {row["reason"] for row in exclusions["candidates"]} == {
        "self_forecast",
        "not_strictly_earlier",
    }

    unavailable_self = retrieval.build_episodic_retrieval_record(
        retrieval_registration=registration,
        trial_registration=trial,
        query_state_snapshot=query["state_snapshot"],
        query_forecast_record=query["forecast_record"],
        query_exact_context_bytes=query["exact_context_bytes"],
        query_coordinates={
            "alpha": None,
            "beta": "0.000000000000000000",
        },
        candidate_inputs=[query_candidate],
        retrieved_at="2026-08-29T00:00:00.000000Z",
    )
    assert unavailable_self["candidates"][0]["reason"] == (
        "query_coordinate_unavailable"
    )
    assert retrieval.validate_episodic_retrieval_record(unavailable_self) == (
        unavailable_self
    )

    false_self = copy.deepcopy(exclusions)
    next(
        row
        for row in false_self["candidates"]
        if row["reason"] == "not_strictly_earlier"
    )["reason"] = "self_forecast"
    _rehash(
        false_self,
        field="episodic_retrieval_record_id",
        prefix="mmepisodicretrieval_",
    )
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError, match="self"):
        retrieval.validate_episodic_retrieval_record(false_self)

    wrong_precedence = copy.deepcopy(exclusions)
    next(
        row
        for row in wrong_precedence["candidates"]
        if row["reason"] == "self_forecast"
    )["reason"] = "self_context"
    _rehash(
        wrong_precedence,
        field="episodic_retrieval_record_id",
        prefix="mmepisodicretrieval_",
    )
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError, match="self"):
        retrieval.validate_episodic_retrieval_record(wrong_precedence)


def test_exact_join_rebuild_detects_coordinate_candidate_and_trial_tampering() -> None:
    record, registration, trial, query, candidates = _record()
    tampered_candidates = copy.deepcopy(candidates)
    tampered_candidates[0]["coordinates"]["alpha"] = "4.000000000000000000"
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError, match="differs"):
        retrieval.validate_episodic_retrieval_record_join(
            record,
            retrieval_registration=registration,
            trial_registration=trial,
            query_state_snapshot=query["state_snapshot"],
            query_forecast_record=query["forecast_record"],
            query_exact_context_bytes=query["exact_context_bytes"],
            query_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
            candidate_inputs=tampered_candidates,
        )

    changed_trial = copy.deepcopy(trial)
    changed_trial["purge"]["before_seconds"] += 1
    _rehash(changed_trial, field="trial_registration_id", prefix="mmtrial_")
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError):
        retrieval.validate_retrieval_registration_join(
            registration, trial_registration=changed_trial
        )


def test_retrieved_at_cannot_retroactively_influence_query_forecast() -> None:
    trial = _trial()
    registration = _registration(trial)
    query = _episode(20, trial=trial)
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError, match="sealed"):
        retrieval.build_episodic_retrieval_record(
            retrieval_registration=registration,
            trial_registration=trial,
            query_state_snapshot=query["state_snapshot"],
            query_forecast_record=query["forecast_record"],
            query_exact_context_bytes=query["exact_context_bytes"],
            query_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
            candidate_inputs=[],
            retrieved_at="2026-08-27T20:05:00.000000Z",
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["claims"].__setitem__("retrieval_quality_evaluated", True),
        lambda value: value["authority"].__setitem__("may_rank", True),
        lambda value: value["counts"].__setitem__("supplied_candidates", 99),
        lambda value: value["effective_n"].update({"status": "estimated", "value": 3}),
        lambda value: value["candidates"][0].__setitem__(
            "distance_value", "-1.000000000000000000"
        ),
        lambda value: value["query"].__setitem__("forecast_disposition", "forged"),
    ],
)
def test_record_rejects_claim_count_effective_n_and_distance_forgery(mutation) -> None:
    record, *_ = _record()
    mutation(record)
    _rehash(record, field="episodic_retrieval_record_id", prefix="mmepisodicretrieval_")
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError):
        retrieval.validate_episodic_retrieval_record(record)


def test_record_rejects_rehashed_rank_and_missingness_forgery() -> None:
    record, *_ = _record()
    ranked = sorted(
        (row for row in record["candidates"] if row["distance_rank"] is not None),
        key=lambda row: row["distance_rank"],
    )
    ranked[0]["distance_rank"], ranked[1]["distance_rank"] = (
        ranked[1]["distance_rank"],
        ranked[0]["distance_rank"],
    )
    _rehash(record, field="episodic_retrieval_record_id", prefix="mmepisodicretrieval_")
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError, match="distance"):
        retrieval.validate_episodic_retrieval_record(record)

    missing, *_ = _record(
        candidate_days=(0,),
        candidate_coordinates=((None, "1.000000000000000000"),),
    )
    missing["candidates"][0].update(
        {
            "distance_value": "1.000000000000000000",
            "distance_rank": 1,
            "selection_rank": 1,
            "disposition": "selected",
            "reason": None,
        }
    )
    missing["selected_forecast_ids"] = [missing["candidates"][0]["forecast_id"]]
    missing["counts"].update(
        {
            "distance_eligible_candidates": 1,
            "selected_nonoverlapping_candidates": 1,
        }
    )
    _rehash(
        missing, field="episodic_retrieval_record_id", prefix="mmepisodicretrieval_"
    )
    with pytest.raises(
        retrieval.MarketMemoryRetrievalContractError, match="incomplete"
    ):
        retrieval.validate_episodic_retrieval_record(missing)


def test_strict_loaders_reject_duplicates_nonfinite_and_oversize() -> None:
    record, registration, trial, query, candidates = _record()
    body = forward.canonical_json_bytes(record)
    assert (
        retrieval.load_episodic_retrieval_record_join_json(
            body,
            retrieval_registration=registration,
            trial_registration=trial,
            query_state_snapshot=query["state_snapshot"],
            query_forecast_record=query["forecast_record"],
            query_exact_context_bytes=query["exact_context_bytes"],
            query_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
            candidate_inputs=candidates,
        )
        == record
    )

    registration_body = forward.canonical_json_bytes(registration)
    assert (
        retrieval.load_retrieval_registration_join_json(
            registration_body, trial_registration=trial
        )
        == registration
    )
    duplicate_registration = registration_body.replace(
        b'{"authority":', b'{"authority":{},"authority":', 1
    )
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError, match="duplicate"):
        retrieval.load_retrieval_registration_join_json(
            duplicate_registration, trial_registration=trial
        )
    with pytest.raises(
        retrieval.MarketMemoryRetrievalContractError, match="byte bound"
    ):
        retrieval.load_retrieval_registration_join_json(
            b"{" + b" " * (256 * 1024), trial_registration=trial
        )
    with pytest.raises(
        retrieval.MarketMemoryRetrievalContractError, match="non-finite"
    ):
        retrieval.load_retrieval_registration_join_json(
            b'{"value":NaN}', trial_registration=trial
        )
    with pytest.raises(
        retrieval.MarketMemoryRetrievalContractError, match="strict JSON"
    ):
        retrieval.load_retrieval_registration_join_json(
            b'{"value":' + b"9" * 5000 + b"}", trial_registration=trial
        )
    duplicate = body.replace(b'{"authority":', b'{"authority":{},"authority":', 1)
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError, match="duplicate"):
        retrieval.load_episodic_retrieval_record_join_json(
            duplicate,
            retrieval_registration=registration,
            trial_registration=trial,
            query_state_snapshot=query["state_snapshot"],
            query_forecast_record=query["forecast_record"],
            query_exact_context_bytes=query["exact_context_bytes"],
            query_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
            candidate_inputs=candidates,
        )
    with pytest.raises(
        retrieval.MarketMemoryRetrievalContractError, match="byte bound"
    ):
        retrieval.load_episodic_retrieval_record_join_json(
            b"{" + b" " * (2 * 1024 * 1024),
            retrieval_registration=registration,
            trial_registration=trial,
            query_state_snapshot=query["state_snapshot"],
            query_forecast_record=query["forecast_record"],
            query_exact_context_bytes=query["exact_context_bytes"],
            query_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
            candidate_inputs=candidates,
        )


def test_candidate_and_aggregate_context_resource_bounds_precede_deep_validation() -> (
    None
):
    trial = _trial()
    registration = _registration(trial)
    query = _episode(20, trial=trial)
    common = {
        "retrieval_registration": registration,
        "trial_registration": trial,
        "query_state_snapshot": query["state_snapshot"],
        "query_forecast_record": query["forecast_record"],
        "query_exact_context_bytes": query["exact_context_bytes"],
        "query_coordinates": {
            "alpha": "0.000000000000000000",
            "beta": "0.000000000000000000",
        },
        "retrieved_at": "2026-08-28T00:00:00.000000Z",
    }
    with pytest.raises(
        retrieval.MarketMemoryRetrievalContractError, match="at most 128"
    ):
        retrieval.build_episodic_retrieval_record(
            **common,
            candidate_inputs=[{}] * 129,
        )
    oversized = {
        "state_snapshot": {},
        "forecast_record": {},
        "exact_context_bytes": b"x" * (16 * 1024 * 1024),
        "coordinates": {},
    }
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError, match="16 MiB"):
        retrieval.build_episodic_retrieval_record(
            **common,
            candidate_inputs=[oversized],
        )


def test_direct_coordinate_entry_rejects_oversized_q18_before_decimal_work() -> None:
    registration = _registration(_trial())
    oversized = "9" * 5000 + "." + "0" * 18
    with pytest.raises(
        retrieval.MarketMemoryRetrievalContractError, match="lexical bound"
    ):
        retrieval.score_normalized_euclidean(
            retrieval_registration=registration,
            query_coordinates={
                "alpha": oversized,
                "beta": "0.000000000000000000",
            },
            candidate_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
        )


def test_supplied_candidate_shape_forbids_outcomes_scores_and_distance_inputs() -> None:
    record, registration, trial, query, candidates = _record()
    assert record
    poisoned = copy.deepcopy(candidates)
    poisoned[0]["outcome_record"] = {}
    with pytest.raises(retrieval.MarketMemoryRetrievalContractError, match="fields"):
        retrieval.build_episodic_retrieval_record(
            retrieval_registration=registration,
            trial_registration=trial,
            query_state_snapshot=query["state_snapshot"],
            query_forecast_record=query["forecast_record"],
            query_exact_context_bytes=query["exact_context_bytes"],
            query_coordinates={
                "alpha": "0.000000000000000000",
                "beta": "0.000000000000000000",
            },
            candidate_inputs=poisoned,
            retrieved_at="2026-08-28T00:00:00.000000Z",
        )


def test_module_is_pure_and_has_no_runtime_plane() -> None:
    source = inspect.getsource(retrieval)
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not imported.intersection(
        {
            "os",
            "pathlib",
            "requests",
            "httpx",
            "socket",
            "subprocess",
            "sqlite3",
            "time",
        }
    )
    assert "datetime.now" not in source
    assert "datetime.utcnow" not in source
    assert not any(
        name in retrieval.__dict__
        for name in (
            "main",
            "serve",
            "write",
            "append",
            "discover_candidates",
            "fit_normalization",
        )
    )


def test_schema_rejects_promoted_claim_and_extra_population_language() -> None:
    record, *_ = _record()
    promoted = copy.deepcopy(record)
    promoted["claims"]["candidate_population_complete"] = True
    with pytest.raises(ValidationError):
        _validate_schema("episodic_retrieval_record.v1.schema.json", promoted)
    extra = copy.deepcopy(record)
    extra["global_nearest"] = True
    with pytest.raises(ValidationError):
        _validate_schema("episodic_retrieval_record.v1.schema.json", extra)
