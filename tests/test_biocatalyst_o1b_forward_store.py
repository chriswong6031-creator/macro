"""Bounded, hermetic tests for the BC-O1b forward evidence ledger.

O1b adds record kinds to the O1a store; it does not add a second writer, a
second root, or a second set of correction semantics.  These tests pin the four
properties the forward ledger exists for: a snapshot is immutable once written,
an outcome carries its known-at clock and its censoring state, the same logical
record written twice is one record, and replay is deterministic.  They also pin
the fences: no look-ahead, no promotion, and no security identity anywhere.

Every test runs under ``tmp_path``.  Nothing here touches a production path, a
route, a source, or a pointer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from engine.biocatalyst.operational_store import (
    KIND_SCOPED_PAYLOAD_KEY_ALLOWANCES,
    MAX_QUERY_LIMIT,
    NEVER_ALLOWED_PAYLOAD_KEY_TOKENS,
    O1B_RECORD_KINDS,
    PAYLOAD_CONTRACT_BY_RECORD_KIND,
    REVISION_LINKED_RECORD_KINDS,
    OperationalStore,
    OperationalStoreConflictError,
    OperationalStoreError,
    OperationalStoreUnavailableError,
    forbidden_payload_key_tokens_for,
    provision_operational_store,
    replay_sequence,
)
from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
)


ROOT = Path(__file__).resolve().parents[1]

NCT = "nct:NCT01234567"
EVIDENCE = "internal:ctgov_snapshot_1"
RECORDED_AT = "2026-08-07T00:00:10.000000Z"


@pytest.fixture()
def store(tmp_path: Path) -> OperationalStore:
    root = tmp_path / "operational"
    provision_operational_store(root)
    return OperationalStore(root)


def _forecast_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_id": "biocatalyst_forecast_record.v1",
        "schema_version": "1.0.0",
        "forecast_key": "fc:trial_progression:1",
        "forecast_family": "trial_progression_termination",
        "subject_ref": NCT,
        "model_key": "baseline_phase_transition",
        "feature_snapshot_record_id": "bcop_" + "0" * 32,
        "forecast_made_at": "2026-08-07T00:00:00Z",
        "evidence_asof": "2026-08-06T00:00:00Z",
        "resolves_after": "2026-11-07T00:00:00Z",
        "forecast_value": 0.4,
        "forecast_value_semantics": "unitless_forward_window_share_display_only",
        "authority_tier": "display_only_not_promoted",
        "promotion_state": "not_promoted",
        "evidence_refs": [EVIDENCE],
        "revision_of": None,
    }
    payload.update(overrides)
    return payload


def _outcome_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_id": "biocatalyst_outcome_record.v1",
        "schema_version": "1.0.0",
        "outcome_id": "oc:trial_progression:1",
        "family_id": "trial_progression_termination",
        "subject_ref": NCT,
        "seed_layer": "study_conduct",
        "value": "terminated",
        "value_authority": "source_native_status_only",
        "censoring_state": "not_censored_terminal_event",
        "terminality": "terminal",
        "effective_at": "2026-08-05T00:00:00Z",
        "known_at": "2026-08-06T00:00:00Z",
        "observed_at": "2026-08-06T12:00:00Z",
        "evidence_refs": [EVIDENCE],
        "policy_version": "m0a.2",
        "resolver_type": "deterministic_source_statement",
        "revision_of": None,
    }
    payload.update(overrides)
    return payload


def _feature_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "feature_set_key": "trial_progression_v1",
        "feature_set_version": "1.0.0",
        "subject_ref": NCT,
        "asof": "2026-08-06T00:00:00Z",
        "evidence_asof": "2026-08-06T00:00:00Z",
        "evidence_sha256": "a" * 64,
        "authority_tier": "display_only_not_promoted",
        "revision_of": None,
    }
    payload.update(overrides)
    return payload


def _model_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model_key": "baseline_phase_transition",
        "model_version": "0.1.0",
        "registered_at": "2026-08-06T00:00:00Z",
        "frozen_input_contract": "biocatalyst_operational_record.v1",
        "authority_tier": "display_only_not_promoted",
        "evidence_sha256": "b" * 64,
    }
    payload.update(overrides)
    return payload


def _manifest_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "manifest_key": "trial_progression_preregistration",
        "preregistered_at": "2026-08-06T00:00:00Z",
        "subject_model_key": "baseline_phase_transition",
        "evaluation_metric_keys": ["brier", "coverage"],
        "evaluation_gate_state": "preregistered_not_run",
        "authority_tier": "display_only_not_promoted",
    }
    payload.update(overrides)
    return payload


def _trace_payload(subject_record_id: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "trace_key": "trial_progression_trace",
        "subject_record_id": subject_record_id,
        "subject_record_kind": "forecast_snapshot",
        "component_key": "phase_state",
        "component_share": 0.25,
        "traced_at": "2026-08-06T00:00:00Z",
        "authority_tier": "display_only_not_promoted",
    }
    payload.update(overrides)
    return payload


# ---- contract registration ------------------------------------------------


def test_every_o1b_payload_contract_is_registered() -> None:
    contract_ids = ContractRegistry(ROOT).contract_ids
    assert PAYLOAD_CONTRACT_BY_RECORD_KIND
    for record_kind, contract_id in PAYLOAD_CONTRACT_BY_RECORD_KIND.items():
        assert record_kind in O1B_RECORD_KINDS, record_kind
        assert contract_id in contract_ids, contract_id


# ---- immutability and correction lineage ----------------------------------


def test_a_correction_never_rewrites_the_original_forecast_snapshot(
    store: OperationalStore,
) -> None:
    original = store.append(
        "forecast_snapshot",
        _forecast_payload(),
        idempotency_key="fc:1",
        recorded_at=RECORDED_AT,
    )
    path = (
        store.state_root
        / "objects"
        / "forecast_snapshot"
        / original.record_id[5:7]
        / f"{original.record_id}.json"
    )
    before = path.read_bytes()

    correction = store.append(
        "forecast_snapshot",
        _forecast_payload(forecast_value=0.55, revision_of=original.record_id),
        idempotency_key="fc:1:r2",
        corrects_record_id=original.record_id,
        recorded_at="2026-08-07T01:00:00.000000Z",
    )

    assert correction.record_id != original.record_id
    # The original object is byte-identical after the correction.
    assert path.read_bytes() == before
    assert store.get("forecast_snapshot", original.record_id)["payload"][
        "forecast_value"
    ] == 0.4
    corrected = store.get("forecast_snapshot", correction.record_id)
    assert corrected["corrects_record_id"] == original.record_id
    assert corrected["payload"]["revision_of"] == original.record_id
    # Both snapshots remain readable: the ledger grows, it never replaces.
    assert len(store.read("forecast_snapshot", limit=MAX_QUERY_LIMIT).records) == 2


def test_a_revision_must_name_the_same_predecessor_the_store_can_see(
    store: OperationalStore,
) -> None:
    original = store.append(
        "forecast_snapshot",
        _forecast_payload(),
        idempotency_key="fc:1",
        recorded_at=RECORDED_AT,
    )
    assert REVISION_LINKED_RECORD_KINDS == {"forecast_snapshot", "outcome_observation"}
    with pytest.raises(ContractValidationError) as error:
        store.append(
            "forecast_snapshot",
            # revision_of left null while corrects_record_id names a predecessor.
            _forecast_payload(forecast_value=0.55),
            idempotency_key="fc:1:r2",
            corrects_record_id=original.record_id,
            recorded_at="2026-08-07T01:00:00.000000Z",
        )
    assert "operational_record.revision_link" in str(error.value)


def test_the_store_still_has_no_update_or_delete_path_for_o1b(
    store: OperationalStore,
) -> None:
    public = {name for name in dir(OperationalStore) if not name.startswith("_")}
    assert public == {"append", "get", "read", "rebuild_index", "replay_digest", "state_root"}


# ---- the known-at clock ---------------------------------------------------


def test_an_outcome_carries_its_known_at_clock_and_censoring_state(
    store: OperationalStore,
) -> None:
    receipt = store.append(
        "outcome_observation",
        _outcome_payload(),
        idempotency_key="oc:1",
        recorded_at=RECORDED_AT,
    )
    payload = store.get("outcome_observation", receipt.record_id)["payload"]
    assert payload["effective_at"] <= payload["known_at"] <= payload["observed_at"]
    assert payload["censoring_state"] == "not_censored_terminal_event"
    assert payload["terminality"] == "terminal"
    assert payload["value_authority"] == "source_native_status_only"


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        # A fact may not be known before it happened.
        (
            {"effective_at": "2026-08-06T12:00:00Z", "known_at": "2026-08-06T00:00:00Z"},
            "operational_record.clock_order",
        ),
        # A fact may not be read before it was knowable.
        (
            {"known_at": "2026-08-06T13:00:00Z", "observed_at": "2026-08-06T12:00:00Z"},
            "operational_record.clock_order",
        ),
        # A fact may not be observed after it was written down.
        (
            {"observed_at": "2026-08-08T00:00:00Z", "known_at": "2026-08-08T00:00:00Z"},
            "operational_record.clock_after_recorded_at",
        ),
    ],
)
def test_an_out_of_order_known_at_clock_fails_closed(
    store: OperationalStore, overrides: dict[str, Any], expected_code: str
) -> None:
    with pytest.raises(ContractValidationError) as error:
        store.append(
            "outcome_observation",
            _outcome_payload(**overrides),
            idempotency_key="oc:1",
            recorded_at=RECORDED_AT,
        )
    assert expected_code in str(error.value)
    assert store.read("outcome_observation", limit=MAX_QUERY_LIMIT).records == ()


def test_a_censored_observation_is_never_a_resolved_outcome(
    store: OperationalStore,
) -> None:
    with pytest.raises(ContractValidationError) as error:
        store.append(
            "outcome_observation",
            _outcome_payload(
                censoring_state="right_censored_open_window", terminality="terminal"
            ),
            idempotency_key="oc:1",
            recorded_at=RECORDED_AT,
        )
    assert "operational_record.censoring_terminality" in str(error.value)
    # The same observation is accepted once it stops claiming to be resolved.
    store.append(
        "outcome_observation",
        _outcome_payload(
            censoring_state="right_censored_open_window", terminality="non_terminal"
        ),
        idempotency_key="oc:1",
        recorded_at=RECORDED_AT,
    )


def test_a_forecast_for_an_already_resolving_window_fails_closed(
    store: OperationalStore,
) -> None:
    # resolves_after in the past relative to recorded_at: the window has already
    # begun to resolve, so this is a backdated forecast, not a forward one.
    with pytest.raises(ContractValidationError) as error:
        store.append(
            "forecast_snapshot",
            _forecast_payload(resolves_after="2026-08-06T00:00:00Z"),
            idempotency_key="fc:1",
            recorded_at=RECORDED_AT,
        )
    assert "operational_record.window_already_resolving" in str(error.value)
    assert store.read("forecast_snapshot", limit=MAX_QUERY_LIMIT).records == ()


def test_a_forecast_may_not_use_evidence_from_after_it_was_made(
    store: OperationalStore,
) -> None:
    with pytest.raises(ContractValidationError) as error:
        store.append(
            "forecast_snapshot",
            _forecast_payload(evidence_asof="2026-08-07T00:00:05Z"),
            idempotency_key="fc:1",
            recorded_at=RECORDED_AT,
        )
    assert "operational_record.clock_order" in str(error.value)


# ---- idempotency and replay ------------------------------------------------


def test_the_same_logical_forecast_twice_is_one_record(store: OperationalStore) -> None:
    first = store.append(
        "forecast_snapshot",
        _forecast_payload(),
        idempotency_key="fc:1",
        recorded_at=RECORDED_AT,
    )
    second = store.append(
        "forecast_snapshot",
        _forecast_payload(),
        idempotency_key="fc:1",
        recorded_at=RECORDED_AT,
    )
    assert first.record_id == second.record_id
    assert first.created is True and second.created is False
    assert len(store.read("forecast_snapshot", limit=MAX_QUERY_LIMIT).records) == 1


def test_different_bytes_under_one_forecast_key_fail_closed(
    store: OperationalStore,
) -> None:
    store.append(
        "forecast_snapshot",
        _forecast_payload(),
        idempotency_key="fc:1",
        recorded_at=RECORDED_AT,
    )
    with pytest.raises(OperationalStoreConflictError) as error:
        store.append(
            "forecast_snapshot",
            _forecast_payload(forecast_value=0.9),
            idempotency_key="fc:1",
            recorded_at=RECORDED_AT,
        )
    assert error.value.code == "OPERATIONAL_IDEMPOTENCY_KEY_CONFLICT"
    assert len(store.read("forecast_snapshot", limit=MAX_QUERY_LIMIT).records) == 1


def _o1b_append_sequence(forecast_record_id: str) -> tuple[dict[str, Any], ...]:
    return (
        {
            "record_kind": "feature_snapshot",
            "payload": _feature_payload(),
            "idempotency_key": "fs:1",
            "recorded_at": "2026-08-07T00:00:01.000000Z",
        },
        {
            "record_kind": "model_registration",
            "payload": _model_payload(),
            "idempotency_key": "mr:1",
            "recorded_at": "2026-08-07T00:00:02.000000Z",
        },
        {
            "record_kind": "evaluation_manifest",
            "payload": _manifest_payload(),
            "idempotency_key": "em:1",
            "recorded_at": "2026-08-07T00:00:03.000000Z",
        },
        {
            "record_kind": "forecast_snapshot",
            "payload": _forecast_payload(),
            "idempotency_key": "fc:1",
            "recorded_at": RECORDED_AT,
        },
        {
            "record_kind": "contribution_trace",
            "payload": _trace_payload(forecast_record_id),
            "idempotency_key": "ct:1",
            "recorded_at": "2026-08-07T00:00:11.000000Z",
        },
        {
            "record_kind": "outcome_observation",
            "payload": _outcome_payload(),
            "idempotency_key": "oc:1",
            "recorded_at": "2026-08-07T00:00:12.000000Z",
        },
    )


def test_replay_of_an_o1b_append_sequence_is_deterministic(tmp_path: Path) -> None:
    placeholder = "bcop_" + "1" * 32
    produced: list[tuple[str, ...]] = []
    digests: list[str] = []
    for name in ("first", "second"):
        root = tmp_path / name
        provision_operational_store(root)
        store = OperationalStore(root)
        produced.append(replay_sequence(store, _o1b_append_sequence(placeholder)))
        digests.append(
            "|".join(
                store.replay_digest(record_kind, limit=MAX_QUERY_LIMIT)
                for record_kind in O1B_RECORD_KINDS
            )
        )
    assert produced[0] == produced[1]
    assert len(set(produced[0])) == len(produced[0])
    assert digests[0] == digests[1]


# ---- the explicit UNAVAILABLE state ---------------------------------------


def test_o1b_writes_fail_closed_when_the_state_root_is_missing(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    store = OperationalStore(missing)
    with pytest.raises(OperationalStoreUnavailableError) as error:
        store.append(
            "outcome_observation",
            _outcome_payload(),
            idempotency_key="oc:1",
            recorded_at=RECORDED_AT,
        )
    assert error.value.code == "OPERATIONAL_STATE_ROOT_MISSING"
    assert not missing.exists()


def test_o1b_writes_fail_closed_on_an_unprovisioned_root(tmp_path: Path) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    store = OperationalStore(root)
    with pytest.raises(OperationalStoreUnavailableError) as error:
        store.append(
            "forecast_snapshot",
            _forecast_payload(),
            idempotency_key="fc:1",
            recorded_at=RECORDED_AT,
        )
    assert error.value.code == "OPERATIONAL_STATE_ROOT_NOT_PROVISIONED"
    assert list(root.iterdir()) == []


# ---- the authority fence ---------------------------------------------------


@pytest.mark.parametrize("token", sorted(NEVER_ALLOWED_PAYLOAD_KEY_TOKENS))
@pytest.mark.parametrize("record_kind", sorted(O1B_RECORD_KINDS))
def test_no_kind_allowance_can_ever_exempt_a_security_identity_token(
    record_kind: str, token: str
) -> None:
    # NCT-only: an identity join is refused in every kind, and no present or
    # future per-kind allowance can switch that off.
    assert token in forbidden_payload_key_tokens_for(record_kind)
    assert not (
        KIND_SCOPED_PAYLOAD_KEY_ALLOWANCES.get(record_kind, frozenset())
        & NEVER_ALLOWED_PAYLOAD_KEY_TOKENS
    )


@pytest.mark.parametrize(
    "forbidden_key", ["ticker", "issuer_id", "peer_rank", "position_size", "score"]
)
def test_a_forecast_payload_may_not_rank_size_or_name_a_security(
    store: OperationalStore, forbidden_key: str
) -> None:
    with pytest.raises(ContractValidationError):
        store.append(
            "forecast_snapshot",
            _forecast_payload(**{forbidden_key: "x"}),
            idempotency_key="fc:1",
            recorded_at=RECORDED_AT,
        )
    assert store.read("forecast_snapshot", limit=MAX_QUERY_LIMIT).records == ()


def test_an_outcome_payload_may_not_name_a_security(store: OperationalStore) -> None:
    with pytest.raises(ContractValidationError):
        store.append(
            "outcome_observation",
            _outcome_payload(subject_ref="ticker:MRNA"),
            idempotency_key="oc:1",
            recorded_at=RECORDED_AT,
        )
    assert store.read("outcome_observation", limit=MAX_QUERY_LIMIT).records == ()


@pytest.mark.parametrize(
    "record_kind",
    ["feature_snapshot", "forecast_snapshot", "model_registration", "evaluation_manifest"],
)
def test_no_o1b_record_may_claim_promoted_authority(
    store: OperationalStore, record_kind: str
) -> None:
    builders = {
        "feature_snapshot": _feature_payload,
        "forecast_snapshot": _forecast_payload,
        "model_registration": _model_payload,
        "evaluation_manifest": _manifest_payload,
    }
    payload = builders[record_kind](authority_tier="promoted")
    with pytest.raises(ContractValidationError):
        store.append(
            record_kind, payload, idempotency_key="x:1", recorded_at=RECORDED_AT
        )


def test_a_forecast_value_outside_the_unit_interval_fails_closed(
    store: OperationalStore,
) -> None:
    with pytest.raises(ContractValidationError):
        store.append(
            "forecast_snapshot",
            _forecast_payload(forecast_value=1.5),
            idempotency_key="fc:1",
            recorded_at=RECORDED_AT,
        )


def test_an_unknown_o1b_record_kind_is_refused(store: OperationalStore) -> None:
    with pytest.raises(OperationalStoreError) as error:
        store.append(
            "forecast_snapshot_v2", _forecast_payload(), idempotency_key="fc:1"
        )
    assert error.value.code == "OPERATIONAL_RECORD_KIND_UNKNOWN"
