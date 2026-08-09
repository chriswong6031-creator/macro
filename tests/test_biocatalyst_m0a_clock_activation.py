"""Tests for BC-M0a family clock activation.

These pin the honest answer as of m0a.3 and, more importantly, pin WHY it is
that answer.  BC-O1b now exists, so the ``o1b_outcome_writer`` precondition is
discharged for all nine outcome families.  Record History is rights-reviewed,
but its committed runtime switch is off and its committed allowlist is empty;
the other source and identity blockers remain.  Every clock therefore stays
closed.

The tests below prove three separate things:

1. the evaluator opens nothing today, and names the exact blocker for each
   family;
2. it WOULD open the NCT-keyed trial families the moment their source becomes
   eligible — so the closure is evidence, not a missing code path; and
3. a hand-edited entry gate cannot open a family whose sources cannot be read.

Every store write runs under ``tmp_path``.  No production state root is
provisioned, no source is activated, and nothing accrues.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from engine.biocatalyst.family_clock import (
    CLOCK_CLOSED,
    CLOCK_OPENED,
    FAMILY_CLOCK_ACTIVATION_CONTRACT_ID,
    FAMILY_CLOCK_ACTIVATION_RECORD_KIND,
    INELIGIBLE_SOURCE_BLOCKER,
    O1B_WRITER_CONTRACT_ID,
    O1B_WRITER_RECORD_KIND,
    WRITER_ABSENT_BLOCKER,
    build_activation_payload,
    evaluate_family_clocks,
    load_yaml_document,
    o1b_writer_is_available,
    record_family_clock_activations,
)
from engine.biocatalyst.operational_store import (
    MAX_QUERY_LIMIT,
    RECORD_KINDS,
    OperationalStore,
    OperationalStoreConflictError,
    provision_operational_store,
)
from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
)


ROOT = Path(__file__).resolve().parents[1]
FAMILY_POLICY = ROOT / "config" / "biocatalyst_outcome_family_policy.yml"
SOURCE_REGISTRY = ROOT / "config" / "biocatalyst_sources.yml"

TRIAL_FAMILIES = (
    "trial_progression_termination",
    "endpoint_readout",
    "timing_slip",
    "enrollment_site_change",
)
RECORD_HISTORY = "clinicaltrials_gov_record_history"

EVALUATED_AT = "2026-08-07T00:00:00Z"
RECORDED_AT = "2026-08-07T00:00:01.000000Z"


@pytest.fixture(scope="module")
def policy() -> dict[str, Any]:
    document, _ = load_yaml_document(FAMILY_POLICY)
    return document


@pytest.fixture(scope="module")
def policy_sha256() -> str:
    _, digest = load_yaml_document(FAMILY_POLICY)
    return digest


@pytest.fixture(scope="module")
def sources() -> dict[str, Any]:
    document, _ = load_yaml_document(SOURCE_REGISTRY)
    return document


@pytest.fixture()
def store(tmp_path: Path) -> OperationalStore:
    root = tmp_path / "operational"
    provision_operational_store(root)
    return OperationalStore(root)


def _decisions(policy: dict, sources: dict, *, writer: bool = True) -> dict:
    return {
        decision.family_id: decision
        for decision in evaluate_family_clocks(policy, sources, writer_available=writer)
    }


# ---- the writer precondition, discharged -----------------------------------


def test_the_o1b_outcome_writer_now_genuinely_exists() -> None:
    # Both halves are required: a contract with no record kind is a document,
    # not a writer.
    assert O1B_WRITER_CONTRACT_ID in ContractRegistry(ROOT).contract_ids
    assert O1B_WRITER_RECORD_KIND in RECORD_KINDS
    assert o1b_writer_is_available(repo_root=ROOT) is True


def test_without_the_writer_every_family_is_blocked_on_it(
    policy: dict, sources: dict
) -> None:
    decisions = _decisions(policy, sources, writer=False)
    assert len(decisions) == 9
    for family_id, decision in decisions.items():
        assert decision.clock_state == CLOCK_CLOSED, family_id
        assert "o1b_outcome_writer" in decision.unsatisfied_preconditions, family_id
        assert WRITER_ABSENT_BLOCKER in decision.blockers, family_id


# ---- the honest answer today ----------------------------------------------


def test_record_history_is_rights_allowed_but_not_activation_eligible(
    sources: dict,
) -> None:
    registrations = sources["sources"]
    rights_allowed = sorted(
        source_id
        for source_id, registration in registrations.items()
        if registration.get("production_ingest_allowed") is True
    )
    assert rights_allowed == [
        "clinicaltrials_gov_record_history",
        "clinicaltrials_gov_v2",
    ]
    assert registrations[RECORD_HISTORY]["rights_state"] == (
        "official_terms_operator_reviewed_for_bounded_beta"
    )
    control = sources["b2_history_canary"]
    assert control["default_enabled"] is False
    assert control["default_allowlist"] == []


def test_no_family_clock_opens_today_and_each_names_its_blocker(
    policy: dict, sources: dict
) -> None:
    decisions = _decisions(policy, sources)
    assert len(decisions) == 9
    assert [decision.clock_state for decision in decisions.values()] == [
        CLOCK_CLOSED
    ] * 9
    for family_id, decision in decisions.items():
        assert decision.blockers, family_id
        assert decision.unsatisfied_preconditions, family_id
        # The one precondition BC-O1b did discharge stays discharged.
        assert "o1b_outcome_writer" not in decision.unsatisfied_preconditions, family_id
        assert WRITER_ABSENT_BLOCKER not in decision.blockers, family_id


@pytest.mark.parametrize("family_id", TRIAL_FAMILIES)
def test_each_nct_keyed_family_is_closed_on_record_history_ineligibility(
    policy: dict, sources: dict, family_id: str
) -> None:
    decision = _decisions(policy, sources)[family_id]
    assert decision.clock_state == CLOCK_CLOSED
    assert decision.ineligible_source_ids == (RECORD_HISTORY,)
    assert INELIGIBLE_SOURCE_BLOCKER in decision.blockers
    assert decision.unsatisfied_preconditions == ("eligible_source_registration",)


def test_the_frozen_policy_gate_states_match_the_evaluated_evidence(
    policy: dict, sources: dict
) -> None:
    # The YAML may not drift from what the registry actually says.  A hand-typed
    # "satisfied" or a quietly dropped blocker goes red here.
    decisions = _decisions(policy, sources)
    for family_id, family in policy["families"].items():
        gate = family["entry_gate"]
        decision = decisions[family_id]
        assert gate["satisfied"] is False, family_id
        assert family["state"] == "clock_not_opened", family_id
        assert sorted(gate["unsatisfied_preconditions"]) == list(
            decision.unsatisfied_preconditions
        ), family_id
        assert sorted(gate["blockers"]) == list(decision.blockers), family_id


# ---- the closure is evidence, not a missing code path ----------------------


def _sources_with_eligible_record_history(sources: dict) -> dict:
    widened = copy.deepcopy(sources)
    widened["sources"][RECORD_HISTORY]["production_ingest_allowed"] = True
    widened["b2_history_canary"]["default_enabled"] = True
    widened["b2_history_canary"]["default_allowlist"] = ["NCT00000001"]
    return widened


def test_the_trial_families_would_open_once_their_source_is_eligible(
    policy: dict, sources: dict
) -> None:
    decisions = _decisions(policy, _sources_with_eligible_record_history(sources))
    for family_id in (
        "trial_progression_termination",
        "timing_slip",
        "enrollment_site_change",
    ):
        decision = decisions[family_id]
        assert decision.clock_state == CLOCK_OPENED, family_id
        assert decision.blockers == (), family_id
        assert decision.unsatisfied_preconditions == (), family_id
    # Endpoint readouts stay closed on a blocker this evaluator cannot clear.
    endpoint = decisions["endpoint_readout"]
    assert endpoint.clock_state == CLOCK_CLOSED
    assert endpoint.blockers == ("endpoint_alignment_review_queue_not_drained",)


def test_the_identity_gated_families_stay_closed_even_with_eligible_sources(
    policy: dict, sources: dict
) -> None:
    decisions = _decisions(policy, _sources_with_eligible_record_history(sources))
    for family_id in (
        "financing_dilution_event",
        "partnership_event",
        "market_reaction",
        "forecast_calibration",
    ):
        decision = decisions[family_id]
        assert decision.clock_state == CLOCK_CLOSED, family_id
        assert "eligible_identity_contract" in decision.unsatisfied_preconditions, family_id


def test_a_hand_edited_gate_cannot_open_a_family_over_an_ineligible_source(
    policy: dict, sources: dict
) -> None:
    forged = copy.deepcopy(policy)
    gate = forged["families"]["trial_progression_termination"]["entry_gate"]
    gate["satisfied"] = True
    gate["unsatisfied_preconditions"] = []
    gate["blockers"] = []
    decision = _decisions(forged, sources)["trial_progression_termination"]
    assert decision.clock_state == CLOCK_CLOSED
    assert decision.ineligible_source_ids == (RECORD_HISTORY,)
    assert INELIGIBLE_SOURCE_BLOCKER in decision.blockers


def test_an_unknown_required_source_is_ineligible(policy: dict, sources: dict) -> None:
    forged = copy.deepcopy(policy)
    forged["families"]["timing_slip"]["entry_gate"]["required_source_ids"] = [
        "some_source_nobody_registered"
    ]
    decision = _decisions(forged, sources)["timing_slip"]
    assert decision.clock_state == CLOCK_CLOSED
    assert decision.ineligible_source_ids == ("some_source_nobody_registered",)


# ---- the activation receipt ------------------------------------------------


def test_every_family_records_an_activation_receipt_through_the_o1a_writer(
    store: OperationalStore, policy: dict, sources: dict, policy_sha256: str
) -> None:
    decisions = evaluate_family_clocks(policy, sources, writer_available=True)
    receipts = record_family_clock_activations(
        store,
        decisions,
        policy_version=policy["policy_version"],
        policy_sha256=policy_sha256,
        evaluated_at=EVALUATED_AT,
        recorded_at=RECORDED_AT,
    )
    assert len(receipts) == 9
    assert all(receipt.created for receipt in receipts)
    assert FAMILY_CLOCK_ACTIVATION_RECORD_KIND in RECORD_KINDS

    page = store.read(FAMILY_CLOCK_ACTIVATION_RECORD_KIND, limit=MAX_QUERY_LIMIT)
    assert len(page.records) == 9
    for record in page.records:
        payload = record["payload"]
        assert payload["contract_id"] == FAMILY_CLOCK_ACTIVATION_CONTRACT_ID
        # The receipt binds to the exact bytes of the policy it was evaluated
        # against, so a later policy edit cannot inherit this evidence.
        assert payload["policy_version"] == policy["policy_version"]
        assert payload["policy_sha256"] == policy_sha256
        assert payload["backfill"] == "forbidden_no_history_recorded"
        # Today's honest answer: closed, with a named blocker and no accrual.
        assert payload["clock_state"] == CLOCK_CLOSED
        assert payload["blockers"]
        assert payload["accrual_start_known_at"] is None


def test_re_recording_the_same_evaluation_is_a_no_op(
    store: OperationalStore, policy: dict, sources: dict, policy_sha256: str
) -> None:
    decisions = evaluate_family_clocks(policy, sources, writer_available=True)
    kwargs = {
        "policy_version": policy["policy_version"],
        "policy_sha256": policy_sha256,
        "evaluated_at": EVALUATED_AT,
        "recorded_at": RECORDED_AT,
    }
    first = record_family_clock_activations(store, decisions, **kwargs)
    second = record_family_clock_activations(store, decisions, **kwargs)
    assert [receipt.record_id for receipt in first] == [
        receipt.record_id for receipt in second
    ]
    assert not any(receipt.created for receipt in second)
    assert len(
        store.read(FAMILY_CLOCK_ACTIVATION_RECORD_KIND, limit=MAX_QUERY_LIMIT).records
    ) == 9


def test_a_different_answer_under_one_policy_version_and_day_fails_closed(
    store: OperationalStore, policy: dict, sources: dict, policy_sha256: str
) -> None:
    kwargs = {
        "policy_version": policy["policy_version"],
        "policy_sha256": policy_sha256,
        "evaluated_at": EVALUATED_AT,
        "recorded_at": RECORDED_AT,
    }
    record_family_clock_activations(
        store, evaluate_family_clocks(policy, sources, writer_available=True), **kwargs
    )
    widened = evaluate_family_clocks(
        policy, _sources_with_eligible_record_history(sources), writer_available=True
    )
    with pytest.raises(OperationalStoreConflictError) as error:
        record_family_clock_activations(store, widened, **kwargs)
    assert error.value.code == "OPERATIONAL_IDEMPOTENCY_KEY_CONFLICT"


def test_an_activation_receipt_is_append_only(
    store: OperationalStore, policy: dict, sources: dict, policy_sha256: str
) -> None:
    decisions = evaluate_family_clocks(policy, sources, writer_available=True)
    receipts = record_family_clock_activations(
        store,
        decisions,
        policy_version=policy["policy_version"],
        policy_sha256=policy_sha256,
        evaluated_at=EVALUATED_AT,
        recorded_at=RECORDED_AT,
    )
    with pytest.raises(Exception) as error:
        store.append(
            FAMILY_CLOCK_ACTIVATION_RECORD_KIND,
            build_activation_payload(
                decisions[0],
                policy_version=policy["policy_version"],
                policy_sha256=policy_sha256,
                evaluated_at=EVALUATED_AT,
            ),
            idempotency_key="bcm0a:clock:correction",
            corrects_record_id=receipts[0].record_id,
            recorded_at=RECORDED_AT,
        )
    assert "NOT_CORRIGIBLE" in str(error.value)


# ---- opening a clock is never a backfill -----------------------------------


def _opened_payload(policy_sha256: str, **overrides: Any) -> dict[str, Any]:
    payload = {
        "contract_id": FAMILY_CLOCK_ACTIVATION_CONTRACT_ID,
        "schema_version": "1.0.0",
        "family_id": "trial_progression_termination",
        "policy_version": "m0a.3",
        "policy_sha256": policy_sha256,
        "clock_state": CLOCK_OPENED,
        "evaluated_at": EVALUATED_AT,
        "accrual_start_known_at": EVALUATED_AT,
        "satisfied_preconditions": [
            "frozen_policy_version",
            "eligible_source_registration",
            "o1b_outcome_writer",
        ],
        "unsatisfied_preconditions": [],
        "blockers": [],
        "ineligible_source_ids": [],
        "backfill": "forbidden_no_history_recorded",
        "authority": "facts_and_context_only",
    }
    payload.update(overrides)
    return payload


def test_an_open_clock_accrues_from_the_instant_it_opened(
    store: OperationalStore, policy_sha256: str
) -> None:
    receipt = store.append(
        FAMILY_CLOCK_ACTIVATION_RECORD_KIND,
        _opened_payload(policy_sha256),
        idempotency_key="bcm0a:clock:open:1",
        recorded_at=RECORDED_AT,
    )
    payload = store.get(FAMILY_CLOCK_ACTIVATION_RECORD_KIND, receipt.record_id)["payload"]
    assert payload["accrual_start_known_at"] == payload["evaluated_at"]


def test_an_accrual_start_before_the_activation_is_a_backfill_and_fails_closed(
    store: OperationalStore, policy_sha256: str
) -> None:
    with pytest.raises(ContractValidationError) as error:
        store.append(
            FAMILY_CLOCK_ACTIVATION_RECORD_KIND,
            _opened_payload(
                policy_sha256, accrual_start_known_at="2026-01-01T00:00:00Z"
            ),
            idempotency_key="bcm0a:clock:open:1",
            recorded_at=RECORDED_AT,
        )
    assert "operational_record.clock_order" in str(error.value)


def test_a_clock_may_not_be_recorded_open_while_a_blocker_stands(
    store: OperationalStore, policy_sha256: str
) -> None:
    with pytest.raises(ContractValidationError) as error:
        store.append(
            FAMILY_CLOCK_ACTIVATION_RECORD_KIND,
            _opened_payload(policy_sha256, blockers=[INELIGIBLE_SOURCE_BLOCKER]),
            idempotency_key="bcm0a:clock:open:1",
            recorded_at=RECORDED_AT,
        )
    assert "operational_record.clock_opened_with_blockers" in str(error.value)


def test_a_closed_clock_may_not_claim_an_accrual_start(
    store: OperationalStore, policy_sha256: str
) -> None:
    with pytest.raises(ContractValidationError) as error:
        store.append(
            FAMILY_CLOCK_ACTIVATION_RECORD_KIND,
            _opened_payload(
                policy_sha256,
                clock_state=CLOCK_CLOSED,
                blockers=[INELIGIBLE_SOURCE_BLOCKER],
                unsatisfied_preconditions=["eligible_source_registration"],
            ),
            idempotency_key="bcm0a:clock:closed:1",
            recorded_at=RECORDED_AT,
        )
    assert "operational_record.closed_clock_accrual_start" in str(error.value)


def test_a_closed_clock_must_name_a_blocker(
    store: OperationalStore, policy_sha256: str
) -> None:
    with pytest.raises(ContractValidationError) as error:
        store.append(
            FAMILY_CLOCK_ACTIVATION_RECORD_KIND,
            _opened_payload(
                policy_sha256,
                clock_state=CLOCK_CLOSED,
                accrual_start_known_at=None,
                blockers=[],
            ),
            idempotency_key="bcm0a:clock:closed:1",
            recorded_at=RECORDED_AT,
        )
    assert "operational_record.clock_closed_without_blocker" in str(error.value)


def test_the_built_payload_never_backfills_a_closed_family(
    policy: dict, sources: dict, policy_sha256: str
) -> None:
    decisions = evaluate_family_clocks(policy, sources, writer_available=True)
    for decision in decisions:
        payload = build_activation_payload(
            decision,
            policy_version=policy["policy_version"],
            policy_sha256=policy_sha256,
            evaluated_at=EVALUATED_AT,
            # Even when a caller hands one in, a closed clock records no start.
            accrual_start_known_at="2020-01-01T00:00:00Z",
        )
        assert payload["clock_state"] == CLOCK_CLOSED
        assert payload["accrual_start_known_at"] is None
