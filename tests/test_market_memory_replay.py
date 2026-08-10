"""W1B.4A uncertainty/session/plan contracts stop before replay materialization."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from engine.neuralweb import market_memory_replay as replay

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "market_memory"
SOURCE_ARTIFACT = b"reviewed NYSE schedule fixture 2026\n"
CALENDAR_ID = "mmcalendar_" + "c" * 64


def _source_event_ref() -> dict[str, Any]:
    return {
        "owner": "market_memory",
        "source_schema": "market_memory.public_event.v1",
        "event_id": "public-event-2026-08-07",
        "event_date_field": "event_date",
        "predecision_event_sha256": "a" * 64,
        "source_contract_sha256": "b" * 64,
        "reference_basis": "caller_attested_predecision_projection",
        "predecision_event_bytes_verified": False,
        "source_contract_semantics_authenticated": False,
        "replay_scope_authenticated_by_source": False,
    }


def _source_evidence(
    body: bytes = SOURCE_ARTIFACT, *, schedule_version: str = "nyse.schedule.2026.v1"
) -> dict[str, Any]:
    return {
        "source": "NYSE",
        "source_url": "https://www.nyse.com/markets/hours-calendars",
        "schedule_version": schedule_version,
        "reviewed_at": "2026-08-10T12:00:00.000000Z",
        "artifact_sha256": hashlib.sha256(body).hexdigest(),
        "artifact_bytes": len(body),
        "source_authentication": "exact_source_bytes_sha256_verified",
        "schedule_basis": "reviewed_exchange_schedule",
        "actual_market_activity_authenticated": False,
    }


def _window(
    state: str = "regular_session",
    *,
    day: str | None = None,
    body: bytes = SOURCE_ARTIFACT,
    opened: str | None = None,
    closed: str | None = None,
    schedule_version: str = "nyse.schedule.2026.v1",
) -> dict[str, Any]:
    defaults: dict[str, tuple[str, str | None, str | None]] = {
        "regular_session": (
            "2026-08-07",
            "2026-08-07T13:30:00.000000Z",
            "2026-08-07T20:00:00.000000Z",
        ),
        "early_close": (
            "2026-11-27",
            "2026-11-27T14:30:00.000000Z",
            "2026-11-27T18:00:00.000000Z",
        ),
        "non_session": ("2026-08-08", None, None),
        "unresolved": ("2026-08-07", None, None),
    }
    default_day, default_opened, default_closed = defaults[state]
    return replay.build_market_session_window(
        calendar_id=CALENDAR_ID,
        session_date=day or default_day,
        session_state=state,  # type: ignore[arg-type]
        session_open=default_opened if opened is None else opened,
        session_close_exclusive=default_closed if closed is None else closed,
        source_evidence=_source_evidence(body, schedule_version=schedule_version),
        exact_source_artifact=body,
    )


def _uncertainty(
    *,
    day: str = "2026-08-07",
    precision: str = "date",
    scope: str = "civil_date",
    window: dict[str, Any] | None = None,
    body: bytes = SOURCE_ARTIFACT,
) -> dict[str, Any]:
    return replay.build_event_time_uncertainty(
        source_event_ref=_source_event_ref(),
        event_date=day,
        event_time_precision=precision,  # type: ignore[arg-type]
        replay_scope=scope,  # type: ignore[arg-type]
        market_session_window=window,
        exact_source_artifact=body if window is not None else None,
        expected_window_id=window["window_id"] if window is not None else None,
    )


def _plan(
    uncertainty: dict[str, Any],
    *,
    window: dict[str, Any] | None = None,
    body: bytes = SOURCE_ARTIFACT,
) -> dict[str, Any]:
    return replay.build_sensitivity_replay_plan(
        uncertainty,
        market_session_window=window,
        exact_source_artifact=body if window is not None else None,
        expected_window_id=window["window_id"] if window is not None else None,
    )


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _rehash(value: dict[str, Any], *, id_field: str, prefix: str) -> None:
    core = copy.deepcopy(value)
    core[id_field] = ""
    value[id_field] = prefix + hashlib.sha256(_canonical(core)).hexdigest()


def _schemas() -> dict[str, dict[str, Any]]:
    return {
        name: json.loads((SCHEMA_DIR / name).read_text())
        for name in (
            "event_time_uncertainty.v1.schema.json",
            "market_session_window.v1.schema.json",
            "sensitivity_replay_plan.v1.schema.json",
        )
    }


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


def _assert_contract_error(callable_: Any, *args: Any, **kwargs: Any) -> None:
    with pytest.raises(replay.MarketMemoryReplayContractError):
        callable_(*args, **kwargs)


def test_schemas_are_draft_2020_12_strict_and_validate_golden_objects() -> None:
    schemas = _schemas()
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
        assert schema["minProperties"] == schema["maxProperties"]

    assert schemas["event_time_uncertainty.v1.schema.json"]["minProperties"] == 16
    assert schemas["market_session_window.v1.schema.json"]["minProperties"] == 14
    assert schemas["sensitivity_replay_plan.v1.schema.json"]["minProperties"] == 11

    window = _window()
    uncertainty = _uncertainty(scope="market_session", window=window)
    plan = _plan(uncertainty, window=window)
    validators = _validators()
    validators["market_session_window.v1.schema.json"].validate(window)
    validators["market_session_window.v1.schema.json"].validate(_window("unresolved"))
    validators["event_time_uncertainty.v1.schema.json"].validate(uncertainty)
    validators["sensitivity_replay_plan.v1.schema.json"].validate(plan)
    validators["sensitivity_replay_plan.v1.schema.json"].validate(_plan(_uncertainty()))
    non_session_window = _window("non_session")
    validators["sensitivity_replay_plan.v1.schema.json"].validate(
        _plan(
            _uncertainty(
                day="2026-08-08",
                scope="market_session",
                window=non_session_window,
            ),
            window=non_session_window,
        )
    )

    for artifact in (window, uncertainty, plan):
        assert artifact["authority"] == dict(replay.AUTHORITY)
        assert artifact["authority"]["proposal_weight"] == 0
        assert artifact["authority"]["may_append_outcome"] is False
    source_ref = uncertainty["source_event_ref"]
    assert source_ref["reference_basis"] == ("caller_attested_predecision_projection")
    assert source_ref["predecision_event_bytes_verified"] is False
    assert source_ref["source_contract_semantics_authenticated"] is False
    assert source_ref["replay_scope_authenticated_by_source"] is False


def test_schema_rejects_contradictory_receipt_state_and_hostile_extensions() -> None:
    validators = _validators()
    unbound = _uncertainty(scope="market_session")
    contradictory = copy.deepcopy(unbound)
    contradictory["market_session_window_id"] = "mmsessionwindow_" + "1" * 64
    with pytest.raises(ValidationError):
        validators["event_time_uncertainty.v1.schema.json"].validate(contradictory)

    forged_provenance = copy.deepcopy(unbound)
    forged_provenance["source_event_ref"]["predecision_event_bytes_verified"] = True
    with pytest.raises(ValidationError):
        validators["event_time_uncertainty.v1.schema.json"].validate(forged_provenance)

    window = _window("non_session")
    non_session = _uncertainty(day="2026-08-08", scope="market_session", window=window)
    contradictory = copy.deepcopy(non_session)
    contradictory["market_session_window_id"] = None
    with pytest.raises(ValidationError):
        validators["event_time_uncertainty.v1.schema.json"].validate(contradictory)

    regular = _window()
    plan = _plan(_uncertainty(scope="market_session", window=regular), window=regular)
    plan["scenarios"][0]["context_id"] = "forbidden"
    with pytest.raises(ValidationError):
        validators["sensitivity_replay_plan.v1.schema.json"].validate(plan)


def test_ids_are_deterministic_permutation_stable_and_values_are_detached() -> None:
    evidence = _source_evidence()
    event_ref = _source_event_ref()
    first_window = _window()
    second_window = replay.build_market_session_window(
        calendar_id=CALENDAR_ID,
        session_date="2026-08-07",
        session_state="regular_session",
        session_open="2026-08-07T13:30:00.000000Z",
        session_close_exclusive="2026-08-07T20:00:00.000000Z",
        source_evidence=dict(reversed(list(evidence.items()))),
        exact_source_artifact=SOURCE_ARTIFACT,
    )
    assert first_window == second_window

    first = replay.build_event_time_uncertainty(
        source_event_ref=event_ref,
        event_date="2026-08-07",
        event_time_precision="date",
        replay_scope="market_session",
        market_session_window=first_window,
        exact_source_artifact=SOURCE_ARTIFACT,
        expected_window_id=first_window["window_id"],
    )
    second = replay.build_event_time_uncertainty(
        source_event_ref=dict(reversed(list(event_ref.items()))),
        event_date="2026-08-07",
        event_time_precision="date",
        replay_scope="market_session",
        market_session_window=second_window,
        exact_source_artifact=SOURCE_ARTIFACT,
        expected_window_id=second_window["window_id"],
    )
    assert first == second
    assert _plan(first, window=first_window) == _plan(second, window=second_window)

    validated = replay.validate_event_time_uncertainty(
        first,
        market_session_window=first_window,
        exact_source_artifact=SOURCE_ARTIFACT,
        expected_window_id=first_window["window_id"],
    )
    assert validated is not first
    assert validated["source_event_ref"] is not first["source_event_ref"]
    event_ref["event_id"] = "changed-after-build"
    evidence["schedule_version"] = "changed.after.build"
    assert first["source_event_ref"]["event_id"] == "public-event-2026-08-07"
    assert first_window["source_evidence"]["schedule_version"] == (
        "nyse.schedule.2026.v1"
    )


@pytest.mark.parametrize(
    ("day", "lower", "upper", "hours"),
    [
        (
            "2026-02-03",
            "2026-02-03T05:00:00.000000Z",
            "2026-02-04T05:00:00.000000Z",
            24,
        ),
        (
            "2026-07-03",
            "2026-07-03T04:00:00.000000Z",
            "2026-07-04T04:00:00.000000Z",
            24,
        ),
        (
            "2026-03-08",
            "2026-03-08T05:00:00.000000Z",
            "2026-03-09T04:00:00.000000Z",
            23,
        ),
        (
            "2026-11-01",
            "2026-11-01T04:00:00.000000Z",
            "2026-11-02T05:00:00.000000Z",
            25,
        ),
    ],
)
def test_date_precision_retains_the_whole_new_york_civil_day(
    day: str, lower: str, upper: str, hours: int
) -> None:
    uncertainty = _uncertainty(day=day)
    assert uncertainty["event_time_lower_bound"] == lower
    assert uncertainty["event_time_upper_bound"] == upper
    lower_us = int(
        datetime.fromisoformat(lower.replace("Z", "+00:00")).timestamp() * 1_000_000
    )
    upper_us = int(
        datetime.fromisoformat(upper.replace("Z", "+00:00")).timestamp() * 1_000_000
    )
    assert upper_us - lower_us == hours * 60 * 60 * 1_000_000
    plan = _plan(uncertainty)
    assert plan["plan_status"] == "abstained"
    assert plan["abstention_reason"] == "civil_date_scope"
    assert plan["scenarios"] == []


def test_exact_fail_closed_date_session_mapping() -> None:
    missing = _uncertainty(scope="market_session")
    assert missing["sensitivity_coverage"] == "none_session_window_unresolved"
    assert _plan(missing)["abstention_reason"] == "session_window_unresolved"

    for state, day, coverage, reason in (
        ("non_session", "2026-08-08", "none_non_session", "non_session"),
    ):
        window = _window(state)
        uncertainty = _uncertainty(day=day, scope="market_session", window=window)
        assert uncertainty["sensitivity_coverage"] == coverage
        assert uncertainty["event_time_lower_bound"].endswith("04:00:00.000000Z")
        plan = _plan(uncertainty, window=window)
        assert plan["abstention_reason"] == reason
        assert plan["scenarios"] == []

    unresolved = _window("unresolved")
    _assert_contract_error(
        replay.build_event_time_uncertainty,
        source_event_ref=_source_event_ref(),
        event_date="2026-08-07",
        event_time_precision="date",
        replay_scope="market_session",
        market_session_window=unresolved,
        exact_source_artifact=SOURCE_ARTIFACT,
        expected_window_id=unresolved["window_id"],
    )

    for state, day in (
        ("regular_session", "2026-08-07"),
        ("early_close", "2026-11-27"),
    ):
        window = _window(state)
        uncertainty = _uncertainty(day=day, scope="market_session", window=window)
        assert uncertainty["sensitivity_coverage"] == "partial_session_sensitivity"
        assert uncertainty["event_time_lower_bound"] != window["session_open"]
        assert _plan(uncertainty, window=window)["plan_status"] == "unmaterialized"

    _assert_contract_error(
        replay.build_event_time_uncertainty,
        source_event_ref=_source_event_ref(),
        event_date="2026-08-07",
        event_time_precision="session",
        replay_scope="civil_date",
    )
    _assert_contract_error(
        replay.build_event_time_uncertainty,
        source_event_ref=_source_event_ref(),
        event_date="2026-08-07",
        event_time_precision="session",
        replay_scope="market_session",
    )
    non_session = _window("non_session")
    _assert_contract_error(
        replay.build_event_time_uncertainty,
        source_event_ref=_source_event_ref(),
        event_date="2026-08-08",
        event_time_precision="session",
        replay_scope="market_session",
        market_session_window=non_session,
        exact_source_artifact=SOURCE_ARTIFACT,
        expected_window_id=non_session["window_id"],
    )


def test_session_precision_is_exactly_bound_to_the_admitted_window() -> None:
    for state in ("regular_session", "early_close"):
        window = _window(state)
        uncertainty = _uncertainty(
            day=window["session_date"],
            precision="session",
            scope="market_session",
            window=window,
        )
        assert uncertainty["event_time_lower_bound"] == window["session_open"]
        assert (
            uncertainty["event_time_upper_bound"] == window["session_close_exclusive"]
        )
        assert uncertainty["sensitivity_coverage"] == "session_samples_only"

        forged = copy.deepcopy(uncertainty)
        forged["event_time_lower_bound"] = (
            "2026-08-07T14:00:00.000000Z"
            if state == "regular_session"
            else "2026-11-27T15:00:00.000000Z"
        )
        _rehash(forged, id_field="uncertainty_id", prefix="mmuncertainty_")
        _assert_contract_error(
            replay.validate_event_time_uncertainty,
            forged,
            market_session_window=window,
            exact_source_artifact=SOURCE_ARTIFACT,
            expected_window_id=window["window_id"],
        )


def test_window_and_plan_require_an_out_of_band_trusted_window_id() -> None:
    window = _window()
    _assert_contract_error(
        replay.build_event_time_uncertainty,
        source_event_ref=_source_event_ref(),
        event_date="2026-08-07",
        event_time_precision="date",
        replay_scope="market_session",
        market_session_window=window,
        exact_source_artifact=SOURCE_ARTIFACT,
    )

    trusted_uncertainty = _uncertainty(scope="market_session", window=window)
    _assert_contract_error(
        replay.build_sensitivity_replay_plan,
        trusted_uncertainty,
        market_session_window=window,
        exact_source_artifact=SOURCE_ARTIFACT,
    )
    _assert_contract_error(
        replay.validate_event_time_uncertainty,
        trusted_uncertainty,
        market_session_window=window,
        exact_source_artifact=SOURCE_ARTIFACT,
    )
    _assert_contract_error(
        replay.validate_market_session_window,
        window,
        exact_source_artifact=SOURCE_ARTIFACT,
        expected_window_id="mmsessionwindow_" + "f" * 64,
    )
    with pytest.raises(TypeError):
        replay.validate_market_session_window(
            window, exact_source_artifact=SOURCE_ARTIFACT
        )

    attacker_body = b"attacker-selected schedule bytes"
    attacker_window = _window(
        body=attacker_body, schedule_version="untrusted.schedule.v1"
    )
    _assert_contract_error(
        replay.build_event_time_uncertainty,
        source_event_ref=_source_event_ref(),
        event_date="2026-08-07",
        event_time_precision="date",
        replay_scope="market_session",
        market_session_window=attacker_window,
        exact_source_artifact=attacker_body,
        expected_window_id=window["window_id"],
    )


def test_bound_json_loaders_require_and_forward_source_proof() -> None:
    window = _window()
    uncertainty = _uncertainty(scope="market_session", window=window)
    plan = _plan(uncertainty, window=window)
    _assert_contract_error(
        replay.load_event_time_uncertainty_json, _canonical(uncertainty)
    )
    assert (
        replay.load_event_time_uncertainty_json(
            _canonical(uncertainty),
            market_session_window=window,
            exact_source_artifact=SOURCE_ARTIFACT,
            expected_window_id=window["window_id"],
        )
        == uncertainty
    )
    assert (
        replay.load_market_session_window_json(
            _canonical(window),
            exact_source_artifact=SOURCE_ARTIFACT,
            expected_window_id=window["window_id"],
        )
        == window
    )
    with pytest.raises(TypeError):
        replay.load_market_session_window_json(
            _canonical(window), exact_source_artifact=SOURCE_ARTIFACT
        )
    _assert_contract_error(
        replay.load_market_session_window_json,
        _canonical(window),
        exact_source_artifact=SOURCE_ARTIFACT,
        expected_window_id="mmsessionwindow_" + "f" * 64,
    )
    assert (
        replay.load_sensitivity_replay_plan_json(
            _canonical(plan),
            exact_source_artifact=SOURCE_ARTIFACT,
            expected_window_id=window["window_id"],
        )
        == plan
    )
    _assert_contract_error(
        replay.load_sensitivity_replay_plan_json,
        _canonical(plan),
        exact_source_artifact=SOURCE_ARTIFACT,
    )


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            "regular_session",
            [
                "2026-08-07T13:30:00.000000Z",
                "2026-08-07T16:45:00.000000Z",
                "2026-08-07T19:59:59.999999Z",
            ],
        ),
        (
            "early_close",
            [
                "2026-11-27T14:30:00.000000Z",
                "2026-11-27T16:15:00.000000Z",
                "2026-11-27T17:59:59.999999Z",
            ],
        ),
    ],
)
def test_open_actual_midpoint_and_close_minus_one_microsecond_geometry(
    state: str, expected: list[str]
) -> None:
    window = _window(state)
    uncertainty = _uncertainty(
        day=window["session_date"], scope="market_session", window=window
    )
    plan = _plan(uncertainty, window=window)
    assert [row["ordinal"] for row in plan["scenarios"]] == [0, 1, 2]
    assert [row["cutoff_scenario"] for row in plan["scenarios"]] == [
        "session_open",
        "mid_session",
        "session_close",
    ]
    assert [row["assumed_event_time"] for row in plan["scenarios"]] == expected
    assert [row["as_known_at"] for row in plan["scenarios"]] == expected
    assert {row["materialization_status"] for row in plan["scenarios"]} == {
        "unmaterialized"
    }
    assert {row["assumed_time_role"] for row in plan["scenarios"]} == {
        "sensitivity_only_not_observed_event_time"
    }


@pytest.mark.parametrize(
    ("state", "opened", "closed"),
    [
        (
            "regular_session",
            "2026-08-07T14:00:00.000000Z",
            "2026-08-07T20:00:00.000000Z",
        ),
        (
            "regular_session",
            "2026-08-07T13:30:00.000000Z",
            "2026-08-07T17:00:00.000000Z",
        ),
        ("early_close", "2026-11-27T14:30:00.000000Z", "2026-11-27T21:00:00.000000Z"),
        (
            "regular_session",
            "2026-08-08T13:30:00.000000Z",
            "2026-08-08T20:00:00.000000Z",
        ),
        (
            "regular_session",
            "2026-08-07T20:00:00.000000Z",
            "2026-08-07T13:30:00.000000Z",
        ),
    ],
)
def test_session_window_rejects_arbitrary_or_state_inconsistent_geometry(
    state: str, opened: str, closed: str
) -> None:
    _assert_contract_error(
        replay.build_market_session_window,
        calendar_id=CALENDAR_ID,
        session_date="2026-08-07" if state == "regular_session" else "2026-11-27",
        session_state=state,
        session_open=opened,
        session_close_exclusive=closed,
        source_evidence=_source_evidence(),
        exact_source_artifact=SOURCE_ARTIFACT,
    )


def test_window_rejects_clock_nullability_source_drift_and_stale_ids() -> None:
    for state in ("non_session", "unresolved"):
        _assert_contract_error(
            replay.build_market_session_window,
            calendar_id=CALENDAR_ID,
            session_date="2026-08-08",
            session_state=state,
            session_open="2026-08-08T13:30:00.000000Z",
            session_close_exclusive="2026-08-08T20:00:00.000000Z",
            source_evidence=_source_evidence(),
            exact_source_artifact=SOURCE_ARTIFACT,
        )
    _assert_contract_error(
        replay.build_market_session_window,
        calendar_id=CALENDAR_ID,
        session_date="2026-08-07",
        session_state="regular_session",
        session_open=None,
        session_close_exclusive=None,
        source_evidence=_source_evidence(),
        exact_source_artifact=SOURCE_ARTIFACT,
    )
    window = _window()
    stale = copy.deepcopy(window)
    stale["source_evidence"]["schedule_version"] = "nyse.schedule.2026.v2"
    _assert_contract_error(
        replay.validate_market_session_window,
        stale,
        exact_source_artifact=SOURCE_ARTIFACT,
        expected_window_id=window["window_id"],
    )
    _assert_contract_error(
        replay.validate_market_session_window,
        window,
        exact_source_artifact=b"wrong exact bytes",
        expected_window_id=window["window_id"],
    )
    wrong_count = _source_evidence()
    wrong_count["artifact_bytes"] += 1
    _assert_contract_error(
        replay.build_market_session_window,
        calendar_id=CALENDAR_ID,
        session_date="2026-08-07",
        session_state="regular_session",
        session_open="2026-08-07T13:30:00.000000Z",
        session_close_exclusive="2026-08-07T20:00:00.000000Z",
        source_evidence=wrong_count,
        exact_source_artifact=SOURCE_ARTIFACT,
    )


def test_window_and_uncertainty_dates_are_cross_bound() -> None:
    window = _window()
    _assert_contract_error(
        replay.build_event_time_uncertainty,
        source_event_ref=_source_event_ref(),
        event_date="2026-08-06",
        event_time_precision="date",
        replay_scope="market_session",
        market_session_window=window,
        exact_source_artifact=SOURCE_ARTIFACT,
        expected_window_id=window["window_id"],
    )


def test_hostile_scenario_mutants_and_authority_promotion_fail_closed() -> None:
    window = _window()
    uncertainty = _uncertainty(scope="market_session", window=window)
    plan = _plan(uncertainty, window=window)
    mutations = []

    reordered = copy.deepcopy(plan)
    reordered["scenarios"].reverse()
    mutations.append(reordered)
    duplicate = copy.deepcopy(plan)
    duplicate["scenarios"][1] = copy.deepcopy(duplicate["scenarios"][0])
    mutations.append(duplicate)
    changed = copy.deepcopy(plan)
    changed["scenarios"][1]["assumed_event_time"] = "2026-08-07T17:00:00.000000Z"
    mutations.append(changed)
    fewer = copy.deepcopy(plan)
    fewer["scenarios"].pop()
    mutations.append(fewer)
    extra_field = copy.deepcopy(plan)
    extra_field["scenarios"][0]["context_id"] = "forbidden"
    mutations.append(extra_field)
    bool_ordinal = copy.deepcopy(plan)
    bool_ordinal["scenarios"][0]["ordinal"] = False
    mutations.append(bool_ordinal)
    promoted = copy.deepcopy(plan)
    promoted["authority"]["may_rank"] = True
    mutations.append(promoted)
    weighted = copy.deepcopy(plan)
    weighted["claim_policy"]["weight"] = 0.5
    mutations.append(weighted)

    for mutant in mutations:
        _assert_contract_error(
            replay.validate_sensitivity_replay_plan,
            mutant,
            exact_source_artifact=SOURCE_ARTIFACT,
            expected_window_id=window["window_id"],
        )

    self_hashed = copy.deepcopy(plan)
    self_hashed["scenarios"][1]["as_known_at"] = "2026-08-07T17:00:00.000000Z"
    _rehash(self_hashed, id_field="plan_id", prefix="mmsensitivityplan_")
    _assert_contract_error(
        replay.validate_sensitivity_replay_plan,
        self_hashed,
        exact_source_artifact=SOURCE_ARTIFACT,
        expected_window_id=window["window_id"],
    )


@pytest.mark.parametrize(
    "hostile",
    [
        "label",
        "Outcome",
        "futureReturn",
        "direction",
        "bullish",
        "bearish",
        "bull",
        "bear",
        "long",
        "short",
        "PnL",
        "P/L",
        "realizedPnL",
        "premiumOutcome",
        "HPlus60",
        "h_60",
        "exitPrice",
        "closeDate",
        "Profit-And-Loss",
    ],
)
def test_recursive_predecision_guard_rejects_hostile_opaque_text(
    hostile: str,
) -> None:
    event_ref = _source_event_ref()
    event_ref["event_id"] = f"event-{hostile}"
    _assert_contract_error(
        replay.build_event_time_uncertainty,
        source_event_ref=event_ref,
        event_date="2026-08-07",
        event_time_precision="date",
        replay_scope="civil_date",
    )
    _assert_contract_error(
        replay.build_market_session_window,
        calendar_id=CALENDAR_ID,
        session_date="2026-08-07",
        session_state="regular_session",
        session_open="2026-08-07T13:30:00.000000Z",
        session_close_exclusive="2026-08-07T20:00:00.000000Z",
        source_evidence=_source_evidence(schedule_version=f"nyse.{hostile}"),
        exact_source_artifact=SOURCE_ARTIFACT,
    )


def test_required_structural_close_and_outcome_authority_keys_are_narrowly_allowed() -> (
    None
):
    window = _window()
    plan = _plan(_uncertainty(scope="market_session", window=window), window=window)
    assert plan["scenarios"][2]["cutoff_scenario"] == "session_close"
    assert plan["authority"]["may_append_outcome"] is False
    assert (
        replay.validate_sensitivity_replay_plan(
            plan,
            exact_source_artifact=SOURCE_ARTIFACT,
            expected_window_id=window["window_id"],
        )
        == plan
    )


@pytest.mark.parametrize(
    "bad_timestamp",
    [
        "2026-08-07T13:30:00Z",
        "2026-08-07T09:30:00.000000-04:00",
        "2026-08-07T13:30:00.000000Z ",
        "2026-02-30T13:30:00.000000Z",
    ],
)
def test_timestamps_are_exact_microsecond_utc(bad_timestamp: str) -> None:
    _assert_contract_error(
        replay.build_market_session_window,
        calendar_id=CALENDAR_ID,
        session_date="2026-08-07",
        session_state="regular_session",
        session_open=bad_timestamp,
        session_close_exclusive="2026-08-07T20:00:00.000000Z",
        source_evidence=_source_evidence(),
        exact_source_artifact=SOURCE_ARTIFACT,
    )


def test_timezone_aliases_dates_and_json_scalar_types_are_strict() -> None:
    _assert_contract_error(
        replay.build_event_time_uncertainty,
        source_event_ref=_source_event_ref(),
        event_date="2026-08-07",
        event_time_precision="date",
        replay_scope="civil_date",
        source_timezone="US/Eastern",
    )
    for bad_date in ("2026-2-03", "2026-02-30", "1969-12-31", True):
        _assert_contract_error(
            replay.build_event_time_uncertainty,
            source_event_ref=_source_event_ref(),
            event_date=bad_date,
            event_time_precision="date",
            replay_scope="civil_date",
        )
    evidence = _source_evidence()
    evidence["artifact_bytes"] = False
    _assert_contract_error(
        replay.build_market_session_window,
        calendar_id=CALENDAR_ID,
        session_date="2026-08-07",
        session_state="regular_session",
        session_open="2026-08-07T13:30:00.000000Z",
        session_close_exclusive="2026-08-07T20:00:00.000000Z",
        source_evidence=evidence,
        exact_source_artifact=SOURCE_ARTIFACT,
    )


def test_strict_json_loader_rejects_duplicate_nonfinite_invalid_and_oversized_input() -> (
    None
):
    uncertainty = _uncertainty()
    body = _canonical(uncertainty)
    needle = b'"event_id":"public-event-2026-08-07"'
    duplicate = body.replace(
        needle,
        needle + b',"event_id":"public-event-2026-08-08"',
    )
    assert duplicate != body
    invalid_bodies = (
        duplicate,
        b"\xef\xbb\xbf" + body,
        body + b" trailing",
        b"[]",
        b'{"value":NaN}',
        b"\xff",
        b'{"value":"' + b"a" * (64 * 1024) + b'"}',
        b'{"value":' + b"9" * 5_000 + b"}",
        b'{"value":' + b"[" * 2_000 + b"0" + b"]" * 2_000 + b"}",
    )
    for invalid in invalid_bodies:
        _assert_contract_error(replay.load_event_time_uncertainty_json, invalid)


def test_mapping_shape_cycle_depth_node_string_and_unicode_bounds_fail_closed() -> None:
    malicious_values: list[Any] = []
    cycle: dict[str, Any] = {}
    cycle["self"] = cycle
    malicious_values.append(cycle)
    depth: Any = "leaf"
    for _ in range(20):
        depth = [depth]
    malicious_values.extend(
        [depth, ["node"] * 300, "x" * 4_097, float("nan"), "bad\ud800", "bad\n"]
    )
    for malicious in malicious_values:
        event_ref = _source_event_ref()
        event_ref["event_id"] = malicious
        _assert_contract_error(
            replay.build_event_time_uncertainty,
            source_event_ref=event_ref,
            event_date="2026-08-07",
            event_time_precision="date",
            replay_scope="civil_date",
        )


def test_safe_non_id_tampering_and_post_event_maturation_do_not_cross_layers() -> None:
    uncertainty = _uncertainty()
    stale = copy.deepcopy(uncertainty)
    stale["source_event_ref"]["event_id"] = "public-event-2026-08-08"
    _assert_contract_error(replay.validate_event_time_uncertainty, stale)

    predecision = _source_event_ref()
    first = replay.build_event_time_uncertainty(
        source_event_ref=predecision,
        event_date="2026-08-07",
        event_time_precision="date",
        replay_scope="civil_date",
    )
    external_episode = {"predecision": copy.deepcopy(predecision), "result": None}
    external_episode["result"] = {
        "matured": True,
        "future_return": 0.2,
        "exit_price": 150,
    }
    second = replay.build_event_time_uncertainty(
        source_event_ref=external_episode["predecision"],
        event_date="2026-08-07",
        event_time_precision="date",
        replay_scope="civil_date",
    )
    assert first == second


def test_public_api_is_frozen_and_module_is_pure_stdlib_contract_code() -> None:
    expected_parameters = {
        "build_market_session_window": [
            "calendar_id",
            "session_date",
            "session_state",
            "session_open",
            "session_close_exclusive",
            "source_evidence",
            "exact_source_artifact",
        ],
        "validate_market_session_window": [
            "value",
            "exact_source_artifact",
            "expected_window_id",
        ],
        "build_event_time_uncertainty": [
            "source_event_ref",
            "event_date",
            "event_time_precision",
            "replay_scope",
            "source_timezone",
            "market_session_window",
            "exact_source_artifact",
            "expected_window_id",
        ],
        "validate_event_time_uncertainty": [
            "value",
            "market_session_window",
            "exact_source_artifact",
            "expected_window_id",
        ],
        "build_sensitivity_replay_plan": [
            "uncertainty",
            "market_session_window",
            "exact_source_artifact",
            "expected_window_id",
        ],
        "validate_sensitivity_replay_plan": [
            "value",
            "exact_source_artifact",
            "expected_window_id",
        ],
    }
    for name, expected in expected_parameters.items():
        signature = inspect.signature(getattr(replay, name))
        assert list(signature.parameters) == expected
        assert all(
            parameter.kind not in {parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD}
            for parameter in signature.parameters.values()
        )

    path = ROOT / "engine" / "neuralweb" / "market_memory_replay.py"
    source = path.read_text()
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported_roots <= {
        "__future__",
        "collections",
        "copy",
        "datetime",
        "hashlib",
        "json",
        "math",
        "re",
        "types",
        "typing",
        "unicodedata",
        "zoneinfo",
    }
    forbidden_text = (
        "FileAsKnownAtReader",
        "TrustedFileAsKnownAtReader",
        "CompositeAsKnownAtReader",
        "market_memory_pit",
        "market_memory_trusted",
        "requests",
        "urllib",
        "socket",
    )
    assert not any(value in source for value in forbidden_text)
    forbidden_attributes = {"now", "today", "utcnow", "getenv", "environ"}
    assert (
        not {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        & forbidden_attributes
    )
