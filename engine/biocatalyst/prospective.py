"""Prospective ClinicalTrials.gov observation and change contracts.

This lane intentionally knows only what successive successful official-API
polls prove.  The first complete poll in a coverage epoch establishes a
baseline and emits no change.  Later changes are bounded by the two retrieval
times; source submission/history dates are never used as event time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
import re
from typing import Any, Mapping, Sequence

from engine.sector_intelligence import (
    canonical_json_bytes,
    canonical_json_sha256,
    exact_json_diff,
    validate_contract,
    validate_trial_diff_against_snapshots,
    validate_trial_observation_against_source_evidence,
)
from engine.sector_intelligence.contracts import ContractError


class ProspectiveError(ValueError):
    """Bounded failure while building the prospective source-fact plane."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SourceEvidence:
    """One independently replayed official-API source bundle."""

    run: Mapping[str, Any]
    snapshot: Mapping[str, Any]
    receipts: Sequence[Mapping[str, Any]]
    raw_page_bodies_by_receipt: Mapping[str, bytes]


_NCT_RE = re.compile(r"^NCT[0-9]{8}$")
_PUBLIC_CHANGE_FAMILIES = frozenset(
    {
        "registry_status",
        "enrollment_target",
        "enrollment_actual",
        "enrollment_count",
        "enrollment_type",
        "primary_completion_date",
        "completion_date",
        "site_set",
        "endpoint_record",
    }
)
_AUTHORITY = {
    "classification": "source_fact",
    "decision_authority": False,
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
        "raise_authority",
    ],
}
_INTERPRETATION = "registry_record_changed"
_PRODUCT_LANGUAGE = (
    "ClinicalTrials.gov's registry record changed; first observed within this interval."
)
_MAX_PUBLIC_EVENTS = 2048
_MAX_DISPLAY_CHANGES = 128
_MAX_VALUE_DEPTH = 6
_MAX_VALUE_ITEMS = 32
_MAX_VALUE_STRING = 2000
_MAX_VALUE_BYTES = 16_384


def _copy_json(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value))
    except ContractError as exc:
        raise ProspectiveError("PROSPECTIVE_VALUE_INVALID") from exc


def _with_hash(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    document = _copy_json(payload)
    if not isinstance(document, dict):
        raise ProspectiveError("PROSPECTIVE_VALUE_INVALID")
    document[field] = canonical_json_sha256(document)
    return document


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ProspectiveError("PROSPECTIVE_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProspectiveError("PROSPECTIVE_TIME_INVALID") from exc
    if parsed.tzinfo is None:
        raise ProspectiveError("PROSPECTIVE_TIME_INVALID")
    return parsed


def build_observation(
    current: SourceEvidence,
    *,
    prior: tuple[SourceEvidence, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Build one exact observation from a successful official-API snapshot."""

    snapshot = current.snapshot
    nct_id = snapshot.get("nct_id")
    if not isinstance(nct_id, str) or _NCT_RE.fullmatch(nct_id) is None:
        raise ProspectiveError("PROSPECTIVE_IDENTITY_INVALID")
    prior_snapshot = prior[0].snapshot if prior is not None else None
    prior_observation = prior[1] if prior is not None else None
    prior_ref = prior_snapshot.get("source_snapshot_id") if prior_snapshot else None
    prior_hash = prior_snapshot.get("canonical_content_sha256") if prior_snapshot else None
    current_hash = snapshot.get("canonical_content_sha256")
    changed = prior_hash is not None and prior_hash != current_hash
    same = prior_hash is not None and prior_hash == current_hash
    retrieved_at = snapshot.get("retrieved_at")
    after = prior_observation.get("retrieved_at") if prior_observation else None
    if after is not None and _parse_time(after) >= _parse_time(retrieved_at):
        raise ProspectiveError("PROSPECTIVE_INTERVAL_INVALID")
    seed = canonical_json_sha256(
        {
            "nct_id": nct_id,
            "source_snapshot_ref": snapshot.get("source_snapshot_id"),
            "prior_source_snapshot_ref": prior_ref,
            "retrieved_at": retrieved_at,
        }
    )
    observation = {
        "contract_id": "trial_snapshot_observation.v1",
        "schema_version": "1.0.0",
        "observation_id": f"ctgov_observation_{nct_id}_{seed[:24]}",
        "nct_id": nct_id,
        "run_ref": current.run.get("run_id"),
        "page_receipt_ref": snapshot.get("page_receipt_ref"),
        "source_snapshot_ref": snapshot.get("source_snapshot_id"),
        "canonical_content_sha256": current_hash,
        "prior_source_snapshot_ref": prior_ref,
        "prior_canonical_content_sha256": prior_hash,
        "source_state_changed": changed,
        "same_content_as_prior": same,
        "observed_interval": {"after": after, "at_or_before": retrieved_at},
        "source_last_update_posted_at": snapshot.get("source_last_update_posted_at"),
        "source_dataset_timestamp_raw": snapshot.get("source_dataset_timestamp_raw"),
        "retrieved_at": retrieved_at,
        "first_seen_at": snapshot.get("first_seen_at"),
        "coverage_class": "current_only",
        "transaction_from": snapshot.get("transaction_from"),
        "transaction_to": None,
    }
    try:
        validate_trial_observation_against_source_evidence(
            observation,
            snapshot,
            current.run,
            current.receipts,
            raw_page_bodies_by_receipt=current.raw_page_bodies_by_receipt,
        )
    except Exception as exc:
        raise ProspectiveError("PROSPECTIVE_OBSERVATION_INVALID") from exc
    return observation


def build_exact_diff(
    before: SourceEvidence,
    after: SourceEvidence,
    *,
    before_observation: Mapping[str, Any],
    after_observation: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Build the private immutable exact diff, or ``None`` for unchanged state."""

    before_snapshot = before.snapshot
    after_snapshot = after.snapshot
    if before_snapshot.get("nct_id") != after_snapshot.get("nct_id"):
        raise ProspectiveError("PROSPECTIVE_IDENTITY_INVALID")
    operations = exact_json_diff(
        before_snapshot.get("canonical_study"), after_snapshot.get("canonical_study")
    )
    if not operations:
        if after_observation.get("source_state_changed") is not False:
            raise ProspectiveError("PROSPECTIVE_DIFF_STATE_INVALID")
        return None
    if after_observation.get("source_state_changed") is not True:
        raise ProspectiveError("PROSPECTIVE_DIFF_STATE_INVALID")
    seed = canonical_json_sha256(
        {
            "before_source_snapshot_ref": before_snapshot.get("source_snapshot_id"),
            "after_source_snapshot_ref": after_snapshot.get("source_snapshot_id"),
            "before_observation_ref": before_observation.get("observation_id"),
            "after_observation_ref": after_observation.get("observation_id"),
        }
    )
    payload = {
        "contract_id": "trial_version_diff.v1",
        "schema_version": "1.0.0",
        "diff_id": f"trial_diff_{before_snapshot.get('nct_id')}_{seed[:24]}",
        "nct_id": before_snapshot.get("nct_id"),
        "before_source_snapshot_ref": before_snapshot.get("source_snapshot_id"),
        "after_source_snapshot_ref": after_snapshot.get("source_snapshot_id"),
        "before_observation_ref": before_observation.get("observation_id"),
        "after_observation_ref": after_observation.get("observation_id"),
        "before_content_sha256": before_snapshot.get("canonical_content_sha256"),
        "after_content_sha256": after_snapshot.get("canonical_content_sha256"),
        "source_record_refs": sorted(
            {
                before_snapshot.get("source_record_ref"),
                after_snapshot.get("source_record_ref"),
            }
        ),
        "evidence_claim_refs": [],
        "operations": operations,
        "observed_interval": _copy_json(after_observation.get("observed_interval")),
        "source_last_update_posted_at": after_snapshot.get("source_last_update_posted_at"),
        "source_published_at": after_snapshot.get("source_published_at"),
        "source_effective_at": after_snapshot.get("source_effective_at"),
        "valid_from": after_snapshot.get("valid_from"),
        "valid_to": after_snapshot.get("valid_to"),
        "coverage_class": "current_only",
        "parser_version": "clinicaltrials_v2_parser.v1",
        "semantic_alignment": {
            "status": "exact_source_json_path_only",
            "endpoint_semantics_assessed": False,
            "protocol_semantics_assessed": False,
        },
        "confidence": {
            "value": 1.0,
            "method": "deterministic_json_diff",
            "meaning": "diff_fidelity_not_real_world_materiality",
            "calibrated": False,
        },
        "contradiction_state": "none_known",
        "interpretation": _INTERPRETATION,
        "allowed_product_language": _PRODUCT_LANGUAGE,
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "authority": {
            "decision_authority": False,
            "allowed_uses": ["display", "context", "explain"],
            "forbidden_uses": list(_AUTHORITY["forbidden_uses"]),
        },
        "transaction_from": after_observation.get("transaction_from"),
        "transaction_to": None,
        "hash_scope": "canonical_payload_excluding_diff_payload_sha256",
    }
    diff = _with_hash(payload, "diff_payload_sha256")
    try:
        validate_trial_diff_against_snapshots(
            diff,
            before_snapshot,
            after_snapshot,
            before_observation,
            after_observation,
            before_run=before.run,
            before_receipts=before.receipts,
            before_raw_page_bodies_by_receipt=before.raw_page_bodies_by_receipt,
            after_run=after.run,
            after_receipts=after.receipts,
            after_raw_page_bodies_by_receipt=after.raw_page_bodies_by_receipt,
        )
    except Exception as exc:
        raise ProspectiveError("PROSPECTIVE_DIFF_INVALID") from exc
    return diff


def build_coverage_epoch(
    *,
    nct_ids: Sequence[str],
    current_run_ref: str,
    last_observed_at: str,
    transaction_from: str,
    prior_epoch: Mapping[str, Any] | None,
    coverage_started_at: str | None = None,
    poll_target_seconds: int = 7200,
) -> dict[str, Any]:
    """Create or advance one scope-bound prospective coverage epoch."""

    scope = sorted(set(nct_ids))
    if not scope or len(scope) != len(nct_ids) or any(_NCT_RE.fullmatch(item) is None for item in scope):
        raise ProspectiveError("PROSPECTIVE_SCOPE_INVALID")
    _parse_time(last_observed_at)
    _parse_time(transaction_from)
    expected_scope = {"kind": "explicit_nct_allowlist", "nct_ids": scope}
    if prior_epoch is None:
        coverage_started_at = coverage_started_at or last_observed_at
        if _parse_time(coverage_started_at) > _parse_time(last_observed_at):
            raise ProspectiveError("PROSPECTIVE_INTERVAL_INVALID")
        seed = canonical_json_sha256(
            {"scope": expected_scope, "coverage_started_at": coverage_started_at}
        )
        epoch_id = f"ctgov_coverage_{seed[:24]}"
        first_complete_run_ref = current_run_ref
    else:
        try:
            validate_contract("trial_coverage_epoch.v1", prior_epoch)
        except Exception as exc:
            raise ProspectiveError("PROSPECTIVE_EPOCH_INVALID") from exc
        if prior_epoch.get("scope") != expected_scope:
            raise ProspectiveError("PROSPECTIVE_SCOPE_INVALID")
        if _parse_time(last_observed_at) <= _parse_time(prior_epoch.get("last_observed_at")):
            raise ProspectiveError("PROSPECTIVE_INTERVAL_INVALID")
        epoch_id = prior_epoch.get("coverage_epoch_id")
        coverage_started_at = prior_epoch.get("coverage_started_at")
        first_complete_run_ref = prior_epoch.get("first_complete_run_ref")
    epoch = {
        "contract_id": "trial_coverage_epoch.v1",
        "schema_version": "1.0.0",
        "coverage_epoch_id": epoch_id,
        "source_id": "clinicaltrials_gov_v2",
        "scope": expected_scope,
        "coverage_class": "current_only",
        "coverage_method": "prospective_api_polling",
        "coverage_started_at": coverage_started_at,
        "coverage_ended_at": None,
        "first_complete_run_ref": first_complete_run_ref,
        "last_complete_run_ref": current_run_ref,
        "last_observed_at": last_observed_at,
        "historical_source_versions_ingested": False,
        "poll_target_seconds": poll_target_seconds,
        "upstream_refresh_schedule": "weekdays_generally_by_1400_utc",
        "limitations": [
            "no_complete_history_before_coverage_started_at",
            "last_update_posted_is_not_event_time",
            "missing_from_incremental_query_is_not_deletion",
            "registry_diff_is_not_protocol_change",
        ],
        "transaction_from": transaction_from,
        "transaction_to": None,
    }
    try:
        validate_contract("trial_coverage_epoch.v1", epoch)
    except Exception as exc:
        raise ProspectiveError("PROSPECTIVE_EPOCH_INVALID") from exc
    return epoch


def _safe_public_value(value: Any, *, depth: int = 0) -> bool:
    if depth > _MAX_VALUE_DEPTH:
        return False
    if value is None or isinstance(value, (str, bool, int)):
        return not isinstance(value, str) or len(value) <= _MAX_VALUE_STRING
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return len(value) <= _MAX_VALUE_ITEMS and all(
            _safe_public_value(item, depth=depth + 1) for item in value
        )
    if isinstance(value, dict):
        return (
            len(value) <= _MAX_VALUE_ITEMS
            and all(
                isinstance(key, str)
                and len(key) <= 128
                and _public_value_key_allowed(key)
                and _safe_public_value(item, depth=depth + 1)
                for key, item in value.items()
            )
        )
    return False


def _public_value_key_allowed(key: str) -> bool:
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", key)
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
    compact = normalized.replace("_", "")
    if (
        normalized in {
            "canonical_study",
            "hash",
            "raw",
            "ref",
            "refs",
            "sha256",
            "transaction",
            "object_key",
            "json_path",
            "hash_scope",
            "provenance",
        }
        or normalized.endswith("_ref")
        or normalized.endswith("_refs")
        or normalized.endswith("_sha256")
        or normalized.endswith("_hash")
        or normalized.startswith("raw_")
        or normalized.startswith("receipt")
        or normalized.startswith("transaction_")
        or compact.endswith("hash")
    ):
        return False
    return True


def _site_summary(value: Any, *, state: object) -> dict[str, Any] | None | object:
    if state == "missing":
        return None if value is None else _UNSAFE
    if not isinstance(value, list) or len(value) > 100_000:
        return _UNSAFE
    countries: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            return _UNSAFE
        country = item.get("country")
        if country is not None:
            if not isinstance(country, str) or not country or len(country) > 128:
                return _UNSAFE
            countries.add(country)
    rendered = sorted(countries)
    return {
        "site_count": len(value),
        "country_count": len(rendered),
        "countries": rendered[:_MAX_VALUE_ITEMS],
        "countries_truncated": len(rendered) > _MAX_VALUE_ITEMS,
    }


_UNSAFE = object()


def _display_operation(operation: Mapping[str, Any]) -> dict[str, Any] | None:
    family = operation.get("change_family")
    before_value = operation.get("before_value")
    after_value = operation.get("after_value")
    if family not in _PUBLIC_CHANGE_FAMILIES:
        return None
    if family == "site_set":
        before_value = _site_summary(
            before_value, state=operation.get("before_state")
        )
        after_value = _site_summary(
            after_value, state=operation.get("after_state")
        )
        if before_value is _UNSAFE or after_value is _UNSAFE:
            return None
    if not _safe_public_value(before_value) or not _safe_public_value(after_value):
        return None
    try:
        if (
            len(canonical_json_bytes(before_value)) > _MAX_VALUE_BYTES
            or len(canonical_json_bytes(after_value)) > _MAX_VALUE_BYTES
        ):
            return None
    except ContractError:
        return None
    return {
        "kind": family,
        "op": operation.get("op"),
        "before_state": operation.get("before_state"),
        "before_value": _copy_json(before_value),
        "after_state": operation.get("after_state"),
        "after_value": _copy_json(after_value),
    }


def build_public_event(diff: Mapping[str, Any]) -> dict[str, Any]:
    """Project one private exact diff without exposing private identifiers."""

    operations = diff.get("operations")
    interval = diff.get("observed_interval")
    nct_id = diff.get("nct_id")
    if not isinstance(operations, list) or not isinstance(interval, Mapping):
        raise ProspectiveError("PROSPECTIVE_DIFF_INVALID")
    display: list[dict[str, Any]] = []
    for operation in operations:
        rendered = _display_operation(operation) if isinstance(operation, Mapping) else None
        if rendered is not None and len(display) < _MAX_DISPLAY_CHANGES:
            display.append(rendered)
    public_seed = {
        "nct_id": nct_id,
        "observed_interval": interval,
        "total_exact_operation_count": len(operations),
        "changes": display,
    }
    change_id = f"prospective_change_{nct_id}_{canonical_json_sha256(public_seed)[:24]}"
    event = {
        "change_id": change_id,
        "first_observed_at": interval.get("at_or_before"),
        "observed_interval": _copy_json(interval),
        "total_exact_operation_count": len(operations),
        "display_change_count": len(display),
        "omitted_operation_count": len(operations) - len(display),
        "changes": display,
        "evidence": {
            "source_name": "ClinicalTrials.gov",
            "source_uri": f"https://clinicaltrials.gov/study/{nct_id}",
            "retrieved_at": interval.get("at_or_before"),
        },
        "interpretation": _INTERPRETATION,
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "authority": _copy_json(_AUTHORITY),
    }
    return event


def build_public_model(
    *,
    nct_id: str,
    epoch: Mapping[str, Any],
    observation: Mapping[str, Any],
    exact_diff: Mapping[str, Any] | None,
    generated_at: str,
    prior_model: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build the bounded cumulative read model for one coverage epoch."""

    if _NCT_RE.fullmatch(nct_id) is None or observation.get("nct_id") != nct_id:
        raise ProspectiveError("PROSPECTIVE_IDENTITY_INVALID")
    _parse_time(generated_at)
    if exact_diff is None and observation.get("source_state_changed") is True:
        raise ProspectiveError("PROSPECTIVE_DIFF_STATE_INVALID")
    if exact_diff is not None and observation.get("source_state_changed") is not True:
        raise ProspectiveError("PROSPECTIVE_DIFF_STATE_INVALID")
    if prior_model is None:
        events: list[dict[str, Any]] = []
        observation_count = 1
        accrual_state = "baseline_established"
        baseline_established_at = observation.get("retrieved_at")
        if exact_diff is not None or observation.get("prior_source_snapshot_ref") is not None:
            raise ProspectiveError("PROSPECTIVE_BASELINE_INVALID")
    else:
        validate_public_model(prior_model)
        if (
            prior_model.get("nct_id") != nct_id
            or prior_model.get("coverage_epoch_id") != epoch.get("coverage_epoch_id")
        ):
            raise ProspectiveError("PROSPECTIVE_MODEL_BINDING_INVALID")
        events = _copy_json(prior_model.get("events"))
        if not isinstance(events, list):
            raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
        observation_count = prior_model.get("observation_count", 0) + 1
        accrual_state = "accruing"
        baseline_established_at = prior_model.get("baseline_established_at")
        if exact_diff is not None:
            event = build_public_event(exact_diff)
            if any(item.get("change_id") == event["change_id"] for item in events):
                raise ProspectiveError("PROSPECTIVE_EVENT_COLLISION")
            events.append(event)
    if len(events) > _MAX_PUBLIC_EVENTS:
        raise ProspectiveError("PROSPECTIVE_MODEL_LIMIT_EXCEEDED")
    payload = {
        "contract_id": "trial_prospective_change_read_model.v1",
        "schema_version": "1.0.0",
        "nct_id": nct_id,
        "available": True,
        "unavailable_reason": None,
        "accrual_state": accrual_state,
        "coverage_class": "current_only",
        "coverage_method": "prospective_api_polling",
        "coverage_epoch_id": epoch.get("coverage_epoch_id"),
        "coverage_started_at": epoch.get("coverage_started_at"),
        "baseline_established_at": baseline_established_at,
        "last_observed_at": observation.get("retrieved_at"),
        "observation_count": observation_count,
        "events": events,
        "generated_at": generated_at,
        "interpretation": _INTERPRETATION,
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "authority": _copy_json(_AUTHORITY),
        "hash_scope": "canonical_payload_excluding_model_payload_sha256",
    }
    model = _with_hash(payload, "model_payload_sha256")
    validate_public_model(model)
    return model


def validate_public_model(model: Mapping[str, Any]) -> None:
    """Validate schema, hash, bounds, counts, time order, and public safety."""

    try:
        validate_contract("trial_prospective_change_read_model.v1", model)
    except Exception as exc:
        raise ProspectiveError("PROSPECTIVE_MODEL_INVALID") from exc
    without_hash = {key: value for key, value in model.items() if key != "model_payload_sha256"}
    if canonical_json_sha256(without_hash) != model.get("model_payload_sha256"):
        raise ProspectiveError("PROSPECTIVE_MODEL_HASH_MISMATCH")
    events = model.get("events")
    if not isinstance(events, list) or len(events) > _MAX_PUBLIC_EVENTS:
        raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
    observation_count = model.get("observation_count")
    accrual_state = model.get("accrual_state")
    if (
        not isinstance(observation_count, int)
        or isinstance(observation_count, bool)
        or observation_count < 1
        or (observation_count == 1 and (accrual_state != "baseline_established" or events))
        or (observation_count > 1 and accrual_state != "accruing")
        or len(events) > observation_count - 1
    ):
        raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
    coverage_started = _parse_time(model.get("coverage_started_at"))
    baseline_established = _parse_time(model.get("baseline_established_at"))
    last_observed = _parse_time(model.get("last_observed_at"))
    generated = _parse_time(model.get("generated_at"))
    if (
        coverage_started > baseline_established
        or baseline_established > last_observed
        or last_observed > generated
    ):
        raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
    seen: set[str] = set()
    previous_upper: datetime | None = None
    for event in events:
        if not isinstance(event, Mapping):
            raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
        change_id = event.get("change_id")
        changes = event.get("changes")
        total = event.get("total_exact_operation_count")
        if not isinstance(change_id, str) or change_id in seen or not isinstance(changes, list):
            raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
        seen.add(change_id)
        if (
            event.get("display_change_count") != len(changes)
            or event.get("omitted_operation_count") != total - len(changes)
            or len(changes) > _MAX_DISPLAY_CHANGES
        ):
            raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
        interval = event.get("observed_interval")
        if not isinstance(interval, Mapping):
            raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
        lower = _parse_time(interval.get("after"))
        upper = _parse_time(interval.get("at_or_before"))
        if lower >= upper or event.get("first_observed_at") != interval.get("at_or_before"):
            raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
        if previous_upper is not None and lower < previous_upper:
            raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
        if lower < coverage_started or upper > last_observed:
            raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
        previous_upper = upper
        evidence = event.get("evidence")
        if (
            not isinstance(evidence, Mapping)
            or evidence.get("retrieved_at") != interval.get("at_or_before")
            or evidence.get("source_uri")
            != f"https://clinicaltrials.gov/study/{model.get('nct_id')}"
        ):
            raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
        for change in changes:
            if (
                not isinstance(change, Mapping)
                or change.get("kind") not in _PUBLIC_CHANGE_FAMILIES
                or not _safe_public_value(change.get("before_value"))
                or not _safe_public_value(change.get("after_value"))
            ):
                raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
            expected_states = {
                "add": ("missing", "present"),
                "remove": ("present", "missing"),
                "replace": ("present", "present"),
            }.get(change.get("op"))
            if expected_states != (
                change.get("before_state"),
                change.get("after_state"),
            ):
                raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")
        public_seed = {
            "nct_id": model.get("nct_id"),
            "observed_interval": interval,
            "total_exact_operation_count": total,
            "changes": changes,
        }
        expected_id = (
            f"prospective_change_{model.get('nct_id')}_"
            f"{canonical_json_sha256(public_seed)[:24]}"
        )
        if change_id != expected_id:
            raise ProspectiveError("PROSPECTIVE_MODEL_INVALID")


def validate_publication_evidence(
    model: Mapping[str, Any],
    *,
    epoch: Mapping[str, Any],
    current: SourceEvidence,
    current_observation: Mapping[str, Any],
    exact_diff: Mapping[str, Any] | None,
    generated_at: str,
    prior: SourceEvidence | None,
    prior_observation: Mapping[str, Any] | None,
    prior_model: Mapping[str, Any] | None,
) -> None:
    """Rebuild a public model only from replayed private source evidence."""

    try:
        validate_contract("trial_coverage_epoch.v1", epoch)
        validate_trial_observation_against_source_evidence(
            current_observation,
            current.snapshot,
            current.run,
            current.receipts,
            raw_page_bodies_by_receipt=current.raw_page_bodies_by_receipt,
        )
        if prior is None:
            if prior_observation is not None or exact_diff is not None or prior_model is not None:
                raise ProspectiveError("PROSPECTIVE_BASELINE_INVALID")
        else:
            if prior_observation is None or prior_model is None:
                raise ProspectiveError("PROSPECTIVE_PRIOR_EVIDENCE_MISSING")
            validate_trial_observation_against_source_evidence(
                prior_observation,
                prior.snapshot,
                prior.run,
                prior.receipts,
                raw_page_bodies_by_receipt=prior.raw_page_bodies_by_receipt,
            )
            rebuilt_diff = build_exact_diff(
                prior,
                current,
                before_observation=prior_observation,
                after_observation=current_observation,
            )
            if rebuilt_diff != exact_diff:
                raise ProspectiveError("PROSPECTIVE_DIFF_INVALID")
        expected = build_public_model(
            nct_id=str(current.snapshot.get("nct_id")),
            epoch=epoch,
            observation=current_observation,
            exact_diff=exact_diff,
            generated_at=generated_at,
            prior_model=prior_model,
        )
        if dict(model) != expected:
            raise ProspectiveError("PROSPECTIVE_MODEL_BINDING_INVALID")
    except ProspectiveError:
        raise
    except Exception as exc:
        raise ProspectiveError("PROSPECTIVE_PUBLICATION_EVIDENCE_INVALID") from exc


__all__ = [
    "ProspectiveError",
    "SourceEvidence",
    "build_coverage_epoch",
    "build_exact_diff",
    "build_observation",
    "build_public_event",
    "build_public_model",
    "validate_public_model",
    "validate_publication_evidence",
]
