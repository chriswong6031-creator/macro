#!/usr/bin/env python3
"""Build the immutable zero-denominator sparse-selector preregistration receipt.

This is deliberately not a selector.  It freezes the future candidate/decision
contract while proving that the only committed campaign corpus at registration
is the retired eight-row v1 retrospective ledger.  The output therefore has an
empty candidate denominator, no decisions, no proposals, and no authority.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BENCHMARK_PATH = Path("research/momoedge/completion_benchmark_prereg_v1.json")
BENCHMARK_SCHEMA_PATH = Path(
    "contracts/research/momoedge_oracle_completion_benchmark_prereg.v1.schema.json"
)
LEGACY_CAMPAIGN_PATH = Path("data/options_signal_episode/campaigns.jsonl")
LEGACY_CAMPAIGN_SCHEMA_PATH = Path(
    "contracts/options/options.signal_campaign.v1.schema.json"
)
CAMPAIGN_V2_SCHEMA_PATH = Path(
    "contracts/options/options.signal_campaign.v2.schema.json"
)
CAMPAIGN_V2_IMPLEMENTATION_PATH = Path("engine/options_signal_campaign.py")
RECEIPT_PATH = Path(
    "research/options_estate/sparse_selector_preregistration_receipt_v1.json"
)
RECEIPT_SCHEMA_PATH = Path(
    "contracts/options/options.sparse_selector_activation_receipt.v1.schema.json"
)
CONTEXT_REFERENCE_SCHEMA_PATH = Path(
    "contracts/options/options.market_memory_context_reference.v1.schema.json"
)
CONTEXT_REFERENCE_IMPLEMENTATION_PATH = Path(
    "engine/options_market_memory_context.py"
)
CONTEXT_RECEIPT_STORE_IMPLEMENTATION_PATH = Path(
    "engine/options_market_memory_receipt_store.py"
)
CONTEXT_RECEIPT_HEAD_SCHEMA_PATH = Path(
    "contracts/options/options.market_memory_context_receipt_head.v1.schema.json"
)
CONTEXT_REFERENCE_SET_SCHEMA_PATH = Path(
    "contracts/options/options.market_memory_context_reference_set.v1.schema.json"
)
MARKET_MEMORY_CANARY_IDENTITY_PATH = Path("config/market_memory_canary.v1.json")
LIFECYCLE_EVENT_SCHEMA_PATH = Path(
    "contracts/options/prophet.option_shadow_lifecycle_event.v1.schema.json"
)
LIFECYCLE_STATE_IMPLEMENTATION_PATH = Path(
    "scripts/build_prophet_option_shadow_lifecycle.py"
)
NYSE_RTH_WINDOW_IMPLEMENTATION_PATH = Path("engine/session_digest.py")
NYSE_SESSION_CALENDAR_IMPLEMENTATION_PATH = Path("lib/nyse_calendar.py")

SCHEMA = "options.sparse_selector_activation_receipt/v1"
BENCHMARK_SCHEMA = "momoedge.completion_benchmark_prereg/v1"
BENCHMARK_DIGEST = "20e6c19f691cf9a07381288d6bdb33c6d74c8957b074ceefcdaf0ab8da1b1f42"
BENCHMARK_FILE_SHA256 = "a093804a2394ad5deff01181d2680eea64fa208f7f1d7e0a013c9cce3d806a63"
BENCHMARK_FILE_BYTES = 25_677
BENCHMARK_REGISTERED_AT = "2026-08-11T14:30:19Z"
BENCHMARK_BASELINE_COMMIT = "e1100ee158a8b18576bbc6130276ef6f8becd373"
BENCHMARK_FIRST_MAIN_COMMIT = "c46daec89ce2f25bdff85200eaf29f6de3e1572e"
BENCHMARK_FIRST_MAIN_COMMITTED_AT = "2026-08-11T15:47:06Z"
BENCHMARK_EFFECTIVE_FREEZE_AT = "2026-08-11T15:47:06Z"
REGISTERED_AT = "2026-08-11T22:43:53Z"
REPOSITORY = "mastermindx-market-intelligence/macro"
CAMPAIGN_V2_SOURCE_COMMIT = "d8e290032710d84e538c32af0d58358a16407c88"
SELECTOR_EFFECTIVE_FREEZE_AT = "2026-08-12T13:30:00Z"
SELECTOR_EFFECTIVE_FREEZE_SESSION = "2026-08-12"
SELECTOR_EFFECTIVE_FREEZE_RULE = (
    "preregistered_next_nyse_session_open_after_finalized_rule_head_with_"
    "origin_main_before_boundary/v1"
)

CAMPAIGN_V2_CONTRACT_RECEIPTS = [
    {
        "role": "campaign_v2_schema",
        "path": CAMPAIGN_V2_SCHEMA_PATH.as_posix(),
        "file_sha256": "65ce2f0fe1cb16dfca58949a85562645be4a41eb454b5ce243c16011c8a251a3",
        "file_bytes": 7_177,
        "source_commit": CAMPAIGN_V2_SOURCE_COMMIT,
    },
    {
        "role": "campaign_v2_runtime",
        "path": CAMPAIGN_V2_IMPLEMENTATION_PATH.as_posix(),
        "file_sha256": "f5d0a83c7fd35ee219aad448cef7384df98e1ee04b87d36ae631b0d273e4310c",
        "file_bytes": 46_774,
        "source_commit": CAMPAIGN_V2_SOURCE_COMMIT,
    },
]

CONTEXT_REFERENCE_CONTRACT_RECEIPTS = [
    {
        "role": "reference_schema",
        "path": CONTEXT_REFERENCE_SCHEMA_PATH.as_posix(),
        "file_sha256": "3e00b4410e9e9f6b5328a55e572219a61b0cad21e656c002fbedcf0cd4cd88b4",
        "file_bytes": 8_142,
        "source_commit": "c2ea5ef44a37976b91ad1636c438160c8e11ad68",
    },
    {
        "role": "reference_validator_implementation",
        "path": CONTEXT_REFERENCE_IMPLEMENTATION_PATH.as_posix(),
        "file_sha256": "7d3b410f6997a29299728b1f806956781803a89053f0cf8e016c315c3c296f82",
        "file_bytes": 45_021,
        "source_commit": "6e2c3f5e0ce3bd94eb00e0fad8fee353ae905aa7",
    },
    {
        "role": "reviewed_canary_identity_config",
        "path": MARKET_MEMORY_CANARY_IDENTITY_PATH.as_posix(),
        "file_sha256": "5e7823e48866b2c0828122b65f684ed5872c6816a6224f61e44db4c03d129b33",
        "file_bytes": 1_650,
        "source_commit": "f57e081bc5fc84999011558d8e65a4466d3b5ccb",
    },
    {
        "role": "receipt_store_validator_implementation",
        "path": CONTEXT_RECEIPT_STORE_IMPLEMENTATION_PATH.as_posix(),
        "file_sha256": "923d9d612d6c174a785d00880788cf68c7f9176dae911626b4acd16e2f6bd1fa",
        "file_bytes": 21_818,
        "source_commit": "c2ea5ef44a37976b91ad1636c438160c8e11ad68",
    },
    {
        "role": "receipt_head_schema",
        "path": CONTEXT_RECEIPT_HEAD_SCHEMA_PATH.as_posix(),
        "file_sha256": "bc62d050f254d04802e65b5f88dbe831630b72d0a633e573acae34f01cf072c4",
        "file_bytes": 1_927,
        "source_commit": "c2ea5ef44a37976b91ad1636c438160c8e11ad68",
    },
    {
        "role": "reference_set_schema",
        "path": CONTEXT_REFERENCE_SET_SCHEMA_PATH.as_posix(),
        "file_sha256": "4b74e6784987b71a32cc612857d53fc73a2d07480ab48501d7ec3c1cd78f5998",
        "file_bytes": 828,
        "source_commit": "c2ea5ef44a37976b91ad1636c438160c8e11ad68",
    },
]

LIFECYCLE_CONTRACT_RECEIPTS = [
    {
        "role": "event_schema",
        "path": LIFECYCLE_EVENT_SCHEMA_PATH.as_posix(),
        "file_sha256": "047721a1a86d7ef920a2c9a5fd035ab95f2e407453b33842dbfc6ca54e433a8f",
        "file_bytes": 14_919,
        "source_commit": "087a472d4b5051b732b9810a25245707f38a7426",
    },
    {
        "role": "state_and_chain_validator_implementation",
        "path": LIFECYCLE_STATE_IMPLEMENTATION_PATH.as_posix(),
        "file_sha256": "a5710b6ba5aedcd605541794aa7343c6f10d9af834848a95b2f8eb46b024c281",
        "file_bytes": 86_565,
        "source_commit": "087a472d4b5051b732b9810a25245707f38a7426",
    },
]

NYSE_CLOCK_CONTRACT_RECEIPTS = [
    {
        "role": "rth_window_implementation",
        "path": NYSE_RTH_WINDOW_IMPLEMENTATION_PATH.as_posix(),
        "file_sha256": "25ae25d29f1a1e6ce7d38372bbfaaf03e18925072e41aaea8bc3c1c730a14191",
        "file_bytes": 95_668,
    },
    {
        "role": "session_calendar_implementation",
        "path": NYSE_SESSION_CALENDAR_IMPLEMENTATION_PATH.as_posix(),
        "file_sha256": "7c9167fd416babb64c3067ae7e6237615011ad79e26d826e57005486496410ce",
        "file_bytes": 29_814,
    },
]

CAMPAIGN_V2_POLICIES = {
    "grouping": "exact-contract-session-census/v2",
    "eligibility": "all-valid-options-signal-episodes/v2",
    "member_order": "available-at-then-episode-id/v1",
    "revision": "strict-source-prefix-extension/v1",
    "outcome_anchor": "final-member-availability/v1",
    "frozen_at": "2026-08-12T13:30:00Z",
}
CAMPAIGN_V2_RULE_SHA256 = hashlib.sha256(
    json.dumps(
        CAMPAIGN_V2_POLICIES,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()

FALSE_AUTHORITY = {
    "may_originate_signal": False,
    "may_score": False,
    "may_rank": False,
    "may_select": False,
    "may_issue": False,
    "may_size": False,
    "may_trade": False,
    "may_publish_pick": False,
    "may_train_prophet": False,
    "may_feed_neural_web": False,
    "may_compute_option_pnl": False,
    "may_claim_sparse_gate": False,
}

ABSTENTION_REASON_CODES = [
    "LEGACY_OR_RETROSPECTIVE_CAMPAIGN",
    "BEFORE_SELECTOR_EFFECTIVE_FREEZE",
    "BENCHMARK_DIGEST_MISSING_OR_MISMATCHED",
    "CAMPAIGN_PREFIX_RECEIPT_INVALID",
    "EXACT_OCC_CONTRACT_MISSING_OR_INVALID",
    "OPTIONS_EVIDENCE_MISSING_OR_MISMATCHED",
    "KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED",
    "KONSEKI_EXACT_ASOF_CONTEXT_ABSENT",
    "MARK_RECEIPT_MISSING_OR_MISMATCHED",
    "MARK_NOT_ADMITTED_OR_STALE",
    "LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED",
    "LIFECYCLE_NOT_DURABLE_OR_IDENTITY_DRIFT",
    "LIFECYCLE_ALREADY_TERMINAL",
    "ANY_UPSTREAM_AUTHORITY_TRUE",
    "DECISION_OUTSIDE_NYSE_RTH",
    "SESSION_PROPOSAL_CAP_REACHED",
]

SELECTOR_RULE: dict[str, Any] = {
    "rule_id": "sparse_exact_option_truth_gate/v1",
    "version_fence": {
        "registered_at": REGISTERED_AT,
        "effective_freeze_rule": SELECTOR_EFFECTIVE_FREEZE_RULE,
        "selector_effective_freeze_at": SELECTOR_EFFECTIVE_FREEZE_AT,
        "selector_effective_freeze_nyse_session": SELECTOR_EFFECTIVE_FREEZE_SESSION,
        "source_campaign_effective_freeze_at": CAMPAIGN_V2_POLICIES["frozen_at"],
        "origin_main_hosting_requirement": (
            "exact_rule_digest_must_be_on_origin_main_before_effective_freeze"
        ),
        "origin_main_requirement_failure_action": (
            "global_abstain_new_version_and_future_nyse_boundary_required"
        ),
        "pre_effective_source_policy": (
            "retrospective_global_abstain_permanently_ineligible"
        ),
        "benchmark_digest_sha256": BENCHMARK_DIGEST,
        "benchmark_effective_freeze_at": BENCHMARK_EFFECTIVE_FREEZE_AT,
        "prospective_phase": "prospective_after_benchmark_freeze",
        "legacy_campaign_v1_policy": "permanently_ineligible",
        "rule_change_policy": "new_version_and_new_forward_cohort",
    },
    "candidate_manifest": {
        "source_schema": "options.signal_campaign/v2",
        "source_phase": "prospective_after_rule_freeze",
        "source_rule_sha256": CAMPAIGN_V2_RULE_SHA256,
        "source_contract_registration": {
            "state": "merged_origin_main_dependency_bound",
            "dependency_pull_request": 5362,
            "dependency_merge_commit": CAMPAIGN_V2_SOURCE_COMMIT,
            "required_before_any_candidate": True,
            "exact_schema_full_file_receipt": CAMPAIGN_V2_CONTRACT_RECEIPTS[0],
            "exact_implementation_full_file_receipt": CAMPAIGN_V2_CONTRACT_RECEIPTS[1],
            "dependency_absence_or_failure_action": "abstain",
        },
        "source_clock": "first_selector_observed_available_at",
        "candidate_identity": "sha256(rule_id,benchmark_digest,campaign_id)",
        "required_digest_fields": [
            "benchmark_digest_sha256",
            "selector_rule_sha256",
            "candidate_manifest_rule_sha256",
            "decision_rule_sha256",
            "evidence_rule_sha256",
            "source_campaign_rule_sha256",
        ],
        "immutable_time_fence": {
            "campaign_formed_at_field": "formed_at",
            "final_member_available_at_field": "members[-1].available_at",
            "equality_required": True,
            "both_at_or_after_benchmark_effective_freeze": True,
            "both_at_or_after_selector_effective_freeze": True,
            "observation_clock_cannot_cure_pre_freeze_source": True,
        },
        "one_candidate_per_campaign_id": True,
        "first_observed_revision_frozen": True,
        "manifest_before_decisions": True,
        "late_arrival_policy": "next_manifest_cycle_before_decision",
        "duplicate_policy": "same_identity_same_bytes_idempotent_conflict_fails_closed",
        "order": ["candidate_available_at", "candidate_id"],
    },
    "decisions": {
        "actions": ["abstain", "propose"],
        "exactly_one_per_candidate": True,
        "decision_due": "next_selector_cycle",
        "minimum_proposals_per_nyse_session": 0,
        "maximum_proposals_per_nyse_session": 3,
        "quota_or_forced_fill": False,
        "ranking_or_scoring": False,
        "passing_order": ["candidate_available_at", "candidate_id"],
        "overflow_action": "abstain",
        "overflow_reason": "SESSION_PROPOSAL_CAP_REACHED",
        "proposal_semantics": "private_research_review_only_not_issued_plan",
        "nyse_session_clock": {
            "timezone": "America/New_York",
            "calendar_basis": "nyse_session_window_recurring_schedule/v1",
            "calendar_implementation": (
                "engine.session_digest.session_window_et+lib.nyse_calendar.is_session"
            ),
            "contract_receipts": NYSE_CLOCK_CONTRACT_RECEIPTS,
            "decision_event_clock_field": "decision_event_at",
            "decision_available_clock_field": "decision_available_at",
            "causal_order": "decision_event_at_lte_decision_available_at",
            "proposal_window": "nyse_rth_only",
            "session_bucket_field": "decision_nyse_session_date",
            "session_bucket_rule": (
                "unique_session_containing_both_event_and_available_clocks"
            ),
            "boundary": "lower_inclusive_upper_exclusive",
            "early_close_policy": "recurring_13_et_close_from_session_window_et",
            "unresolved_or_non_session_action": "abstain",
            "outside_rth_action": "abstain",
            "outside_rth_reason": "DECISION_OUTSIDE_NYSE_RTH",
            "cap_count_basis": "propose_actions_with_same_decision_nyse_session_date",
            "cap_evaluation_order": ["candidate_available_at", "candidate_id"],
            "fourth_and_later_passing_action": "abstain",
        },
    },
    "exact_contract": {
        "campaign_required_fields": [
            "ticker",
            "right",
            "expiration",
            "strike",
            "strike_key",
        ],
        "mark_and_lifecycle_required_fields": [
            "root",
            "right",
            "expiry",
            "strike",
            "strike_millis",
            "occ_symbol",
        ],
        "identity_policy": (
            "shared_fields_exact_and_occ_exact_between_mark_and_lifecycle"
        ),
        "fuzzy_or_derived_substitution": False,
    },
    "required_truth_receipts": {
        "options": {
            "schema": "options.signal_campaign/v2",
            "require_exact_source_prefix": True,
            "missing_action": "abstain",
        },
        "konseki": {
            "head_schema": "options.market_memory_context_receipt_head/v1",
            "reference_set_schema": "options.market_memory_context_reference_set/v1",
            "reference_schema": "options.market_memory_context_reference/v1",
            "reference_owner_schema": "options.signal_episode/v1",
            "owner_binding": "campaign_v2_final_member_episode/v1",
            "publication_binding": (
                "authenticated_current_private_head_contains_exact_reference/v1"
            ),
            "contract_receipts": CONTEXT_REFERENCE_CONTRACT_RECEIPTS,
            "campaign_to_owner_requirements": [
                "source_episode_prefix_exact_bytes",
                "final_member_source_row_exact",
                "final_member_source_row_sha256_exact",
                "final_member_episode_id_exact",
                "final_member_available_at_equals_episode_available_at_and_campaign_formed_at",
                "campaign_group_equals_episode_exact_contract",
                "reference_owner_record_sha256_equals_final_member_source_row_sha256",
                "reference_owner_event_time_equals_episode_event_time",
                "reference_owner_requested_as_of_equals_episode_available_at",
            ],
            "subject_identity": {
                "symbol": "SPY",
                "subject_id": (
                    "mmsecurity_5fc37e8db34f74314b654c910ea8bacfa7de8b5d2d067f2e5421c9d5745ceb4c"
                ),
                "instrument_id": (
                    "mmsecurity_6f361f5bad9f06a3b2ff157585d5728f55f77198420959aadd8922d1045c3fea"
                ),
                "identity_config_sha256": (
                    "5e7823e48866b2c0828122b65f684ed5872c6816a6224f61e44db4c03d129b33"
                ),
            },
            "query_identity": [
                "subject_id",
                "instrument_id",
                "event_time",
                "available_at",
                "mode=operational_pit",
            ],
            "exact_absence_reason": "exact_requested_as_of_context_absent",
            "missing_or_absent_action": "abstain",
        },
        "mark": {
            "schema": "prophet.option_mark_observation/v1",
            "require_pointer_fields": ["observation_id", "key", "sha256", "bytes"],
            "require_exact_plan_identity": [
                "id",
                "asset",
                "plan_asof",
                "recorded_at",
                "entry_date",
            ],
            "nbbo_or_execution_authority": False,
            "missing_or_unavailable_action": "abstain",
        },
        "lifecycle": {
            "event_schema": "prophet.option_shadow_lifecycle_event/v1",
            "state_schema": "prophet.option_shadow_lifecycle_state/v1",
            "contract_receipts": LIFECYCLE_CONTRACT_RECEIPTS,
            "state_required_fields": [
                "schema",
                "state_id",
                "activation",
                "lifecycle_head",
                "ledger_cursor",
                "mark_cursor",
                "enrollments",
                "terminals",
                "latest_marks",
            ],
            "state_content_identity": (
                "posls_+sha256(json_utf8_sort_keys_compact_no_ascii_escape(state_without_state_id))"
            ),
            "event_pointer_fields": ["schema", "event_id", "key", "sha256", "bytes"],
            "mark_pointer_fields": [
                "schema",
                "observation_id",
                "key",
                "sha256",
                "bytes",
            ],
            "ledger_cursor_fields": [
                "schema",
                "source_repository",
                "source_ref",
                "source_commit",
                "source_path",
                "bytes",
                "sha256",
                "row_count",
            ],
            "state_mapping": {
                "lifecycle_head": "validated_event_chain_head",
                "activation": "validated_event_chain_root_activation_pointer",
                "ledger_cursor": "exact_canonical_main_ledger_prefix_receipt",
                "mark_cursor": "exact_private_mark_chain_head_pointer",
            },
            "candidate_mapping": {
                "plan_id_source": "enrollment_event.payload.plan.id",
                "open_enrollment_pointer": "state.enrollments[plan_id]",
                "terminal_pointer": "state.terminals[plan_id]",
                "latest_mark_state": "state.latest_marks[plan_id]",
                "require_open_enrollment": True,
                "terminal_action": "abstain",
                "terminal_reason": "LIFECYCLE_ALREADY_TERMINAL",
                "contract_source": "enrollment_event.payload.contract",
                "plan_identity_source": "enrollment_event.payload.plan",
                "require_contract_drift_false": True,
                "require_plan_identity_drift_false": True,
            },
            "chain_requirements": [
                "lifecycle_head_reaches_activation_without_cycle",
                "activation_event_payload_matches_mark_and_ledger_boundaries",
                "enrollment_pointer_loads_content_addressed_enrollment_event",
                "enrollment_mark_observation_is_ancestor_of_mark_cursor",
                "ledger_cursor_validates_exact_append_only_canonical_prefix",
            ],
            "missing_drift_or_unavailable_action": "abstain",
        },
    },
    "abstention_reason_codes": ABSTENTION_REASON_CODES,
    "authority": FALSE_AUTHORITY,
}


class RegistrationError(ValueError):
    """A preregistration input or receipt violates the frozen contract."""


def _fail(message: str) -> NoReturn:
    raise RegistrationError(message)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key {key!r}")
        value[key] = item
    return value


def strict_loads(raw: str | bytes) -> Any:
    return json.loads(
        raw,
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant {token}")
        ),
    )


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise RegistrationError("value is not finite canonical JSON") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate_file_receipts(
    root: Path,
    receipts: list[dict[str, Any]],
    *,
    label: str,
) -> None:
    for receipt in receipts:
        path_value = receipt.get("path")
        expected_bytes = receipt.get("file_bytes")
        expected_sha256 = receipt.get("file_sha256")
        if (
            not isinstance(path_value, str)
            or not isinstance(expected_bytes, int)
            or isinstance(expected_bytes, bool)
            or expected_bytes < 1
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
        ):
            _fail(f"{label} file receipt is malformed")
        path = root / path_value
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise RegistrationError(f"cannot load {label} file receipt: {path}") from exc
        if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
            _fail(f"{label} full-file receipt drift: {path_value}")


def _content_id(prefix: str, value: dict[str, Any], field: str) -> str:
    core = copy.deepcopy(value)
    core[field] = ""
    return prefix + _sha256(canonical_bytes(core))


def _load_document(path: Path, label: str) -> dict[str, Any]:
    try:
        value = strict_loads(path.read_bytes())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RegistrationError(f"cannot load {label}: {path}") from exc
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object")
    return value


def _validator(path: Path, label: str) -> Draft202012Validator:
    schema = _load_document(path, f"{label} schema")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate(value: dict[str, Any], validator: Draft202012Validator, label: str) -> None:
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        where = ".".join(str(part) for part in error.path) or "<root>"
        _fail(f"{label} schema validation failed at {where}: {error.message}")


def _canonical_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RegistrationError(f"{label} must be canonical UTC") from exc
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if canonical != value:
        _fail(f"{label} must be canonical UTC")
    return parsed


def _canonical_decimal(value: object, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        _fail(f"{label} must be a finite positive number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RegistrationError(f"{label} must be a finite positive number") from exc
    if not number.is_finite() or number <= 0:
        _fail(f"{label} must be a finite positive number")
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def validate_proposal_decision_clock(
    *,
    decision_event_at: str,
    decision_available_at: str,
) -> str:
    """Return the exact NYSE session bucket for one otherwise-passing proposal.

    Both clocks must be causal and inside the same repo-frozen RTH window. An
    abstention may be recorded outside RTH, but it can never become a proposal.
    """

    event = _canonical_utc(decision_event_at, "decision event clock")
    available = _canonical_utc(decision_available_at, "decision available clock")
    if event > available:
        _fail("decision event clock is after its available clock")
    try:
        from engine.session_digest import ET, session_window_et
        from lib.nyse_calendar import is_session
    except ImportError as exc:
        raise RegistrationError("NYSE proposal clock implementation is unavailable") from exc
    event_date = event.astimezone(ET).date()
    available_date = available.astimezone(ET).date()
    if event_date != available_date or not is_session(event_date):
        _fail("proposal clocks do not share a resolved NYSE session")
    session_open, session_close = session_window_et(event_date)
    event_et = event.astimezone(ET)
    available_et = available.astimezone(ET)
    if not (
        session_open <= event_et < session_close
        and session_open <= available_et < session_close
    ):
        _fail("proposal clock is outside the frozen NYSE RTH window")
    return event_date.isoformat()


def validate_campaign_v2_time_fence(
    campaign: dict[str, Any],
    *,
    first_selector_observed_available_at: str,
    selector_effective_freeze_at: str,
) -> None:
    """Validate the frozen clocks for one future v2 candidate.

    A late selector observation cannot cure an old campaign. Both immutable
    source clocks must clear the benchmark and resolved selector freezes.
    """

    if not isinstance(campaign, dict) or campaign.get("schema") != "options.signal_campaign/v2":
        _fail("candidate campaign must use options.signal_campaign/v2")
    if campaign.get("policies") != CAMPAIGN_V2_POLICIES:
        _fail("candidate campaign rule differs from the frozen v2 policy")
    if campaign.get("evidence_phase") != "prospective_after_rule_freeze":
        _fail("candidate campaign is not prospectively phased")
    members = campaign.get("members")
    if not isinstance(members, list) or not members or not isinstance(members[-1], dict):
        _fail("candidate campaign requires an immutable final member")
    formed = _canonical_utc(campaign.get("formed_at"), "candidate formed_at")
    final_available = _canonical_utc(
        members[-1].get("available_at"), "candidate final-member available_at"
    )
    if formed != final_available:
        _fail("candidate formed_at must equal final-member available_at")
    benchmark_freeze = _canonical_utc(
        BENCHMARK_EFFECTIVE_FREEZE_AT, "benchmark effective freeze"
    )
    selector_freeze = _canonical_utc(
        selector_effective_freeze_at, "selector effective freeze"
    )
    frozen_selector_freeze = _canonical_utc(
        SELECTOR_EFFECTIVE_FREEZE_AT, "registered selector effective freeze"
    )
    source_campaign_freeze = _canonical_utc(
        CAMPAIGN_V2_POLICIES["frozen_at"], "source campaign effective freeze"
    )
    registered = _canonical_utc(REGISTERED_AT, "selector registered_at")
    if selector_freeze < registered:
        _fail("selector effective freeze cannot predate registration")
    if selector_freeze != frozen_selector_freeze:
        _fail("selector effective freeze differs from the frozen registration")
    effective = max(benchmark_freeze, selector_freeze, source_campaign_freeze)
    if formed < effective or final_available < effective:
        _fail("candidate source clocks predate the effective freeze")
    observed = _canonical_utc(
        first_selector_observed_available_at,
        "first selector observed available_at",
    )
    if observed < formed or observed < selector_freeze:
        _fail("selector observation clock is non-causal")


def _decode_canonical_jsonl(
    raw: bytes,
    *,
    label: str,
    validator: Draft202012Validator | None = None,
) -> list[tuple[dict[str, Any], bytes]]:
    if raw and not raw.endswith(b"\n"):
        _fail(f"{label} has a torn final line")
    rows: list[tuple[dict[str, Any], bytes]] = []
    for ordinal, line in enumerate(raw.splitlines(), start=1):
        if not line:
            _fail(f"{label} has a blank row at {ordinal}")
        try:
            value = strict_loads(line)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RegistrationError(f"{label} row {ordinal} is malformed") from exc
        if not isinstance(value, dict) or canonical_bytes(value) != line:
            _fail(f"{label} row {ordinal} is not canonical")
        if validator is not None:
            _validate(value, validator, f"{label} row {ordinal}")
        rows.append((value, line))
    return rows


def validate_campaign_v2_context_owner_binding(
    campaign: dict[str, Any],
    *,
    episode_prefix_raw: bytes,
    context_reference: dict[str, Any],
    repo_root: str | Path = ROOT,
) -> None:
    """Bind campaign v2 through its final v1 episode to an exact #5353 reference."""

    if not isinstance(campaign, dict) or campaign.get("schema") != "options.signal_campaign/v2":
        _fail("context binding requires options.signal_campaign/v2")
    if campaign.get("policies") != CAMPAIGN_V2_POLICIES:
        _fail("context binding campaign policy drift")
    root = Path(repo_root).resolve()
    episode_schema_path = (
        root / "contracts/options/options.signal_episode.v1.schema.json"
    )
    rows = _decode_canonical_jsonl(
        episode_prefix_raw,
        label="campaign episode prefix",
        validator=_validator(episode_schema_path, "episode"),
    )
    source = campaign.get("source_episode_prefix")
    if not isinstance(source, dict) or set(source) != {"path", "records", "prefix_sha256"}:
        _fail("campaign source episode prefix receipt is malformed")
    if source["path"] != "data/options_signal_episode/episodes.jsonl":
        _fail("campaign source episode prefix path drift")
    if source["records"] != len(rows) or source["prefix_sha256"] != _sha256(episode_prefix_raw):
        _fail("campaign source episode prefix receipt mismatch")
    episode_ledger_path = root / source["path"]
    try:
        episode_ledger_raw = episode_ledger_path.read_bytes()
    except OSError as exc:
        raise RegistrationError(
            f"cannot load campaign source episode ledger: {episode_ledger_path}"
        ) from exc
    ledger_lines = episode_ledger_raw.splitlines(keepends=True)
    expected_prefix = b"".join(ledger_lines[: len(rows)])
    if episode_prefix_raw != expected_prefix:
        _fail("campaign episode prefix is not the exact source-ledger prefix")
    members = campaign.get("members")
    if not isinstance(members, list) or not members or not isinstance(members[-1], dict):
        _fail("campaign final member is missing")
    final = members[-1]
    source_row = final.get("source_row")
    if not isinstance(source_row, int) or isinstance(source_row, bool) or not 1 <= source_row <= len(rows):
        _fail("campaign final-member source row is invalid")
    episode, episode_line = rows[source_row - 1]
    episode_sha256 = _sha256(episode_line)
    if (
        final.get("episode_id") != episode.get("episode_id")
        or final.get("available_at") != episode.get("available_at")
        or final.get("source_row_sha256") != episode_sha256
        or campaign.get("formed_at") != episode.get("available_at")
    ):
        _fail("campaign final member does not bind its exact episode row")
    group = campaign.get("group")
    contract = episode.get("contract")
    if not isinstance(group, dict) or not isinstance(contract, dict):
        _fail("campaign or episode exact contract is malformed")
    if (
        group.get("session_date") != episode.get("session_date")
        or group.get("ticker") != episode.get("ticker")
        or group.get("right") != contract.get("right")
        or group.get("expiration") != contract.get("expiration")
        or _canonical_decimal(group.get("strike"), "campaign strike")
        != _canonical_decimal(contract.get("strike"), "episode strike")
        or group.get("strike_key")
        != _canonical_decimal(contract.get("strike"), "episode strike")
    ):
        _fail("campaign group differs from its exact final-member contract")

    try:
        from engine.options_market_memory_context import (
            load_canary_identity_snapshot,
            validate_context_reference,
        )

        reference = validate_context_reference(context_reference)
        identity = load_canary_identity_snapshot(
            root / MARKET_MEMORY_CANARY_IDENTITY_PATH
        )
    except Exception as exc:
        raise RegistrationError("context reference fails its owner contract") from exc
    expected_owner = {
        "schema": "options.signal_episode/v1",
        "id": episode["episode_id"],
        "record_sha256": episode_sha256,
        "ticker": episode["ticker"],
        "event_time": episode["event_time"],
        "requested_as_of": episode["available_at"],
        "requested_as_of_basis": "durable_available_at",
        "evidence_phase": "decision_time_actual_output",
    }
    if reference.get("owner") != expected_owner:
        _fail("context reference owner differs from the campaign final member")
    query = reference.get("query")
    if not isinstance(query, dict) or (
        episode.get("ticker") != identity.symbol
        or query.get("subject") != identity.subject
        or query.get("identity_config_sha256") != identity.config_sha256
        or query.get("event_time") != episode["event_time"]
        or query.get("as_known_at") != episode["available_at"]
        or query.get("mode") != "operational_pit"
        or query.get("fallback_policy") != "exact_no_fallback"
    ):
        _fail("context reference query differs from the exact episode clocks")
    if reference.get("disposition") != "bound" or reference.get("context") is None:
        _fail("proposal requires a bound exact context reference")


def _load_legacy_campaigns(
    path: Path, validator: Draft202012Validator
) -> tuple[list[dict[str, Any]], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RegistrationError(f"cannot load legacy campaign ledger: {path}") from exc
    if raw and not raw.endswith(b"\n"):
        _fail("legacy campaign ledger has a torn final line")
    rows: list[dict[str, Any]] = []
    identities: set[str] = set()
    for ordinal, line in enumerate(raw.splitlines(), start=1):
        if not line:
            _fail(f"legacy campaign ledger has a blank row at {ordinal}")
        try:
            row = strict_loads(line)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RegistrationError(
                f"legacy campaign ledger row {ordinal} is malformed"
            ) from exc
        if not isinstance(row, dict) or canonical_bytes(row) != line:
            _fail(f"legacy campaign ledger row {ordinal} is not canonical")
        _validate(row, validator, f"legacy campaign row {ordinal}")
        campaign_id = row["campaign_id"]
        if campaign_id in identities:
            _fail(f"duplicate legacy campaign identity: {campaign_id}")
        identities.add(campaign_id)
        rows.append(row)
    return rows, raw


def _baseline_ledger(benchmark: dict[str, Any]) -> dict[str, Any]:
    ledgers = benchmark["benchmark"]["baselines"]["mastermindx"]["ledgers"]
    matches = [item for item in ledgers if item["path"] == LEGACY_CAMPAIGN_PATH.as_posix()]
    if len(matches) != 1:
        _fail("benchmark must carry exactly one legacy campaign baseline")
    return matches[0]


def build_receipt(repo_root: str | Path = ROOT) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    _validate_file_receipts(
        root,
        CAMPAIGN_V2_CONTRACT_RECEIPTS,
        label="campaign v2 schema/runtime contract",
    )
    _validate_file_receipts(
        root,
        CONTEXT_REFERENCE_CONTRACT_RECEIPTS,
        label="Market Memory context-reference contract",
    )
    _validate_file_receipts(
        root,
        LIFECYCLE_CONTRACT_RECEIPTS,
        label="option lifecycle contract",
    )
    _validate_file_receipts(
        root,
        NYSE_CLOCK_CONTRACT_RECEIPTS,
        label="NYSE proposal-clock contract",
    )
    benchmark_file = root / BENCHMARK_PATH
    try:
        benchmark_raw = benchmark_file.read_bytes()
    except OSError as exc:
        raise RegistrationError(
            f"cannot load completion benchmark: {benchmark_file}"
        ) from exc
    if (
        len(benchmark_raw) != BENCHMARK_FILE_BYTES
        or _sha256(benchmark_raw) != BENCHMARK_FILE_SHA256
    ):
        _fail("completion benchmark full-file receipt drift")
    benchmark = _load_document(benchmark_file, "completion benchmark")
    _validate(
        benchmark,
        _validator(root / BENCHMARK_SCHEMA_PATH, "completion benchmark"),
        "completion benchmark",
    )
    if benchmark.get("schema") != BENCHMARK_SCHEMA:
        _fail("completion benchmark schema drift")
    expected_benchmark_registration = {
        "registered_at": BENCHMARK_REGISTERED_AT,
        "repository": REPOSITORY,
        "baseline_commit": BENCHMARK_BASELINE_COMMIT,
        "effective_freeze_rule": (
            "later_of_registered_at_and_first_origin_main_commit_containing_exact_benchmark_digest"
        ),
        "canonicalization": "json_utf8_sort_keys_compact_no_ascii_escape/v1",
        "benchmark_digest_sha256": BENCHMARK_DIGEST,
    }
    if benchmark.get("registration") != expected_benchmark_registration:
        _fail("completion benchmark registration drift")
    benchmark_digest = _sha256(canonical_bytes(benchmark["benchmark"]))
    if benchmark_digest != BENCHMARK_DIGEST or (
        benchmark["registration"]["benchmark_digest_sha256"] != BENCHMARK_DIGEST
    ):
        _fail("completion benchmark digest drift")
    benchmark_registered_at = _canonical_utc(
        BENCHMARK_REGISTERED_AT, "benchmark registered_at"
    )
    benchmark_first_main_at = _canonical_utc(
        BENCHMARK_FIRST_MAIN_COMMITTED_AT, "benchmark first-main committed_at"
    )
    benchmark_effective_at = _canonical_utc(
        BENCHMARK_EFFECTIVE_FREEZE_AT, "benchmark effective freeze"
    )
    if benchmark_effective_at != max(benchmark_registered_at, benchmark_first_main_at):
        _fail("completion benchmark effective freeze is inconsistent")

    legacy_validator = _validator(root / LEGACY_CAMPAIGN_SCHEMA_PATH, "legacy campaign")
    rows, legacy_raw = _load_legacy_campaigns(
        root / LEGACY_CAMPAIGN_PATH, legacy_validator
    )
    baseline = _baseline_ledger(benchmark)
    if "schema" in baseline:
        _fail("unexpected schema field in benchmark ledger baseline")
    if baseline["row_count"] != len(rows) or baseline["sha256"] != _sha256(legacy_raw):
        _fail("legacy campaign ledger differs from the frozen benchmark baseline")
    if baseline["prospective_row_count"] != 0 or baseline["authority"] != "research_only":
        _fail("legacy campaign benchmark baseline authority drift")

    for ordinal, row in enumerate(rows, start=1):
        if row["schema"] != "options.signal_campaign/v1":
            _fail(f"legacy campaign row {ordinal} schema drift")
        if row["evidence_phase"] != "retrospective_discovery":
            _fail(f"legacy campaign row {ordinal} is not permanently retrospective")
        if _canonical_utc(row["formed_at"], f"legacy row {ordinal} formed_at") >= (
            benchmark_registered_at
        ):
            _fail(f"legacy campaign row {ordinal} is not before the benchmark freeze floor")
        if row["disposition"] != "abstain" or row["training_eligible"] is not False:
            _fail(f"legacy campaign row {ordinal} gained disposition or training authority")
        if any(value is not False for value in row["authority"].values()):
            _fail(f"legacy campaign row {ordinal} gained authority")

    rule = copy.deepcopy(SELECTOR_RULE)
    rule_sha256 = _sha256(canonical_bytes(rule))
    rule_components = {
        "candidate_manifest_rule_sha256": _sha256(
            canonical_bytes(rule["candidate_manifest"])
        ),
        "decision_rule_sha256": _sha256(canonical_bytes(rule["decisions"])),
        "evidence_rule_sha256": _sha256(
            canonical_bytes(
                {
                    "exact_contract": rule["exact_contract"],
                    "required_truth_receipts": rule["required_truth_receipts"],
                    "abstention_reason_codes": rule["abstention_reason_codes"],
                }
            )
        ),
        "source_campaign_rule_sha256": CAMPAIGN_V2_RULE_SHA256,
    }
    empty_ids_sha256 = _sha256(canonical_bytes([]))
    source = {
        "path": LEGACY_CAMPAIGN_PATH.as_posix(),
        "schema": "options.signal_campaign/v1",
        "records": len(rows),
        "sha256": _sha256(legacy_raw),
        "benchmark_baseline_match": True,
        "all_rows_canonical": True,
        "all_rows_retrospective": True,
        "all_rows_authority_false": True,
    }
    manifest: dict[str, Any] = {
        "manifest_id": "",
        "scope": "activation_snapshot_not_covered_session",
        "source": source,
        "candidate_count": 0,
        "candidate_ids_sha256": empty_ids_sha256,
        "prospective_source_count": 0,
        "excluded_legacy_source_count": len(rows),
        "exclusion_reason_counts": {
            "LEGACY_OR_RETROSPECTIVE_CAMPAIGN": len(rows),
            "BEFORE_SELECTOR_EFFECTIVE_FREEZE": len(rows),
            "BENCHMARK_DIGEST_MISSING_OR_MISMATCHED": len(rows),
        },
    }
    manifest["manifest_id"] = _content_id("ossm_", manifest, "manifest_id")

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "receipt_id": "",
        "registration": {
            "registered_at": REGISTERED_AT,
            "repository": REPOSITORY,
            "benchmark": {
                "path": BENCHMARK_PATH.as_posix(),
                "schema": BENCHMARK_SCHEMA,
                "file_sha256": BENCHMARK_FILE_SHA256,
                "file_bytes": BENCHMARK_FILE_BYTES,
                "canonicalization": expected_benchmark_registration["canonicalization"],
                "benchmark_digest_sha256": BENCHMARK_DIGEST,
                "registered_at": BENCHMARK_REGISTERED_AT,
                "baseline_commit": BENCHMARK_BASELINE_COMMIT,
                "effective_freeze_rule": expected_benchmark_registration[
                    "effective_freeze_rule"
                ],
                "first_origin_main_commit_containing_digest": (
                    BENCHMARK_FIRST_MAIN_COMMIT
                ),
                "first_origin_main_commit_committed_at": (
                    BENCHMARK_FIRST_MAIN_COMMITTED_AT
                ),
                "effective_freeze_at": BENCHMARK_EFFECTIVE_FREEZE_AT,
            },
            "selector_rule_sha256": rule_sha256,
            "selector_rule_component_sha256s": rule_components,
            "selector_effective_freeze": {
                "rule": rule["version_fence"]["effective_freeze_rule"],
                "state": "preregistered_future_nyse_boundary",
                "nyse_session_date": SELECTOR_EFFECTIVE_FREEZE_SESSION,
                "timezone": "America/New_York",
                "boundary": "session_open_lower_inclusive",
                "first_origin_main_commit_containing_rule_digest": None,
                "first_origin_main_commit_committed_at": None,
                "origin_main_hosting_requirement": rule["version_fence"][
                    "origin_main_hosting_requirement"
                ],
                "origin_main_requirement_failure_action": rule["version_fence"][
                    "origin_main_requirement_failure_action"
                ],
                "pre_effective_source_policy": rule["version_fence"][
                    "pre_effective_source_policy"
                ],
                "effective_freeze_at": SELECTOR_EFFECTIVE_FREEZE_AT,
            },
        },
        "selector_rule": rule,
        "activation_manifest": manifest,
        "reconciliation": {
            "candidate_count": 0,
            "decision_count": 0,
            "abstain_decision_count": 0,
            "propose_decision_count": 0,
            "candidate_ids_sha256": empty_ids_sha256,
            "decision_candidate_ids_sha256": empty_ids_sha256,
            "exactly_one_reconciled": True,
            "coverage_ratio": 1.0,
            "empty_set_policy": "vacuous_one_to_one_not_sparse_gate_evidence",
            "silent_drop_count": 0,
            "minimum_proposals_per_nyse_session": 0,
            "maximum_proposals_per_nyse_session": 3,
        },
        "activation_disposition": {
            "action": "abstain",
            "reason_codes": ["NO_PROSPECTIVE_CANDIDATES"],
            "selector_active": False,
            "future_rows_policy": "new_governed_implementation_required",
        },
        "claim_boundary": {
            "prospective_selector_evidence": False,
            "covered_session_evidence": False,
            "satisfies_sparse_gate": False,
            "proposal_or_issue_authority": False,
            "public_output": False,
            "prophet_promotion": False,
            "neural_web_promotion": False,
            "training_eligible": False,
            "trade_or_return_claim": False,
        },
        "authority": copy.deepcopy(FALSE_AUTHORITY),
    }
    receipt["receipt_id"] = _content_id("ossr_", receipt, "receipt_id")
    _validate(
        receipt,
        _validator(root / RECEIPT_SCHEMA_PATH, "activation receipt"),
        "activation receipt",
    )
    return receipt


def receipt_bytes(repo_root: str | Path = ROOT) -> bytes:
    return canonical_bytes(build_receipt(repo_root)) + b"\n"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the tracked receipt is byte-identical to a fresh build",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        built = receipt_bytes(args.repo_root)
        if args.check:
            tracked_path = args.repo_root.resolve() / RECEIPT_PATH
            try:
                tracked = tracked_path.read_bytes()
            except OSError as exc:
                raise RegistrationError(
                    f"cannot read tracked preregistration receipt: {tracked_path}"
                ) from exc
            if tracked != built:
                _fail("tracked preregistration receipt differs from the frozen build")
            print(f"OK {RECEIPT_PATH.as_posix()} {_sha256(tracked)}")
        else:
            sys.stdout.buffer.write(built)
    except RegistrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
