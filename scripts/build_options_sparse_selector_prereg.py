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
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = Path("research/momoedge/completion_benchmark_prereg_v1.json")
BENCHMARK_SCHEMA_PATH = Path(
    "contracts/research/momoedge_oracle_completion_benchmark_prereg.v1.schema.json"
)
LEGACY_CAMPAIGN_PATH = Path("data/options_signal_episode/campaigns.jsonl")
LEGACY_CAMPAIGN_SCHEMA_PATH = Path(
    "contracts/options/options.signal_campaign.v1.schema.json"
)
RECEIPT_PATH = Path(
    "research/options_estate/sparse_selector_preregistration_receipt_v1.json"
)
RECEIPT_SCHEMA_PATH = Path(
    "contracts/options/options.sparse_selector_activation_receipt.v1.schema.json"
)

SCHEMA = "options.sparse_selector_activation_receipt/v1"
BENCHMARK_SCHEMA = "momoedge.completion_benchmark_prereg/v1"
BENCHMARK_DIGEST = "20e6c19f691cf9a07381288d6bdb33c6d74c8957b074ceefcdaf0ab8da1b1f42"
REGISTERED_AT = "2026-08-11T18:51:16Z"
REPOSITORY = "mastermindx-market-intelligence/macro"

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
    "ANY_UPSTREAM_AUTHORITY_TRUE",
    "SESSION_PROPOSAL_CAP_REACHED",
]

SELECTOR_RULE: dict[str, Any] = {
    "rule_id": "sparse_exact_option_truth_gate/v1",
    "version_fence": {
        "registered_at": REGISTERED_AT,
        "effective_freeze_rule": (
            "later_of_registered_at_and_first_origin_main_commit_containing_exact_rule_digest"
        ),
        "benchmark_digest_sha256": BENCHMARK_DIGEST,
        "prospective_phase": "prospective_after_benchmark_freeze",
        "legacy_campaign_v1_policy": "permanently_ineligible",
        "rule_change_policy": "new_version_and_new_forward_cohort",
    },
    "candidate_manifest": {
        "source_schema": "options.signal_campaign/v2",
        "source_phase": "prospective_after_rule_freeze",
        "source_clock": "first_selector_observed_available_at",
        "candidate_identity": "sha256(rule_id,benchmark_digest,campaign_id)",
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
            "require_event_pointer_fields": ["event_id", "key", "sha256", "bytes"],
            "require_chain_fields": [
                "lifecycle_head",
                "activation_boundary",
                "canonical_ledger_receipt",
                "mark_chain_pointer",
            ],
            "require_prior_durable_enrollment_or_terminal": True,
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
    benchmark = _load_document(root / BENCHMARK_PATH, "completion benchmark")
    _validate(
        benchmark,
        _validator(root / BENCHMARK_SCHEMA_PATH, "completion benchmark"),
        "completion benchmark",
    )
    if benchmark.get("schema") != BENCHMARK_SCHEMA:
        _fail("completion benchmark schema drift")
    benchmark_digest = _sha256(canonical_bytes(benchmark["benchmark"]))
    if benchmark_digest != BENCHMARK_DIGEST or (
        benchmark["registration"]["benchmark_digest_sha256"] != BENCHMARK_DIGEST
    ):
        _fail("completion benchmark digest drift")

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

    benchmark_registered_at = _canonical_utc(
        benchmark["registration"]["registered_at"], "benchmark registered_at"
    )
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
            "benchmark_path": BENCHMARK_PATH.as_posix(),
            "benchmark_schema": BENCHMARK_SCHEMA,
            "benchmark_digest_sha256": BENCHMARK_DIGEST,
            "selector_rule_sha256": rule_sha256,
            "selector_effective_freeze_rule": rule["version_fence"][
                "effective_freeze_rule"
            ],
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
