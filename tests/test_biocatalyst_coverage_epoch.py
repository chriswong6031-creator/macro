"""Adversarial tests for the dark B1S4 recorded-denominator coverage lane.

Every test here is hermetic: the only transport is an injected scripted fake, no
test performs network I/O, no source is enabled, and nothing is published.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from collectors.biocatalyst.clinicaltrials_discovery import (
    ClinicalTrialsDiscoveryWalker,
    DiscoveryConfig,
    DiscoveryLimits,
    DiscoveryQuarantine,
    DiscoveryResponse,
    DiscoverySuccess,
    DiscoveryWindow,
)
import engine.biocatalyst.coverage_epoch as coverage_module
from engine.biocatalyst.coverage_epoch import (
    ADMISSION_DECISION_CONTRACT_ID,
    COHORT_ENLARGEMENT_REFUSAL,
    COMPLETE_STOP_CONDITION,
    DISCOVERY_AUTHORITY,
    LIFECYCLE_POLICY,
    VERSION_PROBES_PER_RUN,
    CoverageEpochError,
    build_attested_coverage_epoch,
    build_cohort_admission_decision,
    derive_coverage_denominator,
    included_run_payload_digest,
    validate_attested_coverage_epoch,
    validate_cohort_admission_decision,
)
from engine.biocatalyst.discovery import (
    build_discovery_coverage_epoch,
    build_discovery_scope,
    reconcile_discovery_run,
)
from engine.biocatalyst.fixed_cohort import admit_fixed_cohort_candidates
from engine.sector_intelligence import canonical_json_sha256, validate_contract
from engine.sector_intelligence.contracts import ContractValidationError


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "biocatalyst"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
TOKEN_A = "d" * 64
NOW = datetime(2026, 8, 3, 8, 30, tzinfo=timezone.utc)

EXCLUSIONS = [
    {
        "kind": "records_never_returned_by_the_declared_query_family",
        "description": "studies the declared /studies query family never returns",
    },
    {
        "kind": "records_outside_the_declared_selection_window",
        "description": "studies whose LastUpdatePostDate falls outside the declared window",
    },
]


# --------------------------------------------------------------------------
# Bounded builders mirroring the shipped discovery test idiom.
# --------------------------------------------------------------------------


def _scope(start: str = "2026-08-01", end: str = "2026-08-02", **overrides: Any) -> dict:
    return build_discovery_scope(selection_start_date=start, selection_end_date=end, **overrides)


def _page(
    *,
    ordinal: int = 0,
    request: str | None = None,
    next_token: str | None = None,
    total: int | None = 1,
    nct_id: str = "NCT00000001",
    content: str = HASH_B,
    updated: str = "2026-08-01",
    received_at: str = "2026-08-03T00:01:00Z",
    byte_count: int = 100,
    response: str | None = None,
) -> dict:
    return {
        "page_ordinal": ordinal,
        "response_sha256": response or (f"{ordinal:x}" * 64)[:64],
        "byte_count": byte_count,
        "received_at": received_at,
        "request_page_token_sha256": request,
        "next_page_token_sha256": next_token,
        "total_count": total,
        "records": [
            {
                "nct_id": nct_id,
                "canonical_content_sha256": content,
                "last_update_posted_date": updated,
            }
        ],
    }


def _version(*, retrieved_at: str = "2026-08-03T00:00:00Z") -> dict:
    return {
        "data_timestamp_raw": "2026-08-03T00:00:00Z",
        "api_version": "2.0",
        "retrieved_at": retrieved_at,
    }


def _run(
    *,
    scope: dict | None = None,
    run_id: str = "ctgov_discovery_run_one",
    pages: list[dict] | None = None,
    started_at: str = "2026-08-03T00:00:00Z",
    finished_at: str = "2026-08-03T00:03:00Z",
    transaction_from: str = "2026-08-03T00:03:00Z",
) -> dict:
    return reconcile_discovery_run(
        scope=scope or _scope(),
        run_id=run_id,
        pages=pages if pages is not None else [_page()],
        source_version_before=_version(),
        source_version_after=_version(retrieved_at="2026-08-03T00:02:00Z"),
        started_at=started_at,
        finished_at=finished_at,
        transaction_from=transaction_from,
    )


def _epoch(
    *,
    runs: list[dict] | None = None,
    coverage_epoch_id: str = "ctgov_discovery_coverage_b1s4",
    declared_start_date: str = "2026-08-01",
    declared_end_date: str = "2026-08-02",
    **overrides: Any,
) -> dict:
    kwargs: dict[str, Any] = {
        "known_exclusions": copy.deepcopy(EXCLUSIONS),
        "byte_budget": 1_000_000,
        "request_budget": 100,
        "wall_clock_budget_ms": 600_000,
        "min_request_interval_ms": 1_000,
    }
    kwargs.update(overrides)
    return build_attested_coverage_epoch(
        coverage_epoch_id=coverage_epoch_id,
        runs=runs if runs is not None else [_run()],
        declared_start_date=declared_start_date,
        declared_end_date=declared_end_date,
        transaction_from="2026-08-03T00:04:00Z",
        **kwargs,
    )


def _cohort() -> dict:
    return json.loads((FIXTURE_ROOT / "ctgov_fixed_cohort.v1.valid.json").read_text(encoding="utf-8"))


def _rehash_epoch(document: dict) -> dict:
    document["coverage_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in document.items() if key != "coverage_payload_sha256"}
    )
    return document


def _rehash_decision(document: dict) -> dict:
    identity = {
        key: value
        for key, value in document.items()
        if key not in {"decision_id", "decision_payload_sha256"}
    }
    document["decision_id"] = f"biocatalyst_cohort_admission_{canonical_json_sha256(identity)[:24]}"
    document["decision_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in document.items() if key != "decision_payload_sha256"}
    )
    return document


def _codes(caught: pytest.ExceptionInfo[ContractValidationError]) -> set[str]:
    return {issue.code for issue in caught.value.issues}


def _assert_epoch_rejected(document: dict, code: str, **kwargs: Any) -> None:
    with pytest.raises(ContractValidationError) as caught:
        validate_attested_coverage_epoch(document, **kwargs)
    assert code in _codes(caught)


# --------------------------------------------------------------------------
# Injected-transport fake.  No test in this module touches the network.
# --------------------------------------------------------------------------


class ScriptedTransport:
    """A strict fake: any extra fetch or wrong path is an immediate test fault."""

    def __init__(self, responses: list[tuple[str, DiscoveryResponse]]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def get(self, path: str, *, params, headers) -> DiscoveryResponse:
        self.calls.append(path)
        if not self._responses:
            raise AssertionError(f"unexpected extra source fetch for {path}")
        expected_path, response = self._responses.pop(0)
        if path != expected_path:
            raise AssertionError(f"expected {expected_path}, received {path}")
        return response


class IncrementingClock:
    def __init__(self) -> None:
        self._ticks = 0

    def __call__(self) -> datetime:
        value = NOW + timedelta(seconds=self._ticks)
        self._ticks += 1
        return value


def _response(body: bytes) -> DiscoveryResponse:
    return DiscoveryResponse(
        status_code=200,
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "identity",
            "Content-Length": str(len(body)),
        },
        body=body,
    )


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def _study(nct_id: str, date_value: str) -> dict[str, Any]:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id},
            "statusModule": {"lastUpdatePostDateStruct": {"date": date_value}},
        }
    }


def _walk(responses: list[tuple[str, DiscoveryResponse]]) -> object:
    config = DiscoveryConfig(
        window=DiscoveryWindow("2026-08-01", "2026-08-03"),
        limits=DiscoveryLimits(
            page_size=1,
            page_cap=3,
            max_records=3,
            max_response_bytes=4_096,
            max_total_response_bytes=16_384,
            max_record_bytes=4_096,
            max_token_bytes=128,
            max_string_bytes=128,
        ),
        user_agent="MastermindX-BioCatalyst/coverage-epoch-test (ops@example.invalid)",
    )
    walker = ClinicalTrialsDiscoveryWalker(
        config=config, transport=ScriptedTransport(responses), now_fn=IncrementingClock()
    )
    return walker.walk(), walker


# --------------------------------------------------------------------------
# The recorded denominator.
# --------------------------------------------------------------------------


def test_attested_epoch_records_denominator_budget_lifecycle_and_authority() -> None:
    run = _run()
    epoch = _epoch(runs=[run])

    validate_contract(epoch, repo_root=ROOT)
    assert epoch["coverage_state"] == "complete"
    assert epoch["coverage_denominator"] == {
        "basis": "recorded_source_declared_total_count_per_included_scope",
        "semantics": "denominator_is_recorded_evidence_not_inferred_from_query_breadth",
        "declared_total_by_scope": [{"scope_ref": run["scope_ref"], "declared_total_count": 1}],
        "declared_total_sum": 1,
        "observed_unique_records": 1,
        "unreconciled_records": 0,
        "known_exclusions": sorted(EXCLUSIONS, key=lambda row: row["kind"]),
    }
    assert epoch["budget_ledger"] == {
        "byte_budget": 1_000_000,
        "bytes_spent": 100,
        "request_budget": 100,
        "requests_spent": 1 + VERSION_PROBES_PER_RUN,
        "wall_clock_budget_ms": 600_000,
        "wall_clock_spent_ms": 180_000,
        "min_request_interval_ms": 1_000,
        "observed_min_request_interval_ms": 60_000,
        "stop_condition": COMPLETE_STOP_CONDITION,
    }
    assert epoch["lifecycle"] == {
        **LIFECYCLE_POLICY,
        "included_run_payload_digest_sha256": canonical_json_sha256([run["run_payload_sha256"]]),
        "supersedes_coverage_epoch_id": None,
        "superseded_by_coverage_epoch_id": None,
        "withdrawn_at": None,
        "withdrawal_reason_code": None,
    }
    assert epoch["discovery_authority"] == DISCOVERY_AUTHORITY
    # Replay determinism: the epoch is a pure function of its recorded inputs.
    assert _epoch(runs=[run]) == epoch
    assert validate_attested_coverage_epoch(epoch, runs=[run]) == epoch


def test_a_coverage_claim_without_a_recorded_denominator_claims_nothing() -> None:
    run = _run()
    # The already-shipped builder proves an atomic window and nothing about how
    # much of the source it covers.  That document may not claim coverage here.
    unattested = build_discovery_coverage_epoch(
        coverage_epoch_id="ctgov_discovery_coverage_unattested",
        runs=[run],
        declared_start_date="2026-08-01",
        declared_end_date="2026-08-02",
        transaction_from="2026-08-03T00:04:00Z",
    )
    _assert_epoch_rejected(unattested, "coverage_epoch.unrecorded_denominator")

    stripped = copy.deepcopy(_epoch(runs=[run]))
    del stripped["coverage_denominator"]
    _assert_epoch_rejected(_rehash_epoch(stripped), "coverage_epoch.unrecorded_denominator")

    without_exclusions = copy.deepcopy(_epoch(runs=[run]))
    without_exclusions["coverage_denominator"]["known_exclusions"] = []
    # The contract owns the empty case; the semantic layer owns it independently
    # so a caller that skips schema validation still cannot claim coverage.
    _assert_epoch_rejected(_rehash_epoch(without_exclusions), "schema")
    assert "coverage_epoch.unrecorded_denominator" in {
        issue.code
        for issue in coverage_module.attested_coverage_epoch_semantic_issues(without_exclusions)
    }
    with pytest.raises(CoverageEpochError, match="COVERAGE_EXCLUSIONS_REQUIRED"):
        _epoch(runs=[run], known_exclusions=[])


def test_a_wide_query_may_not_borrow_a_denominator_it_never_ran() -> None:
    run = _run()
    epoch = copy.deepcopy(_epoch(runs=[run]))
    wide_scope = _scope("2026-08-01", "2026-08-02", page_size=1, page_cap=2, record_cap=2)
    assert wide_scope["scope_id"] != run["scope_ref"]

    epoch["coverage_denominator"]["declared_total_by_scope"] = [
        {"scope_ref": wide_scope["scope_id"], "declared_total_count": 500_000 // 1000}
    ]
    epoch["coverage_denominator"]["declared_total_sum"] = 500
    epoch["coverage_denominator"]["unreconciled_records"] = 499
    _assert_epoch_rejected(_rehash_epoch(epoch), "coverage_epoch.denominator_scope_binding")


def test_denominator_arithmetic_ordering_and_replay_are_exact() -> None:
    run = _run()
    inflated = copy.deepcopy(_epoch(runs=[run]))
    inflated["coverage_denominator"]["declared_total_sum"] = 500
    _assert_epoch_rejected(_rehash_epoch(inflated), "coverage_epoch.denominator_arithmetic")

    unreconciled = copy.deepcopy(_epoch(runs=[run]))
    unreconciled["coverage_denominator"]["unreconciled_records"] = 7
    _assert_epoch_rejected(_rehash_epoch(unreconciled), "coverage_epoch.denominator_arithmetic")

    understated = copy.deepcopy(_epoch(runs=[run]))
    understated["coverage_denominator"]["observed_unique_records"] = 0
    understated["coverage_denominator"]["unreconciled_records"] = 1
    _assert_epoch_rejected(
        _rehash_epoch(understated), "coverage_epoch.denominator_replay", runs=[run]
    )

    duplicated = copy.deepcopy(_epoch(runs=[run]))
    duplicated["coverage_denominator"]["known_exclusions"] = [
        dict(EXCLUSIONS[0]),
        dict(EXCLUSIONS[0]) | {"description": "a second description for the same kind"},
    ]
    _assert_epoch_rejected(_rehash_epoch(duplicated), "coverage_epoch.exclusion_kind")
    with pytest.raises(CoverageEpochError, match="COVERAGE_EXCLUSION_DUPLICATE_KIND"):
        _epoch(runs=[run], known_exclusions=[dict(EXCLUSIONS[0]), dict(EXCLUSIONS[0])])
    with pytest.raises(CoverageEpochError, match="COVERAGE_EXCLUSION_KIND_UNKNOWN"):
        _epoch(
            runs=[run],
            known_exclusions=[{"kind": "everything_else", "description": "unreviewed"}],
        )


def test_denominator_refuses_more_observed_records_than_the_source_declared() -> None:
    scope = _scope("2026-08-01", "2026-08-02", page_size=1, page_cap=2, record_cap=2)
    run = _run(
        scope=scope,
        pages=[
            _page(next_token=TOKEN_A, total=2),
            _page(
                ordinal=1,
                request=TOKEN_A,
                total=2,
                nct_id="NCT00000002",
                content=HASH_C,
                updated="2026-08-02",
                received_at="2026-08-03T00:01:30Z",
            ),
        ],
    )
    forged = copy.deepcopy(run)
    forged["counts"]["declared_total_count"] = 1

    with pytest.raises(CoverageEpochError, match="COVERAGE_DENOMINATOR_UNRECONCILED"):
        derive_coverage_denominator([forged], known_exclusions=EXCLUSIONS)


# --------------------------------------------------------------------------
# Budgets and stop conditions.
# --------------------------------------------------------------------------


def test_budgets_bound_the_walk_and_a_budget_stop_may_never_claim_completion() -> None:
    run = _run()
    with pytest.raises(CoverageEpochError, match="COVERAGE_BUDGET_EXCEEDED"):
        _epoch(runs=[run], byte_budget=99)
    with pytest.raises(CoverageEpochError, match="COVERAGE_BUDGET_EXCEEDED"):
        _epoch(runs=[run], request_budget=2)
    with pytest.raises(CoverageEpochError, match="COVERAGE_BUDGET_EXCEEDED"):
        _epoch(runs=[run], wall_clock_budget_ms=179_999)
    with pytest.raises(CoverageEpochError, match="COVERAGE_RATE_LIMIT_VIOLATION"):
        _epoch(runs=[run], min_request_interval_ms=60_001)
    with pytest.raises(CoverageEpochError, match="COVERAGE_STOP_CONDITION_CONTRADICTS_CLAIM"):
        _epoch(runs=[run], stop_condition="byte_budget_reached")
    with pytest.raises(CoverageEpochError, match="COVERAGE_STOP_CONDITION_UNKNOWN"):
        _epoch(runs=[run], stop_condition="operator_said_it_was_fine")

    forged_stop = copy.deepcopy(_epoch(runs=[run]))
    forged_stop["budget_ledger"]["stop_condition"] = "record_cap_reached"
    _assert_epoch_rejected(_rehash_epoch(forged_stop), "coverage_epoch.stop_condition")

    overspent = copy.deepcopy(_epoch(runs=[run]))
    overspent["budget_ledger"]["byte_budget"] = 10
    _assert_epoch_rejected(_rehash_epoch(overspent), "coverage_epoch.budget_exceeded")

    understated_spend = copy.deepcopy(_epoch(runs=[run]))
    understated_spend["budget_ledger"]["bytes_spent"] = 1
    _assert_epoch_rejected(
        _rehash_epoch(understated_spend), "coverage_epoch.budget_replay", runs=[run]
    )

    throttled = copy.deepcopy(_epoch(runs=[run]))
    throttled["budget_ledger"]["min_request_interval_ms"] = 60_001
    _assert_epoch_rejected(_rehash_epoch(throttled), "coverage_epoch.rate_limit")

    missing = copy.deepcopy(_epoch(runs=[run]))
    del missing["budget_ledger"]
    _assert_epoch_rejected(_rehash_epoch(missing), "coverage_epoch.unrecorded_budget")


# --------------------------------------------------------------------------
# Replay, correction, withdrawal and rollback.
# --------------------------------------------------------------------------


def test_lifecycle_binds_replay_correction_withdrawal_and_rollback() -> None:
    run = _run()
    epoch = _epoch(runs=[run])
    assert included_run_payload_digest(epoch["included_runs"]) == epoch["lifecycle"][
        "included_run_payload_digest_sha256"
    ]

    forged_digest = copy.deepcopy(epoch)
    forged_digest["lifecycle"]["included_run_payload_digest_sha256"] = HASH_A
    _assert_epoch_rejected(_rehash_epoch(forged_digest), "coverage_epoch.replay_digest")

    open_but_withdrawn = copy.deepcopy(epoch)
    open_but_withdrawn["lifecycle"]["withdrawn_at"] = "2026-08-04T00:00:00Z"
    open_but_withdrawn["lifecycle"]["withdrawal_reason_code"] = "source_correction"
    _assert_epoch_rejected(_rehash_epoch(open_but_withdrawn), "coverage_epoch.lifecycle")

    closed_without_successor = copy.deepcopy(epoch)
    closed_without_successor["transaction_to"] = "2026-08-04T00:00:00Z"
    _assert_epoch_rejected(_rehash_epoch(closed_without_successor), "coverage_epoch.lifecycle")

    mismatched_withdrawal = copy.deepcopy(epoch)
    mismatched_withdrawal["transaction_to"] = "2026-08-04T00:00:00Z"
    mismatched_withdrawal["lifecycle"]["withdrawn_at"] = "2026-08-05T00:00:00Z"
    mismatched_withdrawal["lifecycle"]["withdrawal_reason_code"] = "source_correction"
    _assert_epoch_rejected(_rehash_epoch(mismatched_withdrawal), "coverage_epoch.lifecycle")

    self_superseded = copy.deepcopy(epoch)
    self_superseded["transaction_to"] = "2026-08-04T00:00:00Z"
    self_superseded["lifecycle"]["superseded_by_coverage_epoch_id"] = epoch["coverage_epoch_id"]
    _assert_epoch_rejected(_rehash_epoch(self_superseded), "coverage_epoch.lifecycle")

    forged_policy = copy.deepcopy(epoch)
    forged_policy["lifecycle"]["rollback_policy"] = LIFECYCLE_POLICY["correction_policy"]
    # The contract pins each policy constant; the semantic layer pins them again
    # so a caller reaching for the issue list alone still fails closed.
    _assert_epoch_rejected(_rehash_epoch(forged_policy), "schema")
    assert "coverage_epoch.lifecycle" in {
        issue.code
        for issue in coverage_module.attested_coverage_epoch_semantic_issues(forged_policy)
    }

    withdrawn = copy.deepcopy(epoch)
    withdrawn["transaction_to"] = "2026-08-04T00:00:00Z"
    withdrawn["lifecycle"]["withdrawn_at"] = "2026-08-04T00:00:00Z"
    withdrawn["lifecycle"]["withdrawal_reason_code"] = "denominator_unreconciled"
    assert validate_attested_coverage_epoch(_rehash_epoch(withdrawn))["transaction_to"] == (
        "2026-08-04T00:00:00Z"
    )

    corrected = _epoch(
        coverage_epoch_id="ctgov_discovery_coverage_b1s4_correction",
        runs=[run],
        supersedes_coverage_epoch_id=epoch["coverage_epoch_id"],
    )
    assert corrected["lifecycle"]["supersedes_coverage_epoch_id"] == epoch["coverage_epoch_id"]
    with pytest.raises(CoverageEpochError, match="COVERAGE_LIFECYCLE_SUPERSEDES_INVALID"):
        _epoch(runs=[run], supersedes_coverage_epoch_id="ctgov_discovery_coverage_b1s4")


def test_discovery_authority_may_never_carry_identity_or_model_authority() -> None:
    epoch = copy.deepcopy(_epoch())
    epoch["discovery_authority"]["identity_inference"] = "company_join_allowed"
    _assert_epoch_rejected(_rehash_epoch(epoch), "schema")
    assert "coverage_epoch.authority" in {
        issue.code
        for issue in coverage_module.attested_coverage_epoch_semantic_issues(epoch)
    }

    stripped = copy.deepcopy(_epoch())
    del stripped["discovery_authority"]
    _assert_epoch_rejected(_rehash_epoch(stripped), "coverage_epoch.authority")


# --------------------------------------------------------------------------
# Deterministic admission into a reviewed fixed cohort.
# --------------------------------------------------------------------------


def test_cohort_enlargement_refusal_is_the_sibling_controls_own_verdict() -> None:
    with pytest.raises(ValueError) as caught:
        admit_fixed_cohort_candidates(_cohort(), ["NCT00000009"], repo_root=ROOT)

    # If the sibling ever rewords this refusal, admission classification here
    # must go red rather than silently misread a refusal as a broken input.
    assert str(caught.value) == COHORT_ENLARGEMENT_REFUSAL


def test_admission_is_deterministic_and_never_enlarges_a_reviewed_cohort() -> None:
    scope = _scope("2026-08-01", "2026-08-02", page_size=1, page_cap=3, record_cap=3)
    run = _run(
        scope=scope,
        pages=[
            _page(next_token=TOKEN_A, total=3),
            _page(
                ordinal=1,
                request=TOKEN_A,
                next_token=HASH_B,
                total=3,
                nct_id="NCT00000002",
                content=HASH_C,
                updated="2026-08-02",
                received_at="2026-08-03T00:01:20Z",
            ),
            _page(
                ordinal=2,
                request=HASH_B,
                total=3,
                nct_id="NCT00000009",
                content=HASH_A,
                updated="2026-08-02",
                received_at="2026-08-03T00:01:40Z",
            ),
        ],
    )
    epoch = _epoch(runs=[run], min_request_interval_ms=0)
    cohort = _cohort()

    decision = build_cohort_admission_decision(
        epoch=epoch,
        runs=[run],
        cohort=cohort,
        candidates=["NCT00000002", "NCT00000009", "NCT00000007"],
        decided_at="2026-08-03T01:00:00Z",
        repo_root=ROOT,
    )

    validate_contract(decision, repo_root=ROOT)
    assert decision["contract_id"] == ADMISSION_DECISION_CONTRACT_ID
    assert decision["admitted_nct_ids"] == ["NCT00000002"]
    assert decision["refused_nct_ids"] == ["NCT00000007", "NCT00000009"]
    assert decision["decisions"] == [
        {
            "nct_id": "NCT00000002",
            "decision": "admitted",
            "reason": "nominated_reviewed_cohort_member",
        },
        {
            "nct_id": "NCT00000007",
            "decision": "refused",
            "reason": "not_recorded_in_the_bound_coverage_epoch",
        },
        {
            "nct_id": "NCT00000009",
            "decision": "refused",
            "reason": "not_a_reviewed_cohort_member",
        },
    ]
    assert decision["reviewed_membership_bound"] == len(cohort["nct_ids"])
    assert decision["discovered_record_count"] == 3

    understated_discovery = copy.deepcopy(decision)
    understated_discovery["discovered_record_count"] = 1
    with pytest.raises(ContractValidationError) as caught:
        validate_cohort_admission_decision(
            _rehash_decision(understated_discovery), repo_root=ROOT
        )
    assert "cohort_admission.discovery_binding" in _codes(caught)

    assert decision["coverage_epoch_ref"] == epoch["coverage_epoch_id"]
    assert decision["coverage_payload_sha256"] == epoch["coverage_payload_sha256"]

    # Reproducible from exactly the recorded inputs.
    assert (
        build_cohort_admission_decision(
            epoch=epoch,
            runs=[run],
            cohort=cohort,
            candidates=["NCT00000009", "NCT00000007", "NCT00000002"],
            decided_at="2026-08-03T01:00:00Z",
            repo_root=ROOT,
        )
        == decision
    )
    assert validate_cohort_admission_decision(
        decision, cohort=cohort, epoch=epoch, repo_root=ROOT
    ) == decision

    enlarged = copy.deepcopy(decision)
    enlarged["decisions"][2]["decision"] = "admitted"
    enlarged["decisions"][2]["reason"] = "nominated_reviewed_cohort_member"
    enlarged["admitted_nct_ids"] = ["NCT00000002", "NCT00000009"]
    enlarged["refused_nct_ids"] = ["NCT00000007"]
    with pytest.raises(ContractValidationError) as caught:
        validate_cohort_admission_decision(
            _rehash_decision(enlarged), cohort=cohort, repo_root=ROOT
        )
    assert "cohort_admission.enlargement" in _codes(caught)

    overbound = copy.deepcopy(decision)
    overbound["reviewed_membership_bound"] = 1
    overbound["admitted_nct_ids"] = ["NCT00000001", "NCT00000002"]
    overbound["decisions"] = [
        {
            "nct_id": "NCT00000001",
            "decision": "admitted",
            "reason": "nominated_reviewed_cohort_member",
        },
        {
            "nct_id": "NCT00000002",
            "decision": "admitted",
            "reason": "nominated_reviewed_cohort_member",
        },
    ]
    overbound["refused_nct_ids"] = []
    with pytest.raises(ContractValidationError) as caught:
        validate_cohort_admission_decision(_rehash_decision(overbound), repo_root=ROOT)
    assert "cohort_admission.enlargement" in _codes(caught)


def test_admission_refuses_undiscovered_candidates_and_unearned_coverage() -> None:
    run = _run()
    epoch = _epoch(runs=[run])
    cohort = _cohort()

    decision = build_cohort_admission_decision(
        epoch=epoch,
        runs=[run],
        cohort=cohort,
        candidates=["NCT00000002"],
        decided_at="2026-08-03T01:00:00Z",
        repo_root=ROOT,
    )
    # NCT00000002 is a reviewed member but this epoch never recorded it.
    assert decision["admitted_nct_ids"] == []
    assert decision["decisions"][0]["reason"] == "not_recorded_in_the_bound_coverage_epoch"

    unattested = build_discovery_coverage_epoch(
        coverage_epoch_id="ctgov_discovery_coverage_admission_unattested",
        runs=[run],
        declared_start_date="2026-08-01",
        declared_end_date="2026-08-02",
        transaction_from="2026-08-03T00:04:00Z",
    )
    with pytest.raises(ContractValidationError) as caught:
        build_cohort_admission_decision(
            epoch=unattested,
            runs=[run],
            cohort=cohort,
            candidates=["NCT00000001"],
            decided_at="2026-08-03T01:00:00Z",
            repo_root=ROOT,
        )
    assert "coverage_epoch.unrecorded_denominator" in _codes(caught)

    with pytest.raises(CoverageEpochError, match="COVERAGE_ADMISSION_CANDIDATE_CAP_INVALID"):
        build_cohort_admission_decision(
            epoch=epoch,
            runs=[run],
            cohort=cohort,
            candidates=[],
            decided_at="2026-08-03T01:00:00Z",
            repo_root=ROOT,
        )
    with pytest.raises(CoverageEpochError, match="COVERAGE_ADMISSION_CANDIDATES_INVALID"):
        build_cohort_admission_decision(
            epoch=epoch,
            runs=[run],
            cohort=cohort,
            candidates=["NCT00000001", "NCT00000001"],
            decided_at="2026-08-03T01:00:00Z",
            repo_root=ROOT,
        )
    backdated = copy.deepcopy(decision)
    backdated["decided_at"] = "2026-08-03T00:00:00Z"
    backdated["transaction_from"] = "2026-08-03T00:00:00Z"
    with pytest.raises(ContractValidationError) as caught:
        validate_cohort_admission_decision(_rehash_decision(backdated), repo_root=ROOT)
    assert "cohort_admission.knowledge_time" in _codes(caught)


# --------------------------------------------------------------------------
# Injected fake transport: pagination, termination, totals, duplicates, drift.
# --------------------------------------------------------------------------


def test_injected_transport_walk_feeds_an_attested_epoch_and_admission() -> None:
    version = _fixture_bytes("ctgov_discovery_version.v1.json")
    result, walker = _walk(
        [
            ("/version", _response(version)),
            ("/studies", _response(_fixture_bytes("ctgov_discovery_page_1.v1.json"))),
            ("/studies", _response(_fixture_bytes("ctgov_discovery_page_2.v1.json"))),
            ("/version", _response(version)),
        ]
    )

    assert isinstance(result, DiscoverySuccess)
    pages, before, after = result.engine_reconciliation_inputs()
    scope = build_discovery_scope(**walker.config.engine_scope_kwargs())
    run = reconcile_discovery_run(
        scope=scope,
        run_id="ctgov_discovery_run_injected_transport",
        pages=pages,
        source_version_before=before,
        source_version_after=after,
        started_at=result.retrieval_started_at,
        finished_at=result.retrieval_finished_at,
        transaction_from=result.retrieval_finished_at,
    )
    assert run["run_state"] == "complete"

    epoch = build_attested_coverage_epoch(
        coverage_epoch_id="ctgov_discovery_coverage_injected_transport",
        runs=[run],
        declared_start_date="2026-08-01",
        declared_end_date="2026-08-03",
        transaction_from=result.retrieval_finished_at,
        known_exclusions=copy.deepcopy(EXCLUSIONS),
        byte_budget=100_000,
        request_budget=10,
        wall_clock_budget_ms=600_000,
        min_request_interval_ms=0,
    )
    validate_contract(epoch, repo_root=ROOT)
    assert epoch["coverage_denominator"]["declared_total_sum"] == 2
    assert epoch["coverage_denominator"]["observed_unique_records"] == 2
    assert epoch["coverage_denominator"]["unreconciled_records"] == 0
    assert epoch["budget_ledger"]["requests_spent"] == 2 + VERSION_PROBES_PER_RUN

    decision = build_cohort_admission_decision(
        epoch=epoch,
        runs=[run],
        cohort=_cohort(),
        candidates=["NCT00000001", "NCT00000002"],
        decided_at=epoch["transaction_from"],
        repo_root=ROOT,
    )
    assert decision["admitted_nct_ids"] == ["NCT00000001", "NCT00000002"]
    assert decision["refused_nct_ids"] == []


@pytest.mark.parametrize(
    ("pages", "expected_code"),
    [
        # A continuation token after terminal evidence is not a longer walk.
        (
            [
                {
                    "studies": [_study("NCT00000001", "2026-08-01")],
                    "totalCount": 1,
                    "nextPageToken": "again",
                }
            ],
            "TERMINAL_PAGE_CONTRADICTION",
        ),
        # totalCount must not move between pages of one walk.
        (
            [
                {
                    "studies": [_study("NCT00000001", "2026-08-01")],
                    "totalCount": 2,
                    "nextPageToken": "second",
                },
                {"studies": [_study("NCT00000002", "2026-08-02")], "totalCount": 3},
            ],
            "TOTAL_COUNT_MISMATCH",
        ),
        # A repeated identifier is ambiguity, never a silently deduplicated batch.
        (
            [
                {
                    "studies": [_study("NCT00000001", "2026-08-01")],
                    "totalCount": 2,
                    "nextPageToken": "second",
                },
                {"studies": [_study("NCT00000001", "2026-08-01")], "totalCount": 2},
            ],
            "DUPLICATE_NCT_ID_SAME_PAYLOAD",
        ),
        # A repeating pagination token is a cycle, not progress.
        (
            [
                {
                    "studies": [_study("NCT00000001", "2026-08-01")],
                    "totalCount": 3,
                    "nextPageToken": "loop",
                },
                {
                    "studies": [_study("NCT00000002", "2026-08-02")],
                    "totalCount": 3,
                    "nextPageToken": "loop",
                },
            ],
            "PAGINATION_CYCLE",
        ),
    ],
)
def test_injected_transport_pagination_and_total_count_faults_quarantine_empty(
    pages: list[dict[str, Any]], expected_code: str
) -> None:
    version = _fixture_bytes("ctgov_discovery_version.v1.json")
    responses = [("/version", _response(version))]
    responses.extend(("/studies", _response(_json_bytes(page))) for page in pages)
    responses.append(("/version", _response(version)))

    result, _ = _walk(responses)

    assert isinstance(result, DiscoveryQuarantine)
    assert result.error_code == expected_code
    assert result.candidates == ()


def test_injected_transport_version_drift_quarantines_the_whole_walk() -> None:
    before = _fixture_bytes("ctgov_discovery_version.v1.json")
    after = _json_bytes({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T09:00:00"})
    result, _ = _walk(
        [
            ("/version", _response(before)),
            (
                "/studies",
                _response(
                    _json_bytes(
                        {"studies": [_study("NCT00000001", "2026-08-01")], "totalCount": 1}
                    )
                ),
            ),
            ("/version", _response(after)),
        ]
    )

    assert isinstance(result, DiscoveryQuarantine)
    assert result.error_code == "SOURCE_CHANGED_MID_RUN"
    assert result.candidates == ()


# --------------------------------------------------------------------------
# The lane stays dark.
# --------------------------------------------------------------------------


def test_coverage_epoch_module_opens_no_transport_service_route_or_publication() -> None:
    source = inspect.getsource(coverage_module)

    for forbidden in ("import requests", "requests.", "urllib", "httpx", "boto3", "APIRouter"):
        assert forbidden not in source
    for forbidden_entrypoint in (
        "requests",
        "Session",
        "publish",
        "storage",
        "app",
        "router",
        "worker",
        "main",
    ):
        assert not hasattr(coverage_module, forbidden_entrypoint)
    assert "def main" not in source
