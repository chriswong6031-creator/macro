"""Tests for BC-M0a family clock activation.

These pin the honest answer as of the four-NCT forward-clock activation and,
more importantly, pin WHY it is that answer. BC-O1b exists and Record History's
bounded runtime and universe controls are armed, so exactly three source-fact
families can open. Endpoint readout still has an alignment-review blocker; the
other source and identity blockers remain.

The tests below prove three separate things:

1. the evaluator opens exactly the three reviewed families and names the exact
   blocker for every family that stays closed;
2. the frozen policy remains a declaration rather than pretending its old gate
   booleans are the live result; and
3. the operator CLI requires the exact open set before it writes nine
   append-only activation receipts.

Every store write runs under ``tmp_path``.  No production state root is
provisioned, no source is activated, and nothing accrues.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

import scripts.biocatalyst_family_clock_activation as activation_cli
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

OPEN_FAMILIES = (
    "trial_progression_termination",
    "timing_slip",
    "enrollment_site_change",
)
CANARY_NCTS = (
    "NCT04528082",
    "NCT05020236",
    "NCT06602479",
    "NCT07218380",
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


def test_record_history_is_rights_allowed_and_exactly_bounded_for_activation(
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
    assert control["default_enabled"] is True
    assert tuple(control["default_allowlist"]) == CANARY_NCTS
    assert control["universe_mode"] == "explicit_nct_allowlist"


def test_exactly_three_family_clocks_open_and_every_other_family_names_its_blocker(
    policy: dict, sources: dict
) -> None:
    decisions = _decisions(policy, sources)
    assert len(decisions) == 9
    assert {
        family_id for family_id, decision in decisions.items() if decision.opened
    } == set(OPEN_FAMILIES)
    for family_id, decision in decisions.items():
        if family_id in OPEN_FAMILIES:
            assert decision.blockers == (), family_id
            assert decision.unsatisfied_preconditions == (), family_id
        else:
            assert decision.blockers, family_id
        # The one precondition BC-O1b did discharge stays discharged.
        assert "o1b_outcome_writer" not in decision.unsatisfied_preconditions, family_id
        assert WRITER_ABSENT_BLOCKER not in decision.blockers, family_id


@pytest.mark.parametrize("family_id", OPEN_FAMILIES)
def test_each_reviewed_nct_keyed_family_opens_without_a_source_blocker(
    policy: dict, sources: dict, family_id: str
) -> None:
    decision = _decisions(policy, sources)[family_id]
    assert decision.clock_state == CLOCK_OPENED
    assert decision.ineligible_source_ids == ()
    assert decision.blockers == ()
    assert decision.unsatisfied_preconditions == ()


def test_endpoint_readout_stays_closed_on_alignment_review_not_source_eligibility(
    policy: dict, sources: dict
) -> None:
    decision = _decisions(policy, sources)["endpoint_readout"]
    assert decision.clock_state == CLOCK_CLOSED
    assert decision.ineligible_source_ids == ()
    assert decision.blockers == ("endpoint_alignment_review_queue_not_drained",)
    assert decision.unsatisfied_preconditions == ()


def test_the_frozen_policy_stays_a_declaration_and_the_receipt_is_live_authority(
    policy: dict, sources: dict
) -> None:
    # Opening a live clock must not rewrite the frozen M0a policy as though its
    # declaration were an operational receipt.
    decisions = _decisions(policy, sources)
    for family_id, family in policy["families"].items():
        gate = family["entry_gate"]
        assert gate["satisfied"] is False, family_id
        assert family["state"] == "clock_not_opened", family_id
    assert policy["clock_activation"]["clock_state_authority"] == (
        "activation_receipt_not_this_file"
    )
    assert {name for name, decision in decisions.items() if decision.opened} == set(
        OPEN_FAMILIES
    )


# ---- the closure is evidence, not a missing code path ----------------------


def _sources_with_dark_record_history(sources: dict) -> dict:
    dark = copy.deepcopy(sources)
    dark["b2_history_canary"]["default_enabled"] = False
    dark["b2_history_canary"]["default_allowlist"] = []
    return dark


def test_the_three_open_families_close_again_if_the_source_control_is_dark(
    policy: dict, sources: dict
) -> None:
    decisions = _decisions(policy, _sources_with_dark_record_history(sources))
    for family_id in OPEN_FAMILIES:
        decision = decisions[family_id]
        assert decision.clock_state == CLOCK_CLOSED, family_id
        assert decision.ineligible_source_ids == (RECORD_HISTORY,), family_id
        assert INELIGIBLE_SOURCE_BLOCKER in decision.blockers, family_id


def test_the_identity_gated_families_stay_closed_even_with_eligible_sources(
    policy: dict, sources: dict
) -> None:
    decisions = _decisions(policy, sources)
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
    decision = _decisions(
        forged, _sources_with_dark_record_history(sources)
    )["trial_progression_termination"]
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
        if payload["family_id"] in OPEN_FAMILIES:
            assert payload["clock_state"] == CLOCK_OPENED
            assert payload["blockers"] == []
            assert payload["accrual_start_known_at"] == EVALUATED_AT
        else:
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
    darkened = evaluate_family_clocks(
        policy, _sources_with_dark_record_history(sources), writer_available=True
    )
    with pytest.raises(OperationalStoreConflictError) as error:
        record_family_clock_activations(store, darkened, **kwargs)
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
        if decision.opened:
            continue
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


# ---- the explicit operator command ----------------------------------------


def _record_arguments(state_root: Path) -> list[str]:
    arguments = [
        "--mode",
        "record",
        "--state-root",
        str(state_root),
        "--evaluated-at",
        "2026-08-11T08:30:00Z",
    ]
    for family_id in OPEN_FAMILIES:
        arguments.extend(["--expected-open-family", family_id])
    return arguments


def test_preview_is_read_only_and_reports_the_exact_evidence_hashes(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "must-not-exist"
    out, err = io.StringIO(), io.StringIO()
    code = activation_cli.run(
        [
            "--mode",
            "preview",
            "--state-root",
            str(state_root),
            "--evaluated-at",
            "2026-08-11T08:30:00Z",
        ],
        repo_root=ROOT,
        stdout=out,
        stderr=err,
    )
    assert code == activation_cli.EXIT_OK
    assert err.getvalue() == ""
    assert not state_root.exists()
    summary = json.loads(out.getvalue())
    assert summary["action"] == "preview"
    assert summary["opened_family_ids"] == sorted(OPEN_FAMILIES)
    assert summary["record_count"] == 0
    assert summary["policy_sha256"] == hashlib.sha256(
        FAMILY_POLICY.read_bytes()
    ).hexdigest()
    assert summary["source_registry_sha256"] == hashlib.sha256(
        SOURCE_REGISTRY.read_bytes()
    ).hexdigest()


def test_record_refuses_an_unexpected_open_set_before_provisioning(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "must-not-exist"
    arguments = _record_arguments(state_root)
    arguments = arguments[:-2]
    arguments.append("--provision")
    out, err = io.StringIO(), io.StringIO()
    code = activation_cli.run(
        arguments, repo_root=ROOT, stdout=out, stderr=err
    )
    assert code == activation_cli.EXIT_PRECONDITION_FAILED
    assert out.getvalue() == ""
    assert "EXPECTED_OPEN_FAMILIES_MISMATCH" in err.getvalue()
    assert not state_root.exists()


def test_record_provisions_once_writes_nine_receipts_and_is_idempotent(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "operational"
    arguments = _record_arguments(state_root) + ["--provision"]
    first_out, first_err = io.StringIO(), io.StringIO()
    assert activation_cli.run(
        arguments, repo_root=ROOT, stdout=first_out, stderr=first_err
    ) == activation_cli.EXIT_OK
    assert first_err.getvalue() == ""
    first = json.loads(first_out.getvalue())
    assert first["record_count"] == 9
    assert first["created_record_count"] == 9
    assert first["existing_record_ids"] == []

    page = OperationalStore(state_root, repo_root=ROOT).read(
        FAMILY_CLOCK_ACTIVATION_RECORD_KIND, limit=MAX_QUERY_LIMIT
    )
    assert len(page.records) == 9
    assert {
        record["payload"]["family_id"]
        for record in page.records
        if record["payload"]["clock_state"] == CLOCK_OPENED
    } == set(OPEN_FAMILIES)
    for record in page.records:
        payload = record["payload"]
        if payload["clock_state"] == CLOCK_OPENED:
            assert payload["accrual_start_known_at"] == payload["evaluated_at"]

    second_out, second_err = io.StringIO(), io.StringIO()
    assert activation_cli.run(
        _record_arguments(state_root),
        repo_root=ROOT,
        stdout=second_out,
        stderr=second_err,
    ) == activation_cli.EXIT_OK
    second = json.loads(second_out.getvalue())
    assert second_err.getvalue() == ""
    assert second["created_record_count"] == 0
    assert len(second["existing_record_ids"]) == 9
    assert len(
        OperationalStore(state_root, repo_root=ROOT).read(
            FAMILY_CLOCK_ACTIVATION_RECORD_KIND, limit=MAX_QUERY_LIMIT
        ).records
    ) == 9


def test_record_refuses_to_provision_over_an_occupied_directory(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "occupied"
    state_root.mkdir()
    (state_root / "belongs-to-someone-else").write_text("keep", encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    code = activation_cli.run(
        _record_arguments(state_root) + ["--provision"],
        repo_root=ROOT,
        stdout=out,
        stderr=err,
    )
    assert code == activation_cli.EXIT_PRECONDITION_FAILED
    assert "OPERATIONAL_STATE_ROOT_OCCUPIED" in err.getvalue()
    assert (state_root / "belongs-to-someone-else").read_text() == "keep"


def test_record_refuses_a_symlinked_store_metadata_file(tmp_path: Path) -> None:
    state_root = tmp_path / "operational"
    state_root.mkdir()
    outside = tmp_path / "outside-meta.json"
    outside.write_text("{}", encoding="utf-8")
    (state_root / "store_meta.json").symlink_to(outside)
    out, err = io.StringIO(), io.StringIO()
    code = activation_cli.run(
        _record_arguments(state_root) + ["--provision"],
        repo_root=ROOT,
        stdout=out,
        stderr=err,
    )
    assert code == activation_cli.EXIT_PRECONDITION_FAILED
    assert "OPERATIONAL_STATE_ROOT_INVALID" in err.getvalue()
    assert outside.read_text() == "{}"
