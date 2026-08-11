"""Hostile contracts for the bounded prospective W2C SPY experience owner."""

from __future__ import annotations

import ast
import copy
import json
import time as wall_time
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone, tzinfo
from email.utils import format_datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

from engine.neuralweb import market_memory as mm
from engine.neuralweb import market_memory_experience_accrual as accrual
from engine.neuralweb import market_memory_identity as identity
from engine.neuralweb import market_memory_projection as projection
from engine.neuralweb import market_memory_pit as pit
from engine.neuralweb import market_memory_technical_store as technical_store
from engine.neuralweb import market_memory_trusted as trusted
from lib import nyse_calendar
from tests.test_market_memory_technical_store import _bundle as technical_bundle
from tests.test_market_memory_technical_store import _frame as technical_frame
from tests import test_market_memory_technical_store as technical_test
from tests.test_market_memory_trusted import _raw_regime

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
ACTIVATION = date(2026, 8, 17)


class InjectedDurabilityCrash(BaseException):
    """Simulate process loss, which application exception handlers cannot catch."""


class HostileDateTime(datetime):
    """A datetime-shaped value whose inherited-method overrides must never run."""

    def astimezone(self, *_args, **_kwargs):  # pragma: no cover - must be rejected first
        raise AttributeError("hostile datetime astimezone override ran")

    def isoformat(self, *_args, **_kwargs):  # pragma: no cover - must be rejected first
        raise AttributeError("hostile datetime isoformat override ran")


class BrokenClockZone(tzinfo):
    """An exact datetime can still carry a timezone that fails normalization."""

    def utcoffset(self, _value):
        raise AttributeError("hostile timezone offset failed")

    def dst(self, _value):  # pragma: no cover - offset fails first
        return None


def _clock(value: str):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return lambda: parsed.astimezone(timezone.utc)


def _experience_root(tmp_path: Path) -> Path:
    return tmp_path / "market-memory" / "state" / "experience-v1"


def _technical_root(tmp_path: Path) -> Path:
    return tmp_path / "market-memory" / "state" / "technicals-v1"


def _trusted_roots(tmp_path: Path) -> tuple[Path, Path]:
    return (
        tmp_path / "market-memory" / "public" / "trusted-v1",
        tmp_path / "market-memory" / "state" / "context-projection",
    )


def _capture_technical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    session: date,
    observed_at: datetime,
    end_close: float,
) -> technical_store.StoredTechnicalActualOutput:
    frame = technical_frame(end=session)
    close_index = frame.columns.get_loc("close")
    open_index = frame.columns.get_loc("open")
    high_index = frame.columns.get_loc("high")
    low_index = frame.columns.get_loc("low")
    frame.iloc[-1, close_index] = end_close
    frame.iloc[-1, open_index] = end_close
    frame.iloc[-1, high_index] = end_close + 1.0
    frame.iloc[-1, low_index] = end_close - 1.0
    modified = format_datetime(
        (observed_at - timedelta(minutes=10)).astimezone(timezone.utc),
        usegmt=True,
    )
    original_manifest = technical_test._manifest

    def current_manifest(value):
        manifest = original_manifest(value)
        manifest["store"]["updated_at"] = (
            observed_at - timedelta(minutes=9)
        ).isoformat()
        return manifest

    monkeypatch.setattr(technical_test, "_manifest", current_manifest)
    bundle = technical_bundle(
        frame=frame,
        manifest_modified=modified,
        spy_modified=modified,
        pinned_commit=COMMIT,
    )
    monkeypatch.setattr(technical_store, "_utc_now", lambda: observed_at)
    return technical_store.capture_technical_actual_output(
        _technical_root(tmp_path), bundle=bundle
    )


def _capture_trusted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    session: date,
) -> None:
    raw = _raw_regime()
    session_text = session.isoformat()
    built = datetime.combine(
        session, datetime.min.time(), tzinfo=timezone.utc
    ) + timedelta(hours=23)
    raw["asof"] = session_text
    raw["date"] = session_text
    raw["freshness"]["asof"] = session_text
    raw["freshness"]["built_at"] = built.isoformat().replace("+00:00", "Z")
    source = tmp_path / "latest.json"
    body = (
        json.dumps(raw, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode()
    source.write_bytes(body)
    monkeypatch.setattr(projection, "_utc_now", lambda: built + timedelta(minutes=1))
    snapshot = projection.build_macro_regime_snapshot(source)
    monkeypatch.setattr(identity, "_utc_now", lambda: built + timedelta(minutes=2))
    identity_evidence = identity.build_current_spy_identity()
    monkeypatch.setattr(trusted, "_utc_now", lambda: built + timedelta(minutes=3))
    monkeypatch.setattr(pit, "_utc_now", lambda: built + timedelta(minutes=4))
    public, private = _trusted_roots(tmp_path)
    trusted.capture_trusted_regime_context(
        public,
        private,
        snapshot=snapshot,
        identity_evidence=identity_evidence,
        raw_source_body=body,
        deployed_commit=COMMIT,
    )


def _initialize_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    technical: bool = True,
) -> tuple[Path, Path, Path]:
    _capture_trusted(tmp_path, monkeypatch, session=ACTIVATION)
    if technical:
        _capture_technical(
            tmp_path,
            monkeypatch,
            session=ACTIVATION,
            observed_at=datetime(2026, 8, 18, 2, tzinfo=timezone.utc),
            end_close=120.0,
        )
    else:
        technical_store.initialize_technical_actual_output_store(
            _technical_root(tmp_path)
        )
    public, _private = _trusted_roots(tmp_path)
    return _experience_root(tmp_path), public, _technical_root(tmp_path)


def _run(
    tmp_path: Path,
    *,
    experience: Path,
    trusted_root: Path,
    technical_root: Path,
    clock: str,
) -> accrual.AccrualResult:
    return accrual.accrue_spy_experience(
        ROOT,
        experience_root=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        writer_commit=COMMIT,
        clock=_clock(clock),
    )


def _install(
    tmp_path: Path, *, experience: Path, trusted_root: Path, technical_root: Path
) -> None:
    result = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-11T20:00:00Z",
    )
    assert result.opportunity_ids == ()
    assert (experience / "registration_installation.json").is_file()


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def _rehash(value: dict, *, field: str, prefix: str) -> dict:
    changed = copy.deepcopy(value)
    changed[field] = ""
    changed[field] = accrual._content_id(prefix, changed, field=field)
    return changed


def _schema_registry() -> tuple[Registry, dict[str, dict]]:
    schemas: dict[str, dict] = {}
    registry = Registry()
    for path in sorted((ROOT / "contracts" / "market_memory").glob("spy_experience_*.schema.json")):
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry, schemas


def test_registration_is_content_addressed_bounded_and_calendar_derived() -> None:
    registration = accrual.load_registration(ROOT)
    spec = registration.value["spec"]
    sessions = nyse_calendar.sessions_between(
        accrual.ACTIVATION_SESSION, accrual.SUNSET_SESSION
    )
    assert len(sessions) == 126
    assert sessions[0] == date(2026, 8, 17)
    assert sessions[-1] == date(2027, 2, 16)
    assert nyse_calendar.session_n_forward(sessions[-1], 5) == date(2027, 2, 23)
    assert accrual.CORRECTION_SUNSET_SESSION == date(2027, 3, 2)
    assert accrual.TERMINAL_CENSUS_DATE == date(2027, 3, 3)
    assert [opened.date() for opened, _deadline in accrual._final_tail_observation_windows()] == [
        date(2027, 2, 25), date(2027, 2, 26), date(2027, 2, 27),
        date(2027, 3, 2), date(2027, 3, 3),
    ]
    assert accrual._inside_finite_correction_window(
        datetime(2026, 8, 25, 4, 35, tzinfo=timezone.utc),
        target_session=date(2026, 8, 24),
    )
    assert not accrual._inside_finite_correction_window(
        datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
        target_session=date(2026, 8, 24),
    )
    assert not accrual._inside_finite_correction_window(
        datetime(2027, 3, 4, 4, 35, tzinfo=timezone.utc),
        target_session=date(2026, 8, 24),
    )
    assert spec["calendar"]["expected_opportunity_rule"] == "first_126_xnys_sessions_on_or_after_activation.v1"
    assert spec["state_inputs"]["selection"] == "owner_observed_revision_chain.v1"
    assert spec["subject"]["mic"] == "ARCX"
    assert spec["calendar"]["market_session"] == "XNYS_REGULAR"
    assert spec["auditability"]["indefinite_v1_auditability"] is False
    assert spec["outcome"]["final_tail_xnys_sessions"] == 5
    assert spec["outcome"]["correction_observation_window_rule"] == (
        "daily_0430_0445z_from_target_maturity_window_through_terminal_date_inclusive"
    )
    assert spec["outcome"]["terminal_census_window_opens_at"] == "2027-03-03T04:30:00Z"
    assert spec["claims"]["external_clock_authenticated"] is False
    assert spec["claims"]["aba_resistance_authenticated"] is False
    assert spec["cutoff"]["head_observation_model"] == (
        "same_authenticated_head_before_and_after_local_sample_under_"
        "monotone_append_only_owner_protocol"
    )
    assert spec["cutoff"]["aba_adversary_model"] == (
        "transient_a_to_b_to_a_between_reads_not_detectable_v1"
    )
    distance = spec["decision_state_projection"]["distance_arithmetic"]
    assert distance == {
        "decimal_context_precision": 64,
        "rounding": "ROUND_HALF_EVEN",
        "numeric_delta": "(q18_query-q18_candidate)/2.000000000000000000",
        "categorical_delta": "0_if_equal_else_1",
        "sum": "five_squared_deltas_no_intermediate_quantization",
        "sqrt": "decimal_sqrt_then_quantize_once_q18",
    }
    registry, schemas = _schema_registry()
    Draft202012Validator(
        schemas["spy_experience_registration.v1.schema.json"], registry=registry
    ).validate(registration.value)


def test_registration_rejects_hash_drift_and_unbounded_denominator() -> None:
    registration = accrual.load_registration(ROOT)
    changed = copy.deepcopy(registration.value)
    changed["spec"]["calendar"]["expected_opportunity_rule"] = "every_session_forever"
    with pytest.raises(accrual.MarketMemoryExperienceRegistrationError, match="spec drift"):
        accrual.validate_registration(changed)


def test_public_validators_reject_split_views_subclasses_and_deep_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DictSubclass(dict):
        pass

    class ListSubclass(list):
        pass

    class StringSubclass(str):
        pass

    class SplitView(Mapping):
        def __init__(self, clean: dict) -> None:
            self.clean = clean

        def __iter__(self):
            return iter(self.clean)

        def __len__(self) -> int:
            return len(self.clean)

        def __getitem__(self, key):
            if key == "evil":
                return True
            return self.clean[key]

        def items(self):
            return [*self.clean.items(), ("evil", True)]

    registration = accrual.load_registration(ROOT)
    with pytest.raises(
        accrual.MarketMemoryExperienceRegistrationError,
        match="non-JSON-native",
    ):
        accrual.validate_registration(SplitView(registration.value))
    hostile_registration = copy.deepcopy(registration.value)
    hostile_registration["schema"] = StringSubclass(
        hostile_registration["schema"]
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceRegistrationError,
        match="non-JSON-native",
    ):
        accrual.validate_registration(hostile_registration)

    class BytesSubclass(bytes):
        pass

    with pytest.raises(
        accrual.MarketMemoryExperienceRegistrationError,
        match="exact canonical bytes",
    ):
        accrual.validate_registration(
            registration.value, body=BytesSubclass(registration.body)
        )
    deep: object = None
    for _ in range(2_000):
        deep = [deep]
    hostile_registration = copy.deepcopy(registration.value)
    hostile_registration["spec"] = deep
    with pytest.raises(
        accrual.MarketMemoryExperienceRegistrationError,
        match="depth bound",
    ):
        accrual.validate_registration(hostile_registration)
    aggregate_registration = copy.deepcopy(registration.value)
    aggregate_registration["spec"] = {
        "many_strings": ["x" * 100_000] * 90
    }
    with pytest.raises(
        accrual.MarketMemoryExperienceRegistrationError,
        match="aggregate UTF-8 byte bound",
    ):
        accrual.validate_registration(aggregate_registration)

    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:36:00Z",
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:50:00Z",
    )
    opportunity = _read(experience / "opportunities" / "2026-08-17.json")
    outcome = _read(
        experience / "outcomes" / opportunity["opportunity_id"] / "000001.json"
    )
    population_head = _read(experience / "population_HEAD.json")
    population = _read(
        experience
        / "population_receipts"
        / f"{population_head['population_receipt_id']}.json"
    )

    class RegistrationSubclass(accrual.Registration):
        pass

    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="exact Registration",
    ):
        accrual.validate_opportunity(
            opportunity,
            registration=RegistrationSubclass(
                registration.value, registration.body
            ),
        )
    with pytest.raises(accrual.MarketMemoryExperienceStoreError, match="non-JSON-native"):
        accrual.validate_opportunity(
            DictSubclass(opportunity), registration=registration
        )
    tuple_opportunity = copy.deepcopy(opportunity)
    tuple_opportunity["claims"] = tuple(tuple_opportunity["claims"].items())
    with pytest.raises(accrual.MarketMemoryExperienceStoreError, match="non-JSON-native"):
        accrual.validate_opportunity(tuple_opportunity, registration=registration)
    with pytest.raises(accrual.MarketMemoryExperienceStoreError, match="non-JSON-native"):
        accrual.validate_outcome_revision(
            DictSubclass(outcome),
            registration=registration,
            opportunity=opportunity,
        )
    with pytest.raises(TypeError, match="unexpected keyword"):
        accrual.validate_outcome_revision(
            outcome,
            registration=registration,
            opportunity=DictSubclass(opportunity),
            _auxiliary_frozen=True,
        )
    with pytest.raises(accrual.MarketMemoryExperienceStoreError, match="non-JSON-native"):
        accrual.validate_outcome_revision(
            outcome,
            registration=registration,
            opportunity=DictSubclass(opportunity),
        )
    with pytest.raises(accrual.MarketMemoryExperienceStoreError, match="exact list"):
        accrual.validate_outcome_revision(
            outcome,
            registration=registration,
            opportunity=opportunity,
            history=ListSubclass(),
        )
    with pytest.raises(accrual.MarketMemoryExperienceStoreError, match="non-JSON-native"):
        accrual.validate_population_receipt(
            DictSubclass(population),
            registration=registration,
            expected_sessions=[ACTIVATION],
            opportunities=[opportunity],
        )
    with pytest.raises(accrual.MarketMemoryExperienceStoreError, match="exact list"):
        accrual.validate_population_receipt(
            population,
            registration=registration,
            expected_sessions=[ACTIVATION],
            opportunities=ListSubclass([opportunity]),
        )
    with pytest.raises(accrual.MarketMemoryExperienceStoreError, match="non-JSON-native"):
        accrual.validate_population_receipt(
            population,
            registration=registration,
            expected_sessions=[ACTIVATION],
            opportunities=[DictSubclass(opportunity)],
        )


def test_exact_binary64_encoding_and_q18_ignore_ambient_decimal_context() -> None:
    from decimal import getcontext

    previous = getcontext().prec
    try:
        getcontext().prec = 2
        mark = accrual._binary64_mark(0.1, field="fixture")
        assert mark["end_close_binary64_hex"] == 0.1.hex()
        assert mark["end_close_exact_decimal"].startswith("0.10000000000000000555")
        assert accrual._q18_ratio(3.0, 2.0) == "1.500000000000000000"
        assert accrual._q18_fraction(1, 6) == "0.166666666666666667"
        assert accrual._q18_fraction(1, 16 * 10**18) == "0.000000000000000000"
        assert accrual._q18_fraction(3, 16 * 10**18) == "0.000000000000000000"
        assert accrual._signed_binary64_q18(0, field="integer zero") == (
            accrual._signed_binary64_q18(0.0, field="float zero")
        )
    finally:
        getcontext().prec = previous

    feature = {
        "schema": "market_memory.macro_regime_feature_object.v1",
        "transform_version": accrual.SOURCE_REGIME_TRANSFORM_VERSION,
        "state": {
            "growth_score": 0,
            "inflation_score": 0.0,
            "quad": "Q1",
            "liquidity_overlay": "unknown",
            "cycle_tag": "mid",
        },
    }
    unavailable, reason, raw = accrual._decision_state_projection(
        feature,
        feature_snapshot_id="mmsnap_" + "1" * 64,
        feature_content_sha256="2" * 64,
    )
    assert unavailable is None
    assert reason == "owner_liquidity_overlay_unknown"
    assert raw == {
        "quad": "Q1",
        "liquidity_overlay": "unknown",
        "cycle_tag": "mid",
    }


def test_owner_clock_ordering_uses_parsed_utc_instants_not_timestamp_text() -> None:
    def candidate(capture_digit: str, observed_at: str):
        return accrual._TechnicalCandidate(
            reference={
                "capture_id": "mmactualcapture_" + capture_digit * 64,
                "first_observed_at": observed_at,
            },
            end_close=100.0,
        )

    at_t = candidate("f", "2026-08-25T04:35:00Z")
    at_t_plus_100ms = candidate("0", "2026-08-25T04:35:00.100000Z")
    assert not accrual._owner_clock_tie(
        [at_t, at_t_plus_100ms], clock_field="first_observed_at"
    )
    assert accrual._first_owner_observed(
        [at_t_plus_100ms, at_t], clock_field="first_observed_at"
    ) is at_t

    same_instant_short = candidate("1", "2026-08-25T04:35:00.1Z")
    assert accrual._owner_clock_tie(
        [at_t_plus_100ms, same_instant_short],
        clock_field="first_observed_at",
    )


def test_clock_snapshot_is_one_exact_base_utc_datetime() -> None:
    sampled = datetime(
        2026,
        8,
        17,
        21,
        35,
        0,
        123456,
        tzinfo=timezone(timedelta(hours=-7)),
    )
    snapshot = accrual._sample_clock(lambda: sampled)
    assert type(snapshot) is datetime
    assert snapshot.tzinfo is timezone.utc
    assert snapshot == datetime(
        2026, 8, 18, 4, 35, 0, 123456, tzinfo=timezone.utc
    )
    assert accrual._format_utc(snapshot) == "2026-08-18T04:35:00.123456Z"


def test_datetime_subclass_is_rejected_before_clock_overrides_in_builder() -> None:
    registration = accrual.load_registration(ROOT)
    hostile = HostileDateTime(2026, 8, 18, 4, 46, tzinfo=timezone.utc)
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="clock must be one exact timezone-aware datetime",
    ):
        accrual._missed_opportunity(
            registration,
            session=ACTIVATION,
            reconciled_at=hostile,
            writer_commit=COMMIT,
        )


def test_clock_normalization_failure_is_one_w2c_contract_error() -> None:
    broken = datetime(2026, 8, 18, 4, 35, tzinfo=BrokenClockZone())
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="writer clock sample cannot be normalized to UTC",
    ) as failure:
        accrual._sample_clock(lambda: broken)
    assert isinstance(failure.value.__cause__, AttributeError)


def test_accrual_rejects_datetime_subclass_clock_before_store_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    hostile = HostileDateTime(2026, 8, 11, 20, tzinfo=timezone.utc)
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="writer clock sample must be one exact timezone-aware datetime",
    ):
        accrual.accrue_spy_experience(
            ROOT,
            experience_root=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            writer_commit=COMMIT,
            clock=lambda: hostile,
        )
    assert not experience.exists()


def test_public_owner_surface_and_w2c_import_purity() -> None:
    assert {
        "PinnedTechnicalCaptureIndexEntry",
        "PinnedTechnicalGenerationSnapshot",
        "pin_technical_actual_output_generation",
        "TechnicalGenerationHeadObservation",
        "observe_technical_actual_output_generation_head",
        "load_technical_actual_output_captures_from_pinned_generation",
    } <= set(technical_store.__all__)
    source = (ROOT / "engine/neuralweb/market_memory_experience_accrual.py").read_text()
    tree = ast.parse(source)
    imported = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(name.startswith("app") or name.startswith("site") for name in imported)
    forbidden = (
        "capture_trusted_regime_context", "capture_technical_actual_output",
        "fetch_current_spy_daily_inputs", "project_current_spy_raw_close_ratio",
        "market_memory_forward_store", "prophet", "operating_cortex",
    )
    assert all(token not in source for token in forbidden)
    assert "source_bodies" not in {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "market_memory_experience_accrual" not in (
        ROOT / "engine/neuralweb/market_memory_trusted.py"
    ).read_text()
    assert "market_memory_experience_accrual" not in (
        ROOT / "engine/neuralweb/market_memory_technical_store.py"
    ).read_text()


def test_arcx_instrument_and_xnys_calendar_cannot_be_conflated() -> None:
    reference = {
        "capture_id": "mmactualcapture_" + "1" * 64,
        "revision_id": "mmtechrev_" + "2" * 64,
        "source_observation_id": "mmtechsrc_" + "3" * 64,
        "snapshot_id": "mmtechsnap_" + "4" * 64,
        "source_session": "2026-08-17",
        "first_observed_at": "2026-08-18T02:00:00Z",
        "spy_parquet_sha256": "5" * 64,
        **accrual._binary64_mark(120.0, field="fixture"),
        "subject": copy.deepcopy(accrual._SUBJECT),
        "calendar": copy.deepcopy(accrual._CALENDAR),
        "price_basis": {
            "raw_unadjusted": True, "split_adjusted": False,
            "dividend_adjusted": False, "economic_return": False,
        },
    }
    assert accrual._validate_technical_ref(reference, session="2026-08-17")
    broken = copy.deepcopy(reference)
    broken["subject"]["mic"] = "XNYS"
    with pytest.raises(accrual.MarketMemoryExperienceStoreError, match="ARCX"):
        accrual._validate_technical_ref(broken, session="2026-08-17")


@pytest.mark.parametrize("changing", ["trusted", "technical"])
def test_head_change_sandwich_is_retryable_and_never_invents_a_pair(
    monkeypatch: pytest.MonkeyPatch, changing: str
) -> None:
    def pin(name: str, generation: str):
        return SimpleNamespace(
            profile=(trusted.TRUSTED_STORE_PROFILE if name == "trusted" else technical_store.STORE_PROFILE),
            store_id=("mmstore_" if name == "trusted" else "mmactualstore_") + "1" * 64,
            generation_id=("mmgeneration_" if name == "trusted" else "mmactualgeneration_") + generation * 64,
            generation_sha256=generation * 64,
            captures=(),
        )

    trusted_pins = [pin("trusted", "1"), pin("trusted", "2" if changing == "trusted" else "1")]
    technical_pins = [pin("technical", "3"), pin("technical", "4" if changing == "technical" else "3")]

    class Reader:
        def read_pinned_generation(self, **_kwargs):
            return trusted_pins.pop(0)

    monkeypatch.setattr(accrual, "_trusted_candidates", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(accrual, "_technical_candidates", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        technical_store,
        "pin_technical_actual_output_generation",
        lambda *_args, **_kwargs: technical_pins.pop(0),
    )
    observed = accrual._observe_opportunity_sources(
        reader=Reader(),
        trusted_root="ignored",
        technical_root="ignored",
        session=ACTIVATION,
        clock=_clock("2026-08-18T04:35:00Z"),
    )
    assert observed.disposition is None
    assert observed.reason == "owner_pair_not_stable"
    assert observed.source_pins is None


def test_run_owner_pair_retry_is_bounded_and_eventual_stability_is_authenticated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registration = accrual.load_registration(ROOT)

    def head(*, technical: bool, digit: str):
        return SimpleNamespace(
            profile=(
                technical_store.STORE_PROFILE
                if technical
                else trusted.TRUSTED_STORE_PROFILE
            ),
            store_id=("mmactualstore_" if technical else "mmstore_") + "1" * 64,
            generation_id=(
                "mmactualgeneration_" if technical else "mmgeneration_"
            )
            + digit * 64,
            generation_sha256=digit * 64,
            capture_count=0,
        )

    def pin(*, technical: bool, digit: str):
        value = head(technical=technical, digit=digit)
        return SimpleNamespace(
            profile=value.profile,
            store_id=value.store_id,
            generation_id=value.generation_id,
            generation_sha256=value.generation_sha256,
            captures=(),
            ancestry_generation_ids=(),
        )

    class EventualReader:
        def __init__(self) -> None:
            self.heads = iter(
                [
                    head(technical=False, digit="1"),
                    head(technical=False, digit="2"),
                    head(technical=False, digit="3"),
                    head(technical=False, digit="3"),
                ]
            )
            self.full_pin_calls = 0

        def observe_generation_head(self, **_kwargs):
            return next(self.heads)

        def read_pinned_generation(self, **_kwargs):
            self.full_pin_calls += 1
            return pin(technical=False, digit="3")

    reader = EventualReader()
    technical_heads = iter(
        [
            head(technical=True, digit="4"),
            head(technical=True, digit="5"),
            head(technical=True, digit="6"),
            head(technical=True, digit="6"),
        ]
    )
    technical_full_pins: list[int] = []
    monkeypatch.setattr(
        technical_store,
        "observe_technical_actual_output_generation_head",
        lambda *_args, **_kwargs: next(technical_heads),
    )
    monkeypatch.setattr(
        technical_store,
        "pin_technical_actual_output_generation",
        lambda *_args, **_kwargs: (
            technical_full_pins.append(1) or pin(technical=True, digit="6")
        ),
    )
    monkeypatch.setattr(accrual, "_trusted_candidates_by_session", lambda *_args: {})
    monkeypatch.setattr(accrual, "_prepare_technical_view", lambda *_args, **_kwargs: ({}, None))
    monkeypatch.setattr(accrual, "_publish_technical_view", lambda *_args: None)
    clock_values = iter(
        [
            datetime(2026, 8, 18, 4, 30, tzinfo=timezone.utc),
            datetime(2026, 8, 18, 4, 30, tzinfo=timezone.utc),
            datetime(2026, 8, 18, 4, 30, 30, tzinfo=timezone.utc),
        ]
    )
    sleeps: list[float] = []
    view = accrual._observe_run_owner_view(
        tmp_path,
        registration=registration,
        trusted_root=tmp_path / "trusted-v1",
        reader=reader,
        initial_pins=accrual.OwnerPins(
            trusted=pin(technical=False, digit="0"),
            technical=pin(technical=True, digit="0"),
        ),
        technical_root=tmp_path / "technicals-v1",
        clock=lambda: next(clock_values),
        retry_deadline=datetime(2026, 8, 18, 4, 45, tzinfo=timezone.utc),
        sleeper=sleeps.append,
    )
    assert view.stable is True
    assert view.pin_observed_at == "2026-08-18T04:30:30Z"
    assert sleeps == [30.0]
    # One initial ancestry pin plus at most one stable-pair ancestry pin per owner.
    assert 1 + reader.full_pin_calls == 2
    assert 1 + len(technical_full_pins) == 2


def test_owner_clock_after_local_cutoff_is_an_owner_integrity_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registration = accrual.load_registration(ROOT)

    def pin(*, technical: bool):
        return SimpleNamespace(
            profile=(
                technical_store.STORE_PROFILE
                if technical
                else trusted.TRUSTED_STORE_PROFILE
            ),
            store_id=("mmactualstore_" if technical else "mmstore_")
            + "1" * 64,
            generation_id=(
                "mmactualgeneration_" if technical else "mmgeneration_"
            )
            + "2" * 64,
            generation_sha256="2" * 64,
            captures=(),
            ancestry_generation_ids=(),
        )

    trusted_pin = pin(technical=False)
    technical_pin = pin(technical=True)

    class Reader:
        def observe_generation_head(self, **_kwargs):
            return trusted_pin

    monkeypatch.setattr(
        technical_store,
        "observe_technical_actual_output_generation_head",
        lambda *_args, **_kwargs: technical_pin,
    )
    monkeypatch.setattr(
        accrual, "_trusted_candidates_by_session", lambda *_args: {}
    )
    future_candidate = accrual._TechnicalCandidate(
        reference={"first_observed_at": "2026-08-18T04:46:01Z"},
        end_close=120.0,
    )
    monkeypatch.setattr(
        accrual,
        "_prepare_technical_view",
        lambda *_args, **_kwargs: (
            {ACTIVATION.isoformat(): (future_candidate,)},
            None,
        ),
    )
    monkeypatch.setattr(
        accrual,
        "_publish_technical_view",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("invalid owner clocks must not publish a local view")
        ),
    )
    observed = datetime(2026, 8, 18, 4, 46, tzinfo=timezone.utc)
    view = accrual._observe_run_owner_view(
        tmp_path,
        registration=registration,
        trusted_root=tmp_path / "trusted-v1",
        reader=Reader(),
        initial_pins=accrual.OwnerPins(
            trusted=trusted_pin, technical=technical_pin
        ),
        technical_root=tmp_path / "technicals-v1",
        clock=lambda: observed,
        retry_deadline=observed,
        sleeper=lambda _seconds: None,
    )
    assert view.stable is False
    assert view.failure_reason == "owner_integrity_failure_by_deadline"


@pytest.mark.parametrize("mutation", ["delete", "tamper"])
def test_w2c_never_admits_when_trusted_context_receipt_alias_is_not_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    reader = trusted.TrustedFileAsKnownAtReader(trusted_root)
    generation = reader.read_pinned_generation(maximum_capture_count=256)
    assert len(generation.captures) == 1
    context_path = pit._context_path(
        trusted_root, generation.captures[0].context_id
    )
    if mutation == "delete":
        context_path.unlink()
    else:
        context_path.write_bytes(b"{}")

    result = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:46:00Z",
    )
    assert len(result.opportunity_ids) == 1
    opportunity = _read(experience / "opportunities" / "2026-08-17.json")
    assert opportunity["disposition"] == "missed"
    assert opportunity["reason"] == "owner_integrity_failure_by_deadline"
    assert opportunity["source_pins"] is None
    assert opportunity["claims"]["source_generation_pins_authenticated"] is False


def test_run_owner_pair_continuous_movement_stops_after_31_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registration = accrual.load_registration(ROOT)
    calls = {"trusted_heads": 0, "technical_heads": 0}

    def moving_head(*, technical: bool, ordinal: int):
        digit = f"{ordinal:064x}"
        return SimpleNamespace(
            profile=(
                technical_store.STORE_PROFILE
                if technical
                else trusted.TRUSTED_STORE_PROFILE
            ),
            store_id=("mmactualstore_" if technical else "mmstore_") + "1" * 64,
            generation_id=(
                "mmactualgeneration_" if technical else "mmgeneration_"
            )
            + digit,
            generation_sha256=digit,
            capture_count=0,
        )

    class MovingReader:
        def observe_generation_head(self, **_kwargs):
            calls["trusted_heads"] += 1
            return moving_head(
                technical=False, ordinal=calls["trusted_heads"]
            )

        def read_pinned_generation(self, **_kwargs):  # pragma: no cover - must not pin
            raise AssertionError("unstable HEAD pair must not ancestry-pin")

    def observe_technical(*_args, **_kwargs):
        calls["technical_heads"] += 1
        return moving_head(
            technical=True, ordinal=calls["technical_heads"]
        )

    monkeypatch.setattr(
        technical_store,
        "observe_technical_actual_output_generation_head",
        observe_technical,
    )
    monkeypatch.setattr(
        technical_store,
        "pin_technical_actual_output_generation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unstable HEAD pair must not ancestry-pin")
        ),
    )
    initial = SimpleNamespace(
        profile=trusted.TRUSTED_STORE_PROFILE,
        store_id="mmstore_" + "1" * 64,
        generation_id="mmgeneration_" + "0" * 64,
        generation_sha256="0" * 64,
        captures=(),
        ancestry_generation_ids=(),
    )
    initial_technical = SimpleNamespace(
        profile=technical_store.STORE_PROFILE,
        store_id="mmactualstore_" + "1" * 64,
        generation_id="mmactualgeneration_" + "0" * 64,
        generation_sha256="0" * 64,
        captures=(),
        ancestry_generation_ids=(),
    )
    times = iter(
        datetime(2026, 8, 18, 4, 30, tzinfo=timezone.utc)
        + timedelta(seconds=30 * ordinal)
        for ordinal in range(32)
    )
    sleeps: list[float] = []
    view = accrual._observe_run_owner_view(
        tmp_path,
        registration=registration,
        trusted_root=tmp_path / "trusted-v1",
        reader=MovingReader(),
        initial_pins=accrual.OwnerPins(
            trusted=initial, technical=initial_technical
        ),
        technical_root=tmp_path / "technicals-v1",
        clock=lambda: next(times),
        retry_deadline=datetime(2026, 8, 18, 4, 45, tzinfo=timezone.utc),
        sleeper=sleeps.append,
    )
    assert view.stable is False
    assert view.pin_observed_at == "2026-08-18T04:45:30Z"
    assert accrual._parse_utc(
        view.pin_observed_at, field="retry reconciliation"
    ) > datetime(2026, 8, 18, 4, 45, tzinfo=timezone.utc)
    assert calls == {"trusted_heads": 60, "technical_heads": 60}
    assert calls["trusted_heads"] <= 2 * accrual.OWNER_PAIR_MAX_ATTEMPTS
    assert sleeps == [30.0] * 29


def test_unstable_owner_pair_crossing_deadline_seals_a_missed_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )

    def unstable(*_args, reader, **_kwargs):
        return accrual._RunOwnerView(
            pin_observed_at="2026-08-18T04:45:01Z",
            stable=False,
            reader=reader,
            pins=None,
            trusted_candidates_by_session={},
            technical_candidates_by_session={},
        )

    monkeypatch.setattr(accrual, "_observe_run_owner_view", unstable)
    result = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:35:00Z",
    )
    assert len(result.opportunity_ids) == 1
    missed = _read(experience / "opportunities" / "2026-08-17.json")
    assert missed["disposition"] == "missed"
    assert missed["reason"] == "owner_pair_not_stable_by_deadline"
    assert missed["claims"] == {
        "external_clock_authenticated": False,
        "aba_resistance_authenticated": False,
        "calendar_session_derivation_authenticated": True,
        "source_generation_pins_authenticated": False,
    }


def test_installation_is_required_before_activation_and_never_backfilled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(tmp_path, monkeypatch)
    with pytest.raises(accrual.MarketMemoryExperienceAccrualError, match="NO-GO"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-17T00:00:00Z",
        )
    assert not experience.exists()


@pytest.mark.parametrize(
    ("receipt_name", "stage"),
    [
        (receipt_name, stage)
        for receipt_name in ("registration_installation.json", "manifest.json")
        for stage in (
            "temporary_fsynced",
            "final_linked",
            "final_directory_fsynced",
            "temporary_unlinked",
        )
    ],
)
def test_installation_and_manifest_create_once_recover_every_durability_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    receipt_name: str,
    stage: str,
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    original_boundary = accrual._publish_boundary
    injected = False

    def crash_at_boundary(observed_stage: str, path: Path) -> None:
        nonlocal injected
        if (
            not injected
            and path.name == receipt_name
            and observed_stage == stage
        ):
            injected = True
            raise RuntimeError(f"injected {receipt_name} {stage}")

    monkeypatch.setattr(accrual, "_publish_boundary", crash_at_boundary)
    with pytest.raises(RuntimeError, match="injected"):
        _install(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
        )
    assert injected
    final_path = experience / receipt_name
    pending = sorted(experience.glob(f".{receipt_name}.*.pending"))
    assert len(pending) <= 1
    crash_bytes = final_path.read_bytes() if final_path.exists() else pending[0].read_bytes()

    monkeypatch.setattr(accrual, "_publish_boundary", original_boundary)
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    assert final_path.read_bytes() == crash_bytes
    installation_bytes = (experience / "registration_installation.json").read_bytes()
    manifest_bytes = (experience / "manifest.json").read_bytes()
    assert not list(experience.glob(".*.pending"))

    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    assert (experience / "registration_installation.json").read_bytes() == installation_bytes
    assert (experience / "manifest.json").read_bytes() == manifest_bytes
    assert not list(experience.rglob("*.pending"))


def test_pending_only_installation_recovers_after_activation_without_repin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    original_boundary = accrual._publish_boundary

    def crash_after_installation_fsync(stage: str, path: Path) -> None:
        if (
            stage == "temporary_fsynced"
            and path.name == "registration_installation.json"
        ):
            raise InjectedDurabilityCrash("pending installation is durable")

    monkeypatch.setattr(
        accrual, "_publish_boundary", crash_after_installation_fsync
    )
    with pytest.raises(InjectedDurabilityCrash, match="pending installation"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-11T20:00:00Z",
        )
    pending = list(
        experience.glob(".registration_installation.json.*.pending")
    )
    assert len(pending) == 1
    pending_body = pending[0].read_bytes()
    assert not (experience / "registration_installation.json").exists()
    monkeypatch.setattr(accrual, "_publish_boundary", original_boundary)

    def owner_absent(*_args, **_kwargs):
        raise FileNotFoundError("owners unavailable after activation")

    monkeypatch.setattr(accrual, "_pin_owners", owner_absent)
    accrual.accrue_spy_experience(
        ROOT,
        experience_root=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        writer_commit=COMMIT,
        clock=_clock("2027-03-03T04:46:00Z"),
        sleeper=lambda _seconds: None,
    )
    assert (
        experience / "registration_installation.json"
    ).read_bytes() == pending_body
    assert not list(experience.rglob("*.pending"))
    verified = accrual.verify_terminal_ledger(
        ROOT, experience_root=experience
    )
    assert verified is not None
    assert verified["final_source_revision_census_authenticated"] is False


@pytest.mark.parametrize(
    ("relative_path", "body"),
    [
        (Path("opportunities/2026-08-17.json"), b"{}"),
        (Path("outcomes/mmspyexpopp_" + "1" * 64 + "/000001.json"), b"{}"),
        (Path("population_HEAD.json"), b"{}"),
    ],
)
def test_capture_bearing_or_ambiguous_partial_initialization_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_path: Path,
    body: bytes,
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    target = experience / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="partial initialization|unknown artifact|population HEAD",
    ):
        _install(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
        )
    assert not (experience / "registration_installation.json").exists()


_IMMUTABLE_PUBLICATION_STAGES = (
    "temporary_fsynced",
    "final_linked",
    "final_directory_fsynced",
    "temporary_unlinked",
)
_MUTABLE_PUBLICATION_STAGES = (
    "temporary_fsynced",
    "final_replaced",
    "final_directory_fsynced",
)


@pytest.mark.parametrize(
    ("artifact", "stage"),
    [
        *((artifact, stage) for artifact in (
            "technical_view", "prepared_object", "prepared_seal",
            "opportunity", "population_receipt",
        ) for stage in _IMMUTABLE_PUBLICATION_STAGES),
        *((artifact, stage) for artifact in (
            "technical_view_head", "population_head",
        ) for stage in _MUTABLE_PUBLICATION_STAGES),
    ],
)
def test_admission_artifacts_recover_every_publication_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact: str,
    stage: str,
) -> None:
    _unused, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    experience = (
        tmp_path / artifact / stage / "market-memory" / "state" / "experience-v1"
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    original_boundary = accrual._publish_boundary
    injected = False

    def matches(path: Path) -> bool:
        return {
            "technical_view": path.parent.name == "technical_views",
            "technical_view_head": path.name == "technical_view_HEAD.json",
            "prepared_object": path.parent.name == "prepared_objects",
            "prepared_seal": path.parent.name == "prepared_sessions",
            "opportunity": path.parent.name == "opportunities",
            "population_receipt": path.parent.name == "population_receipts",
            "population_head": path.name == "population_HEAD.json",
        }[artifact]

    def crash_at_boundary(observed_stage: str, path: Path) -> None:
        nonlocal injected
        if not injected and observed_stage == stage and matches(path):
            injected = True
            raise InjectedDurabilityCrash(f"injected {artifact} {stage}")

    monkeypatch.setattr(accrual, "_publish_boundary", crash_at_boundary)
    with pytest.raises(InjectedDurabilityCrash, match="injected"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-18T04:35:00Z",
        )
    assert injected
    monkeypatch.setattr(accrual, "_publish_boundary", original_boundary)
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:36:00Z",
    )
    opportunity = _read(experience / "opportunities" / "2026-08-17.json")
    assert opportunity["disposition"] == "admitted"
    assert (experience / "population_HEAD.json").is_file()
    assert not list(experience.rglob("*.pending"))
    frozen = {
        str(path.relative_to(experience)): path.read_bytes()
        for path in experience.rglob("*")
        if path.is_file()
    }
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:37:00Z",
    )
    assert {
        str(path.relative_to(experience)): path.read_bytes()
        for path in experience.rglob("*")
        if path.is_file()
    } == frozen


@pytest.mark.parametrize("stage", _IMMUTABLE_PUBLICATION_STAGES)
def test_missed_opportunity_recovers_every_publication_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    _unused, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    experience = (
        tmp_path / "missed" / stage / "market-memory" / "state" / "experience-v1"
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    original_boundary = accrual._publish_boundary
    injected = False

    def crash_at_boundary(observed_stage: str, path: Path) -> None:
        nonlocal injected
        if (
            not injected
            and observed_stage == stage
            and path.parent.name == "opportunities"
        ):
            injected = True
            raise InjectedDurabilityCrash("injected missed opportunity")

    monkeypatch.setattr(accrual, "_publish_boundary", crash_at_boundary)
    with pytest.raises(InjectedDurabilityCrash, match="missed opportunity"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-18T04:50:00Z",
        )
    assert injected
    monkeypatch.setattr(accrual, "_publish_boundary", original_boundary)
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:51:00Z",
    )
    missed = _read(experience / "opportunities" / "2026-08-17.json")
    assert missed["disposition"] == "missed"
    assert missed["cutoff"]["reconciled_at"] == "2026-08-18T04:50:00Z"
    assert not list(experience.rglob("*.pending"))


@pytest.mark.parametrize("stage", _IMMUTABLE_PUBLICATION_STAGES)
def test_outcome_recovers_every_publication_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    _unused, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    experience = (
        tmp_path / "outcome" / stage / "market-memory" / "state" / "experience-v1"
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:35:00Z",
    )
    original_boundary = accrual._publish_boundary
    injected = False

    def crash_at_boundary(observed_stage: str, path: Path) -> None:
        nonlocal injected
        if (
            not injected
            and observed_stage == stage
            and path.parent.parent.name == "outcomes"
        ):
            injected = True
            raise InjectedDurabilityCrash("injected outcome publication")

    monkeypatch.setattr(accrual, "_publish_boundary", crash_at_boundary)
    with pytest.raises(InjectedDurabilityCrash, match="outcome publication"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-25T04:31:00Z",
        )
    assert injected
    monkeypatch.setattr(accrual, "_publish_boundary", original_boundary)
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:32:00Z",
    )
    opportunity = _read(experience / "opportunities" / "2026-08-17.json")
    outcome = _read(
        experience / "outcomes" / opportunity["opportunity_id"] / "000001.json"
    )
    assert outcome["status"] == "unavailable"
    assert outcome["appended_at"] == "2026-08-25T04:31:00Z"
    assert not list(experience.rglob("*.pending"))


@pytest.mark.parametrize("stage", _IMMUTABLE_PUBLICATION_STAGES)
def test_terminal_marker_recovers_every_publication_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    _unused, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    experience = (
        tmp_path / "terminal" / stage / "market-memory" / "state" / "experience-v1"
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )

    def owner_absent(*_args, **_kwargs):
        raise FileNotFoundError("owner HEAD absent")

    monkeypatch.setattr(accrual, "_pin_owners", owner_absent)
    original_boundary = accrual._publish_boundary
    injected = False

    def crash_at_boundary(observed_stage: str, path: Path) -> None:
        nonlocal injected
        if (
            not injected
            and observed_stage == stage
            and path.name == "TERMINAL.json"
        ):
            injected = True
            raise InjectedDurabilityCrash("injected terminal marker")

    monkeypatch.setattr(accrual, "_publish_boundary", crash_at_boundary)
    with pytest.raises(InjectedDurabilityCrash, match="terminal marker"):
        accrual.accrue_spy_experience(
            ROOT,
            experience_root=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            writer_commit=COMMIT,
            clock=_clock("2027-03-03T04:46:00Z"),
            sleeper=lambda _seconds: None,
        )
    assert injected
    monkeypatch.setattr(accrual, "_publish_boundary", original_boundary)
    resumed = accrual.accrue_spy_experience(
        ROOT,
        experience_root=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        writer_commit=COMMIT,
        clock=_clock("2027-03-03T04:47:00Z"),
        sleeper=lambda _seconds: None,
    )
    assert resumed.population_receipt_id is not None
    assert accrual.verify_terminal_ledger(
        ROOT, experience_root=experience
    ) is not None
    assert not list(experience.rglob("*.pending"))


def test_admission_is_one_immutable_same_session_row_and_schema_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(tmp_path, monkeypatch)
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    result = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:35:00Z",
    )
    assert len(result.opportunity_ids) == 1
    opportunity = _read(experience / "opportunities" / "2026-08-17.json")
    assert opportunity["disposition"] == "admitted"
    assert opportunity["session"] == "2026-08-17"
    assert opportunity["target_session"] == "2026-08-24"
    assert opportunity["cutoff"]["actual_cutoff_at"] == "2026-08-18T04:35:00Z"
    assert opportunity["source_pins"]["subject"]["mic"] == "ARCX"
    assert opportunity["source_pins"]["calendar"]["market_session"] == "XNYS_REGULAR"
    assert opportunity["source_pins"]["trusted_capture"]["source_session"] == "2026-08-17"
    assert opportunity["source_pins"]["technical_capture"]["source_session"] == "2026-08-17"
    assert opportunity["claims"] == {
        "external_clock_authenticated": False,
        "aba_resistance_authenticated": False,
        "calendar_session_derivation_authenticated": True,
        "source_generation_pins_authenticated": True,
    }
    assert "regular_close" not in json.dumps(opportunity).lower()
    assert "source_bodies" not in json.dumps(opportunity)
    decision_state = opportunity["decision_state_projection"]
    assert decision_state["schema"] == (
        "market_memory.spy_regime_decision_state_projection.v1"
    )
    assert decision_state["source_transform_version"] == (
        "market_memory.macro_regime_transform.v1"
    )
    assert decision_state["feature_content_sha256"] == opportunity[
        "source_pins"
    ]["trusted_capture"]["feature_content_sha256"]
    registry, schemas = _schema_registry()
    Draft202012Validator(
        schemas["spy_experience_opportunity.v1.schema.json"], registry=registry
    ).validate(opportunity)
    forged = copy.deepcopy(opportunity)
    forged["claims"]["source_generation_pins_authenticated"] = False
    forged = _rehash(
        forged, field="opportunity_id", prefix="mmspyexpopp_"
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="conditional fields disagree",
    ):
        accrual.validate_opportunity(
            forged, registration=accrual.load_registration(ROOT)
        )
    # A transient A -> B -> A between the two reads is not observable in v1.
    # Rehashing a stronger claim must still fail both runtime and schema gates.
    forged_aba = copy.deepcopy(opportunity)
    forged_aba["claims"]["aba_resistance_authenticated"] = True
    forged_aba = _rehash(
        forged_aba, field="opportunity_id", prefix="mmspyexpopp_"
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="conditional fields disagree",
    ):
        accrual.validate_opportunity(
            forged_aba, registration=accrual.load_registration(ROOT)
        )
    with pytest.raises(ValidationError):
        Draft202012Validator(
            schemas["spy_experience_opportunity.v1.schema.json"],
            registry=registry,
        ).validate(forged_aba)
    forged_projection = copy.deepcopy(opportunity)
    forged_projection["decision_state_projection"][
        "feature_content_sha256"
    ] = "f" * 64
    forged_projection = _rehash(
        forged_projection,
        field="opportunity_id",
        prefix="mmspyexpopp_",
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="projection binding drift",
    ):
        accrual.validate_opportunity(
            forged_projection, registration=accrual.load_registration(ROOT)
        )
    repeated = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:40:00Z",
    )
    assert repeated.opportunity_ids == ()
    assert len(list((experience / "opportunities").glob("*.json"))) == 1


def test_predeadline_prepared_seal_resumes_after_crash_but_unsealed_becomes_missed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(tmp_path, monkeypatch)
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    original = accrual._write_opportunity
    monkeypatch.setattr(
        accrual,
        "_write_opportunity",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("crash after prepared seal")),
    )
    with pytest.raises(RuntimeError, match="crash after prepared"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-18T04:35:00Z",
        )
    assert (experience / "prepared_sessions" / "2026-08-17.json").is_file()
    assert not (experience / "opportunities" / "2026-08-17.json").exists()
    monkeypatch.setattr(accrual, "_write_opportunity", original)
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:50:00Z",
    )
    resumed = _read(experience / "opportunities" / "2026-08-17.json")
    assert resumed["disposition"] == "admitted"
    assert resumed["sealed_at"] == "2026-08-18T04:35:00Z"

    second = tmp_path / "second" / "market-memory" / "state" / "experience-v1"
    _install(
        tmp_path,
        experience=second,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=second,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:50:00Z",
    )
    missed = _read(second / "opportunities" / "2026-08-17.json")
    assert missed["disposition"] == "missed"
    assert missed["reason"] == "not_sealed_by_deadline"
    assert missed["source_pins"] is None
    assert missed["cutoff"]["actual_cutoff_at"] is None
    assert missed["cutoff"]["reconciled_at"] == "2026-08-18T04:50:00Z"


def test_pending_prepared_seal_proves_capacity_recheck_and_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    original_boundary = accrual._publish_boundary

    def crash_on_pending_seal(stage: str, path: Path) -> None:
        if stage == "temporary_fsynced" and path.parent.name == "prepared_sessions":
            raise InjectedDurabilityCrash("pending prepared seal")

    monkeypatch.setattr(accrual, "_publish_boundary", crash_on_pending_seal)
    with pytest.raises(InjectedDurabilityCrash, match="pending prepared seal"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-18T04:35:00Z",
        )
    monkeypatch.setattr(accrual, "_publish_boundary", original_boundary)
    assert len(list((experience / "prepared_sessions").glob(".*.pending"))) == 1

    monkeypatch.setattr(
        accrual,
        "_capacity_preflight",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("durable pending seal repeated capacity preflight")
        ),
    )
    resumed = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:50:00Z",
    )
    assert len(resumed.opportunity_ids) == 1
    opportunity = _read(
        experience / "opportunities" / "2026-08-17.json"
    )
    assert opportunity["disposition"] == "admitted"
    assert opportunity["sealed_at"] == "2026-08-18T04:35:00Z"


def test_timely_abstention_is_never_overwritten_by_later_source_or_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch, technical=False
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:35:00Z",
    )
    path = experience / "opportunities" / "2026-08-17.json"
    abstained_body = path.read_bytes()
    abstained = json.loads(abstained_body)
    assert abstained["disposition"] == "abstained"
    assert abstained["reason"] == "technical_session_absent"
    _capture_technical(
        tmp_path,
        monkeypatch,
        session=ACTIVATION,
        observed_at=datetime(2026, 8, 18, 4, 40, tzinfo=timezone.utc),
        end_close=120.0,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:50:00Z",
    )
    assert path.read_bytes() == abstained_body


def test_obligations_are_registration_and_calendar_derived_not_timer_presence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(tmp_path, monkeypatch)
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T05:00:00Z",
    )
    due = accrual.expected_sessions_due(
        datetime(2026, 8, 25, 5, tzinfo=timezone.utc)
    )
    assert [item.isoformat() for item in due] == [
        "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20",
        "2026-08-21", "2026-08-24",
    ]
    assert sorted(path.stem for path in (experience / "opportunities").glob("*.json")) == [
        item.isoformat() for item in due
    ]
    population_head = _read(experience / "population_HEAD.json")
    population = _read(
        experience / "population_receipts" / f"{population_head['population_receipt_id']}.json"
    )
    assert population["expected_sessions"] == [item.isoformat() for item in due]
    assert population["counts"]["expected"] == len(due)
    assert population["evidence_policy"]["timer_runs_are_census"] is False


def test_outcome_absence_is_append_only_then_late_exact_capture_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(tmp_path, monkeypatch)
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:35:00Z",
    )
    assert not (experience / "outcomes").joinpath(
        _read(experience / "opportunities" / "2026-08-17.json")["opportunity_id"]
    ).exists()
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:31:00Z",
    )
    opportunity = _read(experience / "opportunities" / "2026-08-17.json")
    outcome_dir = experience / "outcomes" / opportunity["opportunity_id"]
    absence = _read(outcome_dir / "000001.json")
    assert absence["status"] == "unavailable"
    assert absence["reason"] == "target_capture_absent_at_maturity_cutoff"
    assert absence["target_generation_pin"] is not None
    assert absence["target_capture"] is None
    assert absence["measurement"] is None
    assert absence["absence_fact"] == {
        "kind": "missing",
        "reason": "target_capture_absent_at_maturity_cutoff",
        "observed_at": "2026-08-25T04:31:00Z",
    }
    assert absence["claims"] == {
        "external_clock_authenticated": False,
        "aba_resistance_authenticated": False,
        "calendar_session_derivation_authenticated": True,
        "target_generation_pin_authenticated": True,
    }
    target_session = date(2026, 8, 24)
    _capture_technical(
        tmp_path,
        monkeypatch,
        session=target_session,
        observed_at=datetime(2026, 8, 25, 4, 35, tzinfo=timezone.utc),
        end_close=150.0,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:40:00Z",
    )
    assert (outcome_dir / "000001.json").read_bytes() == json.dumps(
        absence, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    resolution = _read(outcome_dir / "000002.json")
    assert resolution["previous_outcome_revision_id"] == absence["outcome_revision_id"]
    assert resolution["status"] == "observed"
    assert resolution["revision_kind"] == "late_source_resolution"
    assert resolution["reason"] == "late_owner_source_resolution_after_unavailable"
    assert resolution["measurement"]["target"] == "spy.raw_unadjusted_daily_aggregate_close_ratio"
    assert resolution["measurement"]["formula"] == "target_capture.feature.state.end_close/sealed_anchor_capture.feature.state.end_close"
    assert resolution["measurement"]["close_ratio_q18"] == "1.250000000000000000"
    assert resolution["anchor_mark"]["end_close_binary64_hex"] == (120.0).hex()
    assert resolution["target_mark"]["end_close_binary64_hex"] == (150.0).hex()
    assert "value" not in resolution["measurement"]
    registry, schemas = _schema_registry()
    validator = Draft202012Validator(
        schemas["spy_experience_outcome_revision.v1.schema.json"], registry=registry
    )
    validator.validate(absence)
    validator.validate(resolution)

    initial_tie = copy.deepcopy(absence)
    initial_tie["status"] = "censored"
    initial_tie["revision_kind"] = "initial_maturity_censoring"
    initial_tie["reason"] = "target_capture_clock_tie_censored"
    initial_tie["absence_fact"] = {
        "kind": "censored",
        "reason": "target_capture_clock_tie_censored",
        "observed_at": absence["maturity_cutoff"]["actual_pin_observed_at"],
    }
    initial_tie["target_generation_progress"] = {
        "generation_id": absence["target_generation_pin"]["generation_id"],
        "consumed_capture_ids": [
            "mmactualcapture_" + "b" * 64,
            "mmactualcapture_" + "c" * 64,
        ],
        "current_group": [
            {
                "capture_id": "mmactualcapture_" + "b" * 64,
                "first_observed_at": "2026-08-25T04:30:00Z",
            },
            {
                "capture_id": "mmactualcapture_" + "c" * 64,
                "first_observed_at": "2026-08-25T04:30:00Z",
            },
        ],
    }
    initial_tie = _rehash(
        initial_tie,
        field="outcome_revision_id",
        prefix="mmspyexpout_",
    )
    accrual.validate_outcome_revision(
        initial_tie,
        registration=accrual.load_registration(ROOT),
        opportunity=opportunity,
    )
    validator.validate(initial_tie)
    tie_with_target = copy.deepcopy(initial_tie)
    tie_with_target["target_capture"] = copy.deepcopy(resolution["target_capture"])
    tie_with_target = _rehash(
        tie_with_target,
        field="outcome_revision_id",
        prefix="mmspyexpout_",
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="cannot carry a selected target",
    ):
        accrual.validate_outcome_revision(
            tie_with_target,
            registration=accrual.load_registration(ROOT),
            opportunity=opportunity,
        )

    rehashed_initial_clock_exploits: list[dict] = []
    changed = copy.deepcopy(absence)
    changed["absence_fact"]["observed_at"] = "2026-08-25T04:32:00Z"
    rehashed_initial_clock_exploits.append(changed)
    changed = copy.deepcopy(absence)
    changed["target_generation_pin"]["pin_observed_at"] = (
        "2026-08-25T04:46:00Z"
    )
    rehashed_initial_clock_exploits.append(changed)
    changed = copy.deepcopy(absence)
    changed["maturity_cutoff"]["actual_pin_observed_at"] = (
        "2026-08-25T04:32:00Z"
    )
    rehashed_initial_clock_exploits.append(changed)
    for exploit in rehashed_initial_clock_exploits:
        exploit = _rehash(
            exploit,
            field="outcome_revision_id",
            prefix="mmspyexpout_",
        )
        with pytest.raises(accrual.MarketMemoryExperienceStoreError):
            accrual.validate_outcome_revision(
                exploit,
                registration=accrual.load_registration(ROOT),
                opportunity=opportunity,
            )

    hostile_initials = []
    changed = copy.deepcopy(absence)
    changed["revision_kind"] = "initial_maturity_observation"
    hostile_initials.append(changed)
    changed = copy.deepcopy(absence)
    changed["reason"] = "target_capture_clock_tie_censored"
    hostile_initials.append(changed)
    changed = copy.deepcopy(absence)
    changed["claims"]["external_clock_authenticated"] = True
    hostile_initials.append(changed)
    changed = copy.deepcopy(absence)
    changed["claims"]["target_generation_pin_authenticated"] = False
    hostile_initials.append(changed)
    for changed in hostile_initials:
        changed = _rehash(
            changed,
            field="outcome_revision_id",
            prefix="mmspyexpout_",
        )
        with pytest.raises(accrual.MarketMemoryExperienceStoreError):
            accrual.validate_outcome_revision(
                changed,
                registration=accrual.load_registration(ROOT),
                opportunity=opportunity,
            )

    hostile_later = copy.deepcopy(resolution)
    hostile_later["revision_kind"] = "source_correction"
    hostile_later["reason"] = "later_owner_source_revision"
    hostile_later = _rehash(
        hostile_later,
        field="outcome_revision_id",
        prefix="mmspyexpout_",
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="status/kind/reason matrix",
    ):
        accrual.validate_outcome_revision(
            hostile_later,
            registration=accrual.load_registration(ROOT),
            opportunity=opportunity,
            previous=absence,
            history=[absence],
        )

    equal_clock = copy.deepcopy(resolution)
    equal_clock["appended_at"] = absence["appended_at"]
    equal_clock["target_generation_pin"]["pin_observed_at"] = absence["appended_at"]
    equal_clock = _rehash(
        equal_clock,
        field="outcome_revision_id",
        prefix="mmspyexpout_",
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
    ):
        accrual.validate_outcome_revision(
            equal_clock,
            registration=accrual.load_registration(ROOT),
            opportunity=opportunity,
            previous=absence,
            history=[absence],
        )

    plus_100ms = copy.deepcopy(resolution)
    plus_100ms["appended_at"] = "2026-08-25T04:35:00.100000Z"
    plus_100ms["target_generation_pin"]["pin_observed_at"] = (
        "2026-08-25T04:35:00.100000Z"
    )
    plus_100ms = _rehash(
        plus_100ms,
        field="outcome_revision_id",
        prefix="mmspyexpout_",
    )
    accrual.validate_outcome_revision(
        plus_100ms,
        registration=accrual.load_registration(ROOT),
        opportunity=opportunity,
        previous=absence,
        history=[absence],
    )


def test_maturity_owner_window_miss_is_persisted_and_nullable_only_where_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(tmp_path, monkeypatch)
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:35:00Z",
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:50:00Z",
    )
    opportunity = _read(experience / "opportunities" / "2026-08-17.json")
    outcome = _read(experience / "outcomes" / opportunity["opportunity_id"] / "000001.json")
    assert outcome["status"] == "censored"
    assert outcome["reason"] == "maturity_owner_window_missed"
    assert outcome["target_generation_pin"] is None
    assert outcome["maturity_cutoff"]["actual_pin_observed_at"] is None
    assert outcome["absence_fact"]["observed_at"] == "2026-08-25T04:50:00Z"
    assert outcome["claims"] == {
        "external_clock_authenticated": False,
        "aba_resistance_authenticated": False,
        "calendar_session_derivation_authenticated": True,
        "target_generation_pin_authenticated": False,
    }
    forged = copy.deepcopy(outcome)
    forged["claims"]["target_generation_pin_authenticated"] = True
    forged = _rehash(
        forged, field="outcome_revision_id", prefix="mmspyexpout_"
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="claims disagree",
    ):
        accrual.validate_outcome_revision(
            forged,
            registration=accrual.load_registration(ROOT),
            opportunity=opportunity,
        )


def test_in_window_owner_pin_processed_after_deadline_remains_observed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:35:00Z",
    )
    _capture_technical(
        tmp_path,
        monkeypatch,
        session=date(2026, 8, 24),
        observed_at=datetime(2026, 8, 25, 4, 34, tzinfo=timezone.utc),
        end_close=150.0,
    )
    registration = accrual.load_registration(ROOT)
    reader, pins = accrual._pin_owners(trusted_root, technical_root)
    view = accrual._observe_run_owner_view(
        experience,
        registration=registration,
        trusted_root=trusted_root,
        reader=reader,
        initial_pins=pins,
        technical_root=technical_root,
        clock=_clock("2026-08-25T04:35:00Z"),
        retry_deadline=datetime(2026, 8, 25, 4, 35, tzinfo=timezone.utc),
        sleeper=lambda _seconds: None,
    )
    observation = accrual._target_observation_from_run(
        view, target_session=date(2026, 8, 24)
    )
    opportunity = _read(experience / "opportunities" / "2026-08-17.json")
    outcome_ids = accrual._accrue_outcomes(
        experience,
        registration=registration,
        opportunity=opportunity,
        now=datetime(2026, 8, 25, 4, 46, tzinfo=timezone.utc),
        observation=observation,
        writer_commit=COMMIT,
    )
    assert len(outcome_ids) == 1
    outcome = _read(
        experience / "outcomes" / opportunity["opportunity_id"] / "000001.json"
    )
    assert outcome["status"] == "observed"
    assert outcome["target_generation_pin"]["pin_observed_at"] == (
        "2026-08-25T04:35:00Z"
    )
    assert outcome["appended_at"] == "2026-08-25T04:46:00Z"


def test_observed_then_equal_clock_correction_is_censored_then_later_resolves_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:35:00Z",
    )
    target_session = date(2026, 8, 24)
    _capture_technical(
        tmp_path,
        monkeypatch,
        session=target_session,
        observed_at=datetime(2026, 8, 25, 4, 30, tzinfo=timezone.utc),
        end_close=150.0,
    )
    first = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:31:00Z",
    )
    assert len(first.outcome_revision_ids) == 1
    opportunity = _read(experience / "opportunities" / "2026-08-17.json")
    outcome_dir = experience / "outcomes" / opportunity["opportunity_id"]
    initial = _read(outcome_dir / "000001.json")
    assert initial["status"] == "observed"

    for close in (151.0, 152.0):
        _capture_technical(
            tmp_path,
            monkeypatch,
            session=target_session,
            observed_at=datetime(2026, 8, 25, 4, 35, tzinfo=timezone.utc),
            end_close=close,
        )
    tied = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:36:00Z",
    )
    assert len(tied.outcome_revision_ids) == 1
    censor = _read(outcome_dir / "000002.json")
    assert censor["status"] == "censored"
    assert censor["revision_kind"] == "source_correction_censoring"
    assert censor["reason"] == "later_owner_capture_clock_tie_censored"
    assert censor["target_capture"] is None
    assert censor["previous_outcome_revision_id"] == initial["outcome_revision_id"]

    _capture_technical(
        tmp_path,
        monkeypatch,
        session=target_session,
        observed_at=datetime(2026, 8, 25, 4, 40, tzinfo=timezone.utc),
        end_close=153.0,
    )
    resolved = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:41:00Z",
    )
    assert len(resolved.outcome_revision_ids) == 1
    resolution = _read(outcome_dir / "000003.json")
    assert resolution["status"] == "observed"
    assert resolution["revision_kind"] == "source_correction"
    assert resolution["reason"] == "later_owner_source_revision"
    assert resolution["target_mark"]["end_close_binary64_hex"] == (153.0).hex()
    assert resolution["previous_outcome_revision_id"] == censor["outcome_revision_id"]

    frozen = {path.name: path.read_bytes() for path in outcome_dir.glob("*.json")}
    repeated = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:42:00Z",
    )
    assert repeated.outcome_revision_ids == ()
    assert {path.name: path.read_bytes() for path in outcome_dir.glob("*.json")} == frozen

    # A descendant owner generation may publish a newly discovered same-session
    # capture whose owner clock is older than the consumed boundary.  That fact
    # advances the chain as an integrity censor instead of bricking the census.
    registration = accrual.load_registration(ROOT)
    chain = accrual._load_outcome_chain(
        experience, registration=registration, opportunity=opportunity
    )
    previous_pin = copy.deepcopy(chain[-1]["target_generation_pin"])
    reordered_reference = copy.deepcopy(chain[-1]["target_capture"])
    reordered_reference.update(
        {
            "capture_id": "mmactualcapture_" + "d" * 64,
            "revision_id": "mmtechrev_" + "d" * 64,
            "source_observation_id": "mmtechsrc_" + "d" * 64,
            "snapshot_id": "mmtechsnap_" + "d" * 64,
            "first_observed_at": "2026-08-25T04:39:00Z",
            "spy_parquet_sha256": "d" * 64,
            **accrual._binary64_mark(154.0, field="reordered fixture"),
        }
    )
    next_pin = {
        **previous_pin,
        "generation_id": "mmactualgeneration_" + "e" * 64,
        "generation_sha256": "e" * 64,
        "capture_count": previous_pin["capture_count"] + 1,
        "pin_observed_at": "2026-08-26T04:35:00Z",
    }
    current_technical_pin = (
        technical_store.pin_technical_actual_output_generation(technical_root)
    )
    existing_target_candidates = accrual._technical_candidates(
        technical_root,
        current_technical_pin,
        session=target_session,
    )
    reordered = accrual._append_later_target_revisions(
        experience,
        registration=registration,
        opportunity=opportunity,
        chain=chain,
        observation=accrual._TargetObservation(
            pin_observed_at="2026-08-26T04:35:00Z",
            stable=True,
            generation_pin=next_pin,
            candidates=(
                *existing_target_candidates,
                accrual._TechnicalCandidate(
                    reference=reordered_reference, end_close=154.0
                ),
            ),
            clock_tie=False,
            generation_capture_ordinals={
                # Cumulative technical generations are canonically re-sorted.
                # A correction to this old target session can therefore sit
                # before many already-published later-session captures.
                reordered_reference["capture_id"]: 0
            },
            ancestry_generation_ids=(previous_pin["generation_id"],),
        ),
        appended_at=datetime(2026, 8, 26, 4, 35, tzinfo=timezone.utc),
        writer_commit=COMMIT,
    )
    assert len(reordered) == 1
    assert reordered[0]["status"] == "censored"
    assert reordered[0]["reason"] == (
        "later_owner_capture_order_integrity_censored"
    )
    assert reordered[0]["previous_outcome_revision_id"] == (
        chain[-1]["outcome_revision_id"]
    )


@pytest.mark.parametrize("crash_after_revision", [1, 2])
def test_first_maturity_pin_consumes_full_candidate_suffix_after_each_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_after_revision: int,
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:35:00Z",
    )
    target_session = date(2026, 8, 24)
    for index, close in enumerate((150.0, 151.0, 152.0), start=1):
        _capture_technical(
            tmp_path,
            monkeypatch,
            session=target_session,
            observed_at=datetime(
                2026, 8, 25, 4, 30 + index, tzinfo=timezone.utc
            ),
            end_close=close,
        )

    original_write = accrual._write_outcome
    writes = 0

    def crash_after_durable_revision(root, row):
        nonlocal writes
        original_write(root, row)
        writes += 1
        if writes == crash_after_revision:
            raise RuntimeError("crash after durable outcome revision")

    monkeypatch.setattr(accrual, "_write_outcome", crash_after_durable_revision)
    with pytest.raises(RuntimeError, match="durable outcome"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-25T04:40:00Z",
        )
    monkeypatch.setattr(accrual, "_write_outcome", original_write)
    resumed = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:41:00Z",
    )
    assert len(resumed.outcome_revision_ids) == 3 - crash_after_revision
    opportunity = _read(experience / "opportunities" / "2026-08-17.json")
    outcome_directory = experience / "outcomes" / opportunity["opportunity_id"]
    rows = [
        _read(outcome_directory / f"{number:06d}.json")
        for number in range(1, 4)
    ]
    assert [row["target_mark"]["end_close_binary64_hex"] for row in rows] == [
        value.hex() for value in (150.0, 151.0, 152.0)
    ]
    consumed = [
        row["target_generation_progress"]["consumed_capture_ids"]
        for row in rows
    ]
    assert [len(value) for value in consumed] == [1, 2, 3]
    assert consumed[1][:1] == consumed[0]
    assert consumed[2][:2] == consumed[1]
    frozen = {
        path.name: path.read_bytes()
        for path in outcome_directory.glob("*.json")
    }
    repeated = _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:42:00Z",
    )
    assert repeated.outcome_revision_ids == ()
    assert {
        path.name: path.read_bytes()
        for path in outcome_directory.glob("*.json")
    } == frozen


def test_population_exposes_completeness_coverage_and_finite_auditability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(tmp_path, monkeypatch)
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:50:00Z",
    )
    head = _read(experience / "population_HEAD.json")
    receipt = _read(
        experience / "population_receipts" / f"{head['population_receipt_id']}.json"
    )
    assert receipt["counts"] == {
        "expected": 1, "recorded": 1, "admitted": 0, "abstained": 0,
        "missed": 1, "matured_admitted": 0, "outcome_receipted": 0,
        "outcome_observed": 0, "outcome_unavailable": 0,
        "outcome_censored": 0, "outcome_revision_count": 0,
        "pending_admitted": 0, "corrected_outcome_chains": 0,
        "scoreable": 0, "timely": 0, "projected_timely": 0,
    }
    assert receipt["coverage"]["opportunity_completeness_q18"] == "1.000000000000000000"
    assert receipt["owner_auditability"]["status"] == "within_v1_auditability_window"
    assert receipt["owner_auditability"]["checkpoint_migration_required_before_owner_count"] == 384
    assert receipt["owner_auditability"]["indefinite_v1_auditability"] is False
    assert receipt["owner_generation_refs"]["pin_observed_at"] == "2026-08-18T04:50:00Z"
    assert receipt["owner_generation_refs"]["trusted_generation"]["capture_count"] == 1
    assert receipt["owner_generation_refs"]["technical_generation"]["capture_count"] == 1
    assert receipt["terminal"]["status"] == "open"
    assert receipt["complete"] is False
    assert receipt["claims"] == {
        "external_clock_authenticated": False,
        "aba_resistance_authenticated": False,
        "calendar_session_derivation_authenticated": True,
        "coverage_derived_from_authenticated_ledger_rows": True,
    }
    assert accrual._auditability_status(320, 1) == "warning_checkpoint_migration_due"
    assert accrual._auditability_status(383, 1) == "warning_checkpoint_migration_due"
    assert accrual._auditability_status(384, 1) == "critical_checkpoint_migration_required"
    registry, schemas = _schema_registry()
    Draft202012Validator(
        schemas["spy_experience_population_receipt.v1.schema.json"], registry=registry
    ).validate(receipt)
    forged = copy.deepcopy(receipt)
    forged["claims"]["external_clock_authenticated"] = True
    forged = _rehash(
        forged,
        field="population_receipt_id",
        prefix="mmspyexppop_",
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="binding drift",
    ):
        accrual.validate_population_receipt(
            forged,
            registration=accrual.load_registration(ROOT),
            expected_sessions=[ACTIVATION],
            opportunities=[
                _read(experience / "opportunities" / "2026-08-17.json")
            ],
        )

    registration = accrual.load_registration(ROOT)
    opportunity = _read(experience / "opportunities" / "2026-08-17.json")
    second_session = date(2026, 8, 18)
    extra = accrual._missed_opportunity(
        registration,
        session=second_session,
        reconciled_at=accrual._window(second_session)[1] + timedelta(seconds=1),
        writer_commit=COMMIT,
    )
    hostile_arguments = [
        ([ACTIVATION], [opportunity, opportunity]),
        ([ACTIVATION], [opportunity, extra]),
        ([ACTIVATION, second_session], [extra, opportunity]),
    ]
    for expected, rows in hostile_arguments:
        with pytest.raises(
            accrual.MarketMemoryExperienceStoreError,
            match="duplicated, extra, or permuted",
        ):
            accrual.validate_population_receipt(
                receipt,
                registration=registration,
                expected_sessions=expected,
                opportunities=rows,
            )
    forged_coverage = copy.deepcopy(receipt)
    forged_coverage["coverage"]["opportunity_completeness_q18"] = (
        "2.000000000000000000"
    )
    forged_coverage = _rehash(
        forged_coverage,
        field="population_receipt_id",
        prefix="mmspyexppop_",
    )
    with pytest.raises(accrual.MarketMemoryExperienceStoreError):
        accrual.validate_population_receipt(
            forged_coverage,
            registration=registration,
            expected_sessions=[ACTIVATION],
            opportunities=[opportunity],
        )
    forged_revision_count = copy.deepcopy(receipt)
    forged_revision_count["counts"]["outcome_revision_count"] += 1
    forged_revision_count = _rehash(
        forged_revision_count,
        field="population_receipt_id",
        prefix="mmspyexppop_",
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="exact chain census",
    ):
        accrual.validate_population_receipt(
            forged_revision_count,
            registration=registration,
            expected_sessions=[ACTIVATION],
            opportunities=[opportunity],
        )


def test_population_writer_rejects_local_clock_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:35:00Z",
    )
    monkeypatch.setattr(
        accrual, "_same_population_state", lambda *_args: False
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="strictly later writer clock",
    ):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-18T04:34:00Z",
        )


def test_final_terminal_marker_makes_every_later_invocation_a_pre_owner_no_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    registration = accrual.load_registration(ROOT)
    _reader, pins = accrual._pin_owners(trusted_root, technical_root)
    sessions = nyse_calendar.sessions_between(
        accrual.ACTIVATION_SESSION, accrual.SUNSET_SESSION
    )
    opportunities = [
        accrual._missed_opportunity(
            registration,
            session=session,
            reconciled_at=accrual._window(session)[1] + timedelta(seconds=1),
            writer_commit=COMMIT,
        )
        for session in sessions
    ]
    for opportunity in opportunities:
        accrual._write_opportunity(experience, opportunity)
    missed_terminal = accrual._new_population_receipt(
        registration,
        root=experience,
        expected_sessions=sessions,
        opportunities=opportunities,
        owner_pins=pins,
        owner_pin_observed_at="2027-03-02T04:35:00Z",
        terminal_receipt={
            "disposition": "terminal_owner_window_missed",
            "observed_at": "2027-03-03T04:46:00Z",
            "technical_generation_pin": None,
        },
        observed_at="2027-03-03T04:46:00Z",
        writer_commit=COMMIT,
    )
    assert missed_terminal["complete"] is True
    assert missed_terminal["terminal"]["receipt"]["technical_generation_pin"] is None
    terminal_clock = "2027-03-03T04:35:00Z"
    technical_generation_pin = {
        **accrual._generation_ref(pins.technical, technical=True),
        "pin_observed_at": terminal_clock,
        "selection": "owner_observed_revision_chain.v1",
        "subject": copy.deepcopy(accrual._SUBJECT),
        "calendar": copy.deepcopy(accrual._CALENDAR),
    }
    receipt = accrual._new_population_receipt(
        registration,
        root=experience,
        expected_sessions=sessions,
        opportunities=opportunities,
        owner_pins=pins,
        owner_pin_observed_at=terminal_clock,
        terminal_receipt={
            "disposition": "stable_terminal_generation_observed",
            "observed_at": terminal_clock,
            "technical_generation_pin": technical_generation_pin,
        },
        observed_at=terminal_clock,
        writer_commit=COMMIT,
    )
    assert receipt["complete"] is True
    assert receipt["terminal"]["status"] == "sealed"
    accrual._write_population_receipt(experience, receipt)
    marker = accrual._write_terminal_marker(
        experience,
        registration=registration,
        population_receipt=receipt,
    )
    _technical_rows, technical_view = accrual._prepare_technical_view(
        experience,
        registration=registration,
        technical_root=technical_root,
        pin=pins.technical,
        trusted_pin=pins.trusted,
        pair_observed_at=terminal_clock,
    )
    assert technical_view is not None
    accrual._publish_technical_view(experience, technical_view)
    assert (experience / "TERMINAL.json").is_file()
    marker_body = (experience / "TERMINAL.json").read_bytes()
    installation_verification = accrual.verify_experience_installation(
        ROOT,
        experience_root=experience,
        expected_writer_commit=COMMIT,
    )
    assert installation_verification["verified"] is True
    assert installation_verification["claims"][
        "external_clock_authenticated"
    ] is False
    assert installation_verification["claims"][
        "aba_resistance_authenticated"
    ] is False
    verification_before = {
        str(path.relative_to(experience)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in experience.rglob("*")
        if path.is_file()
    }
    verified_terminal = accrual.verify_terminal_ledger(
        ROOT,
        experience_root=experience,
        expected_writer_commit=COMMIT,
    )
    assert verified_terminal is not None
    assert verified_terminal["terminal_marker_id"] == marker["terminal_marker_id"]
    assert verified_terminal["denominator_and_maturity_receipts_complete"] is True
    assert verified_terminal["final_source_revision_census_authenticated"] is True
    assert {
        str(path.relative_to(experience)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in experience.rglob("*")
        if path.is_file()
    } == verification_before

    def forbidden_owner(*_args, **_kwargs):  # pragma: no cover - contract guard
        raise AssertionError("terminal recovery consulted an owner store")

    # Crash after the final population but before marker publication resumes
    # the exact final receipt without a new clock or owner read.
    (experience / "TERMINAL.json").unlink()
    monkeypatch.setattr(accrual, "_pin_owners", forbidden_owner)
    recovered = accrual.accrue_spy_experience(
        ROOT,
        experience_root=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        writer_commit=COMMIT,
        clock=forbidden_owner,
        sleeper=forbidden_owner,
    )
    assert recovered.population_receipt_id == receipt["population_receipt_id"]
    assert (experience / "TERMINAL.json").read_bytes() == marker_body

    def snapshot() -> dict[str, tuple[bytes, int, int]]:
        return {
            str(path.relative_to(experience)): (
                path.read_bytes(),
                path.stat().st_size,
                path.stat().st_mtime_ns,
            )
            for path in sorted(experience.rglob("*"))
            if path.is_file()
        }

    frozen = snapshot()

    def forbidden(*_args, **_kwargs):  # pragma: no cover - contract guard
        raise AssertionError("terminal invocation crossed pre-owner no-write fence")

    monkeypatch.setattr(accrual, "_pin_owners", forbidden)
    monkeypatch.setattr(accrual.fcntl, "flock", forbidden)
    for _ in range(2):
        result = accrual.accrue_spy_experience(
            ROOT,
            experience_root=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            writer_commit=COMMIT,
            clock=forbidden,
            sleeper=forbidden,
        )
        assert result.opportunity_ids == ()
        assert result.outcome_revision_ids == ()
        assert result.population_receipt_id == marker["population_receipt_id"]
        assert snapshot() == frozen

    # The terminal verifier authenticates the local technical-view cache as a
    # generation-bound prefix chain.  A self-consistent HEAD digest cannot
    # name a different generation than its target view.
    assert accrual.verify_terminal_ledger(
        ROOT, experience_root=experience
    ) is not None
    technical_head_path = experience / "technical_view_HEAD.json"
    technical_head_body = technical_head_path.read_bytes()
    forged_technical_head = json.loads(technical_head_body)
    forged_technical_head["technical_generation_id"] = (
        "mmactualgeneration_" + "f" * 64
    )
    technical_head_path.write_bytes(
        accrual._canonical_bytes(forged_technical_head)
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="technical-view HEAD generation drift",
    ):
        accrual.verify_terminal_ledger(ROOT, experience_root=experience)
    technical_head_path.write_bytes(technical_head_body)

    # Even a self-hashed fabricated population plus self-hashed marker cannot
    # replace the immutable opportunity census and suppress future audits.
    population_head_path = experience / "population_HEAD.json"
    population_head_body = population_head_path.read_bytes()
    population_head = json.loads(population_head_body)
    population_path = (
        experience
        / "population_receipts"
        / f"{population_head['population_receipt_id']}.json"
    )
    fabricated = _read(population_path)
    fabricated["opportunities"][0]["opportunity_id"] = (
        "mmspyexpopp_" + "f" * 64
    )
    fabricated = _rehash(
        fabricated,
        field="population_receipt_id",
        prefix="mmspyexppop_",
    )
    fabricated_body = accrual._canonical_bytes(fabricated)
    fabricated_path = (
        experience
        / "population_receipts"
        / f"{fabricated['population_receipt_id']}.json"
    )
    fabricated_path.write_bytes(fabricated_body)
    fabricated_head = copy.deepcopy(population_head)
    fabricated_head.update(
        {
            "population_receipt_id": fabricated["population_receipt_id"],
            "population_receipt_sha256": accrual._digest(fabricated_body),
            "population_receipt_bytes": len(fabricated_body),
        }
    )
    population_head_path.write_bytes(accrual._canonical_bytes(fabricated_head))
    fabricated_marker = copy.deepcopy(marker)
    fabricated_marker.update(
        {
            "population_receipt_id": fabricated["population_receipt_id"],
            "population_receipt_sha256": accrual._digest(fabricated_body),
            "population_receipt_bytes": len(fabricated_body),
        }
    )
    fabricated_marker = _rehash(
        fabricated_marker,
        field="terminal_marker_id",
        prefix="mmspyexpterminal_",
    )
    (experience / "TERMINAL.json").write_bytes(
        accrual._canonical_bytes(fabricated_marker)
    )
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="opportunity census",
    ):
        accrual.verify_terminal_ledger(ROOT, experience_root=experience)
    (experience / "TERMINAL.json").write_bytes(marker_body)
    population_head_path.write_bytes(population_head_body)
    fabricated_path.unlink()

    # The path marker is not a liveness latch.  Deleting one immutable census
    # row makes the read-only verifier reject the supposedly complete ledger.
    deleted_path = experience / "opportunities" / "2026-08-17.json"
    deleted_body = deleted_path.read_bytes()
    deleted_path.unlink()
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="opportunity inventory|terminal opportunity",
    ):
        accrual.verify_terminal_ledger(ROOT, experience_root=experience)
    deleted_path.write_bytes(deleted_body)
    orphan = (
        experience
        / "prepared_objects"
        / ("mmspyexpprep_" + "f" * 64 + ".json")
    )
    orphan.write_text("{}")
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="prepared-object inventory",
    ):
        accrual.verify_terminal_ledger(ROOT, experience_root=experience)


def test_no_owner_pair_ever_still_seals_finite_local_denominator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )

    def owner_absent(*_args, **_kwargs):
        raise FileNotFoundError("owner HEAD absent")

    monkeypatch.setattr(accrual, "_pin_owners", owner_absent)
    result = accrual.accrue_spy_experience(
        ROOT,
        experience_root=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        writer_commit=COMMIT,
        clock=_clock("2027-03-03T04:46:00Z"),
        sleeper=lambda _seconds: None,
    )
    assert len(result.opportunity_ids) == accrual.PILOT_EXPECTED_SESSIONS
    opportunities = sorted((experience / "opportunities").glob("*.json"))
    assert len(opportunities) == accrual.PILOT_EXPECTED_SESSIONS
    assert {
        _read(path)["reason"] for path in opportunities
    } == {"owner_unavailable_by_deadline"}
    marker = _read(experience / "TERMINAL.json")
    population = _read(
        experience
        / "population_receipts"
        / f"{marker['population_receipt_id']}.json"
    )
    assert population["owner_generation_refs"] is None
    assert population["terminal"]["receipt"]["disposition"] == (
        "no_authenticated_owner_pair_ever"
    )
    assert population["terminal"][
        "denominator_and_maturity_receipts_complete"
    ] is True
    assert population["terminal"][
        "final_source_revision_census_authenticated"
    ] is False
    assert population["decision_state_diagnostics"][
        "owner_unavailable_failure_fact_count"
    ] == accrual.PILOT_EXPECTED_SESSIONS
    verified = accrual.verify_terminal_ledger(
        ROOT, experience_root=experience
    )
    assert verified is not None
    assert verified["final_source_revision_census_authenticated"] is False

    frozen = {
        str(path.relative_to(experience)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in experience.rglob("*")
        if path.is_file()
    }
    repeated = accrual.accrue_spy_experience(
        ROOT,
        experience_root=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        writer_commit=COMMIT,
        clock=lambda: (_ for _ in ()).throw(
            AssertionError("terminal no-pair fast path sampled a clock")
        ),
        sleeper=lambda _seconds: (_ for _ in ()).throw(
            AssertionError("terminal no-pair fast path slept")
        ),
    )
    assert repeated.population_receipt_id == marker["population_receipt_id"]
    assert {
        str(path.relative_to(experience)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in experience.rglob("*")
        if path.is_file()
    } == frozen

    technical_pin = technical_store.pin_technical_actual_output_generation(
        technical_root,
        maximum_capture_count=accrual.MAX_OWNER_GENERATION_CAPTURES,
    )
    trusted_pin = trusted.TrustedFileAsKnownAtReader(
        trusted_root
    ).read_pinned_generation(
        maximum_capture_count=accrual.MAX_OWNER_GENERATION_CAPTURES
    )
    _rows, orphan_view = accrual._prepare_technical_view(
        experience,
        registration=accrual.load_registration(ROOT),
        technical_root=technical_root,
        pin=technical_pin,
        trusted_pin=trusted_pin,
        pair_observed_at="2027-03-03T04:35:00Z",
    )
    assert orphan_view is not None
    accrual._publish_technical_view(experience, orphan_view)
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="no ledger owner reference",
    ):
        accrual.verify_terminal_ledger(ROOT, experience_root=experience)


def test_terminal_recovers_durable_opportunity_pair_after_population_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    original_boundary = accrual._publish_boundary

    def crash_after_opportunity_directory_fsync(stage: str, path: Path) -> None:
        if (
            stage == "final_directory_fsynced"
            and path.parent.name == "opportunities"
        ):
            raise InjectedDurabilityCrash(
                "opportunity durable before population publication"
            )

    monkeypatch.setattr(
        accrual, "_publish_boundary", crash_after_opportunity_directory_fsync
    )
    with pytest.raises(InjectedDurabilityCrash, match="before population"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-18T04:35:00Z",
        )
    monkeypatch.setattr(accrual, "_publish_boundary", original_boundary)
    assert not (experience / "population_HEAD.json").exists()
    assert (experience / "opportunities" / "2026-08-17.json").is_file()

    def owner_absent(*_args, **_kwargs):
        raise FileNotFoundError("owner HEAD absent after durable opportunity")

    monkeypatch.setattr(accrual, "_pin_owners", owner_absent)
    accrual.accrue_spy_experience(
        ROOT,
        experience_root=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        writer_commit=COMMIT,
        clock=_clock("2027-03-03T04:46:00Z"),
        sleeper=lambda _seconds: None,
    )
    marker = _read(experience / "TERMINAL.json")
    population = _read(
        experience
        / "population_receipts"
        / f"{marker['population_receipt_id']}.json"
    )
    assert population["owner_generation_refs"] is not None
    assert population["terminal"]["receipt"]["disposition"] == (
        "terminal_owner_window_missed"
    )
    assert population["terminal"][
        "final_source_revision_census_authenticated"
    ] is False
    assert accrual.verify_terminal_ledger(
        ROOT, experience_root=experience
    ) is not None


@pytest.mark.parametrize(
    ("stage", "path_kind"),
    [
        ("temporary_fsynced", "technical_view"),
        ("final_directory_fsynced", "technical_view"),
        ("temporary_fsynced", "technical_view_head"),
    ],
)
def test_terminal_recovers_durable_technical_pair_after_owner_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    path_kind: str,
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    original_boundary = accrual._publish_boundary

    def crash_at_view_boundary(observed_stage: str, path: Path) -> None:
        matches = (
            path.parent.name == "technical_views"
            if path_kind == "technical_view"
            else path.name == "technical_view_HEAD.json"
        )
        if observed_stage == stage and matches:
            raise InjectedDurabilityCrash("durable technical pair")

    monkeypatch.setattr(accrual, "_publish_boundary", crash_at_view_boundary)
    with pytest.raises(InjectedDurabilityCrash, match="technical pair"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-18T04:35:00Z",
        )
    monkeypatch.setattr(accrual, "_publish_boundary", original_boundary)
    monkeypatch.setattr(
        accrual,
        "_pin_owners",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FileNotFoundError("owners lost after technical-view durability")
        ),
    )
    accrual.accrue_spy_experience(
        ROOT,
        experience_root=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        writer_commit=COMMIT,
        clock=_clock("2027-03-03T04:46:00Z"),
        sleeper=lambda _seconds: None,
    )
    marker = _read(experience / "TERMINAL.json")
    population = _read(
        experience
        / "population_receipts"
        / f"{marker['population_receipt_id']}.json"
    )
    assert population["owner_generation_refs"] is not None
    assert population["terminal"]["receipt"]["disposition"] == (
        "terminal_owner_window_missed"
    )
    assert accrual.verify_terminal_ledger(
        ROOT, experience_root=experience
    ) is not None


def test_terminal_recomputes_every_historical_population_receipt_as_of_its_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:35:00Z",
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-25T04:35:00Z",
    )

    def owner_absent(*_args, **_kwargs):
        raise FileNotFoundError("owner unavailable for terminal census")

    monkeypatch.setattr(accrual, "_pin_owners", owner_absent)
    accrual.accrue_spy_experience(
        ROOT,
        experience_root=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        writer_commit=COMMIT,
        clock=_clock("2027-03-03T04:46:00Z"),
        sleeper=lambda _seconds: None,
    )
    assert accrual.verify_terminal_ledger(
        ROOT, experience_root=experience
    ) is not None

    population_directory = experience / "population_receipts"
    population_head_path = experience / "population_HEAD.json"
    population_head = _read(population_head_path)
    final_path = (
        population_directory
        / f"{population_head['population_receipt_id']}.json"
    )
    final = _read(final_path)
    historical_path = (
        population_directory
        / f"{final['previous_population_receipt_id']}.json"
    )
    historical = _read(historical_path)
    assert historical["latest_outcomes"]

    forged_historical = copy.deepcopy(historical)
    forged_historical["latest_outcomes"][0]["outcome_revision_id"] = (
        "mmspyexpout_" + "f" * 64
    )
    forged_historical = _rehash(
        forged_historical,
        field="population_receipt_id",
        prefix="mmspyexppop_",
    )
    registration = accrual.load_registration(ROOT)
    historical_sessions = [
        date.fromisoformat(value)
        for value in forged_historical["expected_sessions"]
    ]
    historical_opportunities = [
        _read(experience / "opportunities" / f"{session.isoformat()}.json")
        for session in historical_sessions
    ]
    # The forged row is structurally valid in isolation.  Terminal closure
    # must still reject it because the named outcome never existed as of this
    # receipt's own observation clock.
    accrual.validate_population_receipt(
        forged_historical,
        registration=registration,
        expected_sessions=historical_sessions,
        opportunities=historical_opportunities,
    )

    forged_historical_body = accrual._canonical_bytes(forged_historical)
    forged_historical_path = (
        population_directory
        / f"{forged_historical['population_receipt_id']}.json"
    )
    historical_path.unlink()
    forged_historical_path.write_bytes(forged_historical_body)

    forged_final = copy.deepcopy(final)
    forged_final["previous_population_receipt_id"] = forged_historical[
        "population_receipt_id"
    ]
    forged_final = _rehash(
        forged_final,
        field="population_receipt_id",
        prefix="mmspyexppop_",
    )
    forged_final_body = accrual._canonical_bytes(forged_final)
    forged_final_path = (
        population_directory
        / f"{forged_final['population_receipt_id']}.json"
    )
    final_path.unlink()
    forged_final_path.write_bytes(forged_final_body)
    forged_head = {
        "schema": accrual.POPULATION_HEAD_SCHEMA,
        "population_receipt_id": forged_final["population_receipt_id"],
        "population_receipt_sha256": accrual._digest(forged_final_body),
        "population_receipt_bytes": len(forged_final_body),
    }
    population_head_path.write_bytes(accrual._canonical_bytes(forged_head))

    marker_path = experience / "TERMINAL.json"
    forged_marker = _read(marker_path)
    forged_marker.update(
        {
            "population_receipt_id": forged_final["population_receipt_id"],
            "population_receipt_sha256": accrual._digest(forged_final_body),
            "population_receipt_bytes": len(forged_final_body),
        }
    )
    forged_marker = _rehash(
        forged_marker,
        field="terminal_marker_id",
        prefix="mmspyexpterminal_",
    )
    marker_path.write_bytes(accrual._canonical_bytes(forged_marker))
    with pytest.raises(
        accrual.MarketMemoryExperienceStoreError,
        match="as-of ledger",
    ):
        accrual.verify_terminal_ledger(ROOT, experience_root=experience)


def test_activation_capacity_preflight_has_126_session_plus_32_revision_reserve() -> None:
    def pins(trusted_count: int, technical_count: int) -> accrual.OwnerPins:
        return accrual.OwnerPins(
            trusted=SimpleNamespace(captures=(None,) * trusted_count),
            technical=SimpleNamespace(captures=(None,) * technical_count),
        )

    receipt = accrual._capacity_preflight(pins(98, 88))
    assert receipt["trusted_required_capacity"] == 256
    assert receipt["technical_required_capacity"] == 256
    with pytest.raises(accrual.MarketMemoryExperienceAccrualError, match="NO-GO"):
        accrual._capacity_preflight(pins(99, 88))
    with pytest.raises(accrual.MarketMemoryExperienceAccrualError, match="NO-GO"):
        accrual._capacity_preflight(pins(98, 89))


def test_activation_rechecks_capacity_before_first_capture_bearing_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    reader, real_pins = accrual._pin_owners(trusted_root, technical_root)
    oversized_trusted = SimpleNamespace(
        profile=real_pins.trusted.profile,
        store_id=real_pins.trusted.store_id,
        generation_id=real_pins.trusted.generation_id,
        generation_sha256=real_pins.trusted.generation_sha256,
        captures=(None,) * 99,
    )
    monkeypatch.setattr(
        accrual,
        "_pin_owners",
        lambda *_args: (
            reader,
            accrual.OwnerPins(
                trusted=oversized_trusted, technical=real_pins.technical
            ),
        ),
    )
    before = {
        str(path.relative_to(experience)): path.read_bytes()
        for path in experience.rglob("*")
        if path.is_file()
    }
    with pytest.raises(accrual.MarketMemoryExperienceAccrualError, match="NO-GO"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-18T04:35:00Z",
        )
    after = {
        str(path.relative_to(experience)): path.read_bytes()
        for path in experience.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not any((experience / "opportunities").iterdir())


def test_missed_activation_does_not_waive_capacity_gate_or_cleanup_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience, trusted_root, technical_root = _initialize_sources(
        tmp_path, monkeypatch
    )
    _install(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
    )
    real_pin_owners = accrual._pin_owners

    monkeypatch.setattr(
        accrual,
        "_pin_owners",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FileNotFoundError("activation owner unavailable")
        ),
    )
    _run(
        tmp_path,
        experience=experience,
        trusted_root=trusted_root,
        technical_root=technical_root,
        clock="2026-08-18T04:46:00Z",
    )
    activation = _read(
        experience / "opportunities" / "2026-08-17.json"
    )
    assert activation["disposition"] == "missed"

    # Leave a pending-only, unsealed preparation behind.  It is not a durable
    # capture-bearing admission and must neither waive the later exact-pair
    # preflight nor be cleaned up before a NO-GO decision.
    monkeypatch.setattr(accrual, "_pin_owners", real_pin_owners)
    original_boundary = accrual._publish_boundary

    def crash_on_staging(stage: str, path: Path) -> None:
        if stage == "temporary_fsynced" and path.parent.name == "prepared_objects":
            raise InjectedDurabilityCrash("pending-only preparation")

    monkeypatch.setattr(accrual, "_publish_boundary", crash_on_staging)
    with pytest.raises(InjectedDurabilityCrash, match="pending-only"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-19T04:35:00Z",
        )
    monkeypatch.setattr(accrual, "_publish_boundary", original_boundary)
    pending_staging = list(
        (experience / "prepared_objects").glob(".*.pending")
    )
    assert len(pending_staging) == 1

    reader, real_pins = real_pin_owners(trusted_root, technical_root)
    oversized_trusted = SimpleNamespace(
        profile=real_pins.trusted.profile,
        store_id=real_pins.trusted.store_id,
        generation_id=real_pins.trusted.generation_id,
        generation_sha256=real_pins.trusted.generation_sha256,
        captures=(None,) * 99,
    )
    monkeypatch.setattr(
        accrual,
        "_pin_owners",
        lambda *_args: (
            reader,
            accrual.OwnerPins(
                trusted=oversized_trusted, technical=real_pins.technical
            ),
        ),
    )
    before = {
        str(path.relative_to(experience)): (
            path.read_bytes(), path.stat().st_mtime_ns
        )
        for path in experience.rglob("*")
        if path.is_file()
    }
    with pytest.raises(accrual.MarketMemoryExperienceAccrualError, match="NO-GO"):
        _run(
            tmp_path,
            experience=experience,
            trusted_root=trusted_root,
            technical_root=technical_root,
            clock="2026-08-19T04:36:00Z",
        )
    after = {
        str(path.relative_to(experience)): (
            path.read_bytes(), path.stat().st_mtime_ns
        )
        for path in experience.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert pending_staging[0].is_file()


def test_public_owner_pins_admit_256_and_reject_257_before_ancestry_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    technical_root = _technical_root(tmp_path)
    rows = [
        {
            "capture_id": "mmactualcapture_" + f"{index:064x}",
            "session": "2026-08-17",
            "revision_id": "mmtechrev_" + f"{index:064x}",
            "source_observation_id": "mmtechsrc_" + f"{index:064x}",
            "snapshot_id": "mmtechsnap_" + f"{index:064x}",
            "first_observed_at": "2026-08-18T02:00:00Z",
            "receipt_sha256": f"{index:064x}",
        }
        for index in range(1, 257)
    ]
    generation = {
        "store_id": "mmactualstore_" + "1" * 64,
        "generation_id": "mmactualgeneration_" + "2" * 64,
        "captures": rows,
    }
    state = SimpleNamespace(
        generation=generation,
        head={"generation_id": generation["generation_id"], "generation_sha256": "3" * 64},
        manifest={"store_id": generation["store_id"]},
    )
    walks: list[int] = []
    monkeypatch.setattr(technical_store, "_load_state", lambda _root: state)
    monkeypatch.setattr(
        technical_store,
        "_load_generation",
        lambda *_args, **_kwargs: (walks.append(1) or generation, b"generation"),
    )
    pin = technical_store.pin_technical_actual_output_generation(
        technical_root, maximum_capture_count=256
    )
    assert len(pin.captures) == 256
    assert walks == [1]
    state.generation = {**generation, "captures": [*rows, rows[-1]]}
    with pytest.raises(technical_store.MarketMemoryTechnicalStoreError, match="pin budget"):
        technical_store.pin_technical_actual_output_generation(
            technical_root, maximum_capture_count=256
        )
    assert walks == [1]

    trusted_root = tmp_path / "market-memory" / "public" / "trusted-v1"
    trusted_state = SimpleNamespace(
        generation={"captures": [None] * 256},
        head={"generation_id": "mmgeneration_" + "4" * 64},
    )
    trusted_walks: list[int] = []
    monkeypatch.setattr(trusted, "_load_state", lambda _root: trusted_state)
    monkeypatch.setattr(
        pit,
        "_read_pinned_generation_from_state",
        lambda *_args, **_kwargs: (
            trusted_walks.append(1)
            or pit.PinnedGenerationSnapshot(
                profile=trusted.TRUSTED_STORE_PROFILE,
                store_id="mmstore_" + "5" * 64,
                generation_id="mmgeneration_" + "4" * 64,
                generation_sha256="6" * 64,
                captures=(),
            )
        ),
    )
    reader = trusted.TrustedFileAsKnownAtReader(trusted_root)
    reader.read_pinned_generation(maximum_capture_count=256)
    assert trusted_walks == [1]
    trusted_state.generation = {"captures": [None] * 257}
    with pytest.raises(pit.MarketMemoryStoreError, match="pin budget"):
        reader.read_pinned_generation(maximum_capture_count=256)
    assert trusted_walks == [1]


def test_run_scoped_126_session_view_projects_only_generation_delta_at_256_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registration = accrual.load_registration(ROOT)
    experience = _experience_root(tmp_path)
    sessions = nyse_calendar.sessions_between(
        accrual.ACTIVATION_SESSION, accrual.SUNSET_SESSION
    )
    assert len(sessions) == 126

    entries: list[technical_store.PinnedTechnicalCaptureIndexEntry] = []
    references: dict[str, dict] = {}
    for index in range(256):
        digest = f"{index + 1:064x}"
        session = sessions[index % len(sessions)].isoformat()
        entry = technical_store.PinnedTechnicalCaptureIndexEntry(
            capture_id="mmactualcapture_" + digest,
            session=session,
            revision_id="mmtechrev_" + digest,
            source_observation_id="mmtechsrc_" + digest,
            snapshot_id="mmtechsnap_" + digest,
            first_observed_at="2027-03-03T04:00:00Z",
            receipt_sha256=digest,
        )
        entries.append(entry)
        references[entry.capture_id] = {
            "capture_id": entry.capture_id,
            "revision_id": entry.revision_id,
            "source_observation_id": entry.source_observation_id,
            "snapshot_id": entry.snapshot_id,
            "source_session": entry.session,
            "first_observed_at": entry.first_observed_at,
            "spy_parquet_sha256": digest,
            **accrual._binary64_mark(100.0 + index, field="batch fixture"),
            "subject": copy.deepcopy(accrual._SUBJECT),
            "calendar": copy.deepcopy(accrual._CALENDAR),
            "price_basis": {
                "raw_unadjusted": True,
                "split_adjusted": False,
                "dividend_adjusted": False,
                "economic_return": False,
            },
        }

    def pin(count: int, digit: str, *, ancestry: tuple[str, ...] = ()):
        return technical_store.PinnedTechnicalGenerationSnapshot(
            profile=technical_store.STORE_PROFILE,
            store_id="mmactualstore_" + "a" * 64,
            generation_id="mmactualgeneration_" + digit * 64,
            generation_sha256=digit * 64,
            captures=tuple(entries[:count]),
            ancestry_generation_ids=ancestry,
        )

    first_pin = pin(255, "b")
    final_pin = pin(
        256,
        "c",
        ancestry=(first_pin.generation_id,),
    )
    projection_batches: list[tuple[str, ...]] = []
    trusted_pin = SimpleNamespace(
        profile=trusted.TRUSTED_STORE_PROFILE,
        store_id="mmstore_" + "d" * 64,
        generation_id="mmgeneration_" + "e" * 64,
        generation_sha256="f" * 64,
        captures=(),
    )

    def batch_load(_root, *, pin, capture_ids):
        projection_batches.append(tuple(capture_ids))
        return tuple(SimpleNamespace() for _item in capture_ids)

    monkeypatch.setattr(
        technical_store,
        "load_technical_actual_output_captures_from_pinned_generation",
        batch_load,
    )
    monkeypatch.setattr(
        accrual,
        "_technical_candidate_from_stored",
        lambda entry, _stored: accrual._TechnicalCandidate(
            reference=copy.deepcopy(references[entry.capture_id]),
            end_close=float.fromhex(
                references[entry.capture_id]["end_close_binary64_hex"]
            ),
        ),
    )

    started = wall_time.perf_counter()
    first_by_session, first_view = accrual._prepare_technical_view(
        experience,
        registration=registration,
        technical_root=tmp_path / "technicals-v1",
        pin=first_pin,
        trusted_pin=trusted_pin,
        pair_observed_at="2027-03-03T04:35:00Z",
    )
    assert first_view is not None
    accrual._publish_technical_view(experience, first_view)
    final_by_session, final_view = accrual._prepare_technical_view(
        experience,
        registration=registration,
        technical_root=tmp_path / "technicals-v1",
        pin=final_pin,
        trusted_pin=trusted_pin,
        pair_observed_at="2027-03-03T04:36:00Z",
    )
    assert final_view is not None
    accrual._publish_technical_view(experience, final_view)
    unchanged_by_session, unchanged_view = accrual._prepare_technical_view(
        experience,
        registration=registration,
        technical_root=tmp_path / "technicals-v1",
        pin=final_pin,
        trusted_pin=trusted_pin,
        pair_observed_at="2027-03-03T04:37:00Z",
    )
    elapsed = wall_time.perf_counter() - started

    assert len(first_by_session) == len(final_by_session) == 126
    assert unchanged_by_session == final_by_session
    assert unchanged_view is None
    assert projection_batches == [
        tuple(entry.capture_id for entry in entries[:255]),
        (entries[255].capture_id,),
    ]
    assert elapsed < 10.0


def test_257_owner_pin_failure_precedes_any_w2c_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    experience = _experience_root(tmp_path)
    monkeypatch.setattr(
        accrual,
        "_pin_owners",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            technical_store.MarketMemoryTechnicalStoreError(
                "actual-output active generation exceeds the caller's pin budget"
            )
        ),
    )
    with pytest.raises(technical_store.MarketMemoryTechnicalStoreError, match="pin budget"):
        accrual.accrue_spy_experience(
            ROOT,
            experience_root=experience,
            trusted_root=tmp_path / "trusted-v1",
            technical_root=tmp_path / "technicals-v1",
            writer_commit=COMMIT,
            clock=_clock("2026-08-11T20:00:00Z"),
        )
    assert not experience.exists()


def test_future_v2_acceptance_must_reload_every_v1_ref_and_never_claim_indefinite_v1() -> None:
    registration = accrual.load_registration(ROOT).value
    auditability = registration["spec"]["auditability"]
    assert auditability == {
        "warning_owner_capture_count": 320,
        "checkpoint_migration_required_before_owner_count": 384,
        "v2_acceptance_requirement": "reload_every_v1_pilot_source_ref_from_authenticated_checkpoint_or_delta",
        "indefinite_v1_auditability": False,
    }
    corpus = "\n".join(
        path.read_text()
        for path in (
            ROOT / "engine/neuralweb/market_memory_experience_accrual.py",
            ROOT / "config/market_memory_spy_experience_registration.v1.json",
        )
    ).lower()
    assert "indefinite_v1_auditability\":false" in corpus.replace(" ", "")
    assert "v1 ensures indefinite" not in corpus
