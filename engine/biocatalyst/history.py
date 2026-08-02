"""Deterministic ClinicalTrials.gov Record History contracts for BioCatalyst.

This module is deliberately pure: collectors own HTTP/raw bytes and workers own
storage/pointer advancement.  B2 only turns already-receipted source versions
into immutable historical snapshots, replayable exact diffs, and strictly
decision-inert registry-record change facts.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from engine.sector_intelligence import (
    canonical_json_bytes,
    canonical_json_sha256,
    derive_trial_registry_change_descriptors,
    exact_history_json_diff,
    validate_ctgov_history_receipt_against_raw_response,
    validate_ctgov_history_run_against_receipts,
    validate_trial_history_diff_against_snapshots,
    validate_trial_history_read_model,
    validate_trial_history_snapshot_against_evidence,
    validate_trial_registry_change_fact_against_diff,
)
from engine.sector_intelligence.contracts import ContractError


class HistoryError(ValueError):
    """A bounded failure building the historical source-fact plane."""


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
_SOURCE_ID = "clinicaltrials_gov_record_history"
_PARSER_VERSION = "clinicaltrials_record_history_parser.v1"
_COVERAGE_CLASS = "record_history_complete"


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value))
    except ContractError as exc:
        raise HistoryError("value_must_be_canonical_json") from exc


def _with_hash(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    document = _json_copy(payload)
    if not isinstance(document, dict):  # defensive; mappings encode as objects.
        raise HistoryError("payload_must_be_object")
    document[field] = canonical_json_sha256(document)
    return document


def _history_uri(nct_id: str, source_version: int) -> str:
    return f"https://clinicaltrials.gov/study/{nct_id}?a={source_version + 1}&tab=history"


def _source_uri(nct_id: str, resource_kind: str, source_version: int | None) -> str:
    root = f"https://clinicaltrials.gov/api/int/studies/{nct_id}"
    if resource_kind == "history_index":
        return f"{root}?history=true"
    if isinstance(source_version, bool) or not isinstance(source_version, int) or source_version < 0:
        raise HistoryError("invalid_history_source_version")
    return f"{root}/history/{source_version}"


def build_history_receipt(
    *,
    run_id: str,
    nct_id: str,
    resource_kind: str,
    source_version: int | None,
    raw_response: bytes,
    received_at: str,
    transaction_from: str,
    response_headers: Mapping[str, str] | None = None,
    request_headers: Mapping[str, str] | None = None,
    receipt_suffix: str | None = None,
) -> dict[str, Any]:
    """Build one sanitized, content-addressed Record History receipt."""

    if resource_kind not in {"history_index", "history_version"}:
        raise HistoryError("invalid_history_resource_kind")
    if not isinstance(raw_response, bytes) or not raw_response:
        raise HistoryError("history_raw_response_must_be_nonempty_bytes")
    raw_hash = hashlib.sha256(raw_response).hexdigest()
    source_uri = _source_uri(nct_id, resource_kind, source_version)
    if receipt_suffix is None:
        receipt_suffix = "index" if resource_kind == "history_index" else f"version_{source_version}"
    if not isinstance(receipt_suffix, str) or re.fullmatch(r"[A-Za-z0-9_-]+", receipt_suffix) is None:
        raise HistoryError("invalid_history_receipt_suffix")
    resource_key = "index" if resource_kind == "history_index" else f"version-{source_version}"
    seed = canonical_json_sha256(
        {
            "run_id": run_id,
            "nct_id": nct_id,
            "resource_kind": resource_kind,
            "source_version": source_version,
            "raw_response_sha256": raw_hash,
            "receipt_suffix": receipt_suffix,
        }
    )
    payload = {
        "contract_id": "ctgov_history_receipt.v1",
        "schema_version": "1.0.0",
        "receipt_id": f"ctgov_history_receipt_{nct_id}_{seed[:24]}",
        "run_id": run_id,
        "source_id": _SOURCE_ID,
        "resource_kind": resource_kind,
        "nct_id": nct_id,
        "source_version": source_version,
        "request": {
            "method": "GET",
            "source_uri": source_uri,
            "headers": dict(request_headers or {"accept": "application/json"}),
            "credentials_stored": False,
        },
        "response": {
            "status_code": 200,
            "headers": dict(response_headers or {"content-type": "application/json"}),
            "exact_response_sha256": raw_hash,
            "raw_response_object_key": (
                f"biocatalyst/raw/clinicaltrials/history/{nct_id}/{resource_key}/{raw_hash}.json"
            ),
            "byte_count": len(raw_response),
            "received_at": received_at,
        },
        "parser_version": _PARSER_VERSION,
        "transaction_from": transaction_from,
        "transaction_to": None,
        "hash_scope": "canonical_payload_excluding_receipt_payload_sha256",
    }
    receipt = _with_hash(payload, "receipt_payload_sha256")
    validate_ctgov_history_receipt_against_raw_response(receipt, raw_response)
    return receipt


def build_history_run(
    *,
    run_id: str,
    nct_id: str,
    index_receipt: Mapping[str, Any],
    index_post_receipt: Mapping[str, Any],
    version_receipts: Sequence[Mapping[str, Any]],
    version_manifest: Sequence[Mapping[str, Any]],
    raw_bodies_by_receipt: Mapping[str, bytes | bytearray | memoryview],
    started_at: str,
    finished_at: str,
    transaction_from: str,
) -> dict[str, Any]:
    """Build a complete per-NCT version manifest after successful collection."""

    manifest = _json_copy(list(version_manifest))
    receipts = [_json_copy(receipt) for receipt in version_receipts]
    if not isinstance(manifest, list) or not isinstance(receipts, list):
        raise HistoryError("history_run_manifest_must_be_json_array")
    payload = {
        "contract_id": "ctgov_history_run.v1",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "source_id": _SOURCE_ID,
        "nct_id": nct_id,
        "history_index_receipt_ref": index_receipt.get("receipt_id"),
        "history_index_post_receipt_ref": index_post_receipt.get("receipt_id"),
        "version_manifest": manifest,
        "history_version_receipt_refs": [receipt.get("receipt_id") for receipt in receipts],
        "started_at": started_at,
        "finished_at": finished_at,
        "run_state": "complete",
        "completeness_state": "history_complete",
        "parser_version": _PARSER_VERSION,
        "error_codes": [],
        "transaction_from": transaction_from,
        "transaction_to": None,
        "hash_scope": "canonical_payload_excluding_run_payload_sha256",
    }
    run = _with_hash(payload, "run_payload_sha256")
    validate_ctgov_history_run_against_receipts(
        run,
        index_receipt,
        index_post_receipt,
        receipts,
        raw_bodies_by_receipt=raw_bodies_by_receipt,
    )
    return run


def build_history_source_snapshot(
    *,
    run: Mapping[str, Any],
    index_receipt: Mapping[str, Any],
    index_post_receipt: Mapping[str, Any],
    version_receipt: Mapping[str, Any],
    all_version_receipts: Sequence[Mapping[str, Any]],
    raw_bodies_by_receipt: Mapping[str, bytes | bytearray | memoryview],
    canonical_study: Mapping[str, Any],
    transaction_from: str,
) -> dict[str, Any]:
    """Build one immutable historical source snapshot from a version response."""

    source_version = version_receipt.get("source_version")
    if isinstance(source_version, bool) or not isinstance(source_version, int) or source_version < 0:
        raise HistoryError("invalid_history_source_version")
    manifest = run.get("version_manifest")
    if not isinstance(manifest, list):
        raise HistoryError("history_version_missing_from_manifest")
    entry = next(
        (
            candidate
            for candidate in manifest
            if isinstance(candidate, Mapping)
            and candidate.get("source_version") == source_version
        ),
        None,
    )
    if not isinstance(entry, Mapping):
        raise HistoryError("history_manifest_not_contiguous")
    study = _json_copy(canonical_study)
    if not isinstance(study, dict):
        raise HistoryError("history_study_must_be_object")
    nct_id = run.get("nct_id")
    if not isinstance(nct_id, str):
        raise HistoryError("history_run_missing_nct_id")
    content_hash = canonical_json_sha256(study)
    snapshot_seed = canonical_json_sha256(
        {
            "nct_id": nct_id,
            "source_version": source_version,
            "canonical_content_sha256": content_hash,
            "run_ref": run.get("run_id"),
        }
    )
    payload = {
        "contract_id": "trial_history_source_snapshot.v1",
        "schema_version": "1.0.0",
        "source_snapshot_id": f"ctgov_history_snapshot_{nct_id}_{snapshot_seed[:24]}",
        "nct_id": nct_id,
        "source_id": _SOURCE_ID,
        "run_ref": run.get("run_id"),
        "history_index_receipt_ref": index_receipt.get("receipt_id"),
        "history_version_receipt_ref": version_receipt.get("receipt_id"),
        "source_version": source_version,
        "display_version": source_version + 1,
        "source_record_ref": (
            f"src:ctgov-history:{nct_id}:version:{source_version}:sha256:{content_hash}"
        ),
        "source_uri": _history_uri(nct_id, source_version),
        "source_submitted_at": entry.get("source_submitted_at"),
        "source_last_update_submit_qc_at": entry.get("source_last_update_submit_qc_at"),
        "canonical_study": study,
        "canonical_content_sha256": content_hash,
        "retrieved_at": version_receipt.get("response", {}).get("received_at"),
        "source_fact": True,
        "current_only": False,
        "coverage_class": _COVERAGE_CLASS,
        "authority": _json_copy(_AUTHORITY),
        "transaction_from": transaction_from,
        "transaction_to": None,
        "hash_scope": "canonical_payload_excluding_snapshot_payload_sha256",
    }
    snapshot = _with_hash(payload, "snapshot_payload_sha256")
    validate_trial_history_snapshot_against_evidence(
        snapshot,
        run,
        index_receipt,
        index_post_receipt,
        version_receipt,
        all_version_receipts=all_version_receipts,
        raw_bodies_by_receipt=raw_bodies_by_receipt,
    )
    return snapshot


def build_history_exact_diff(
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    *,
    transaction_from: str,
) -> dict[str, Any]:
    """Build and replay-validate one exact diff between consecutive versions."""

    before = _json_copy(before_snapshot)
    after = _json_copy(after_snapshot)
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise HistoryError("history_snapshot_must_be_object")
    if before.get("nct_id") != after.get("nct_id"):
        raise HistoryError("history_diff_cross_nct")
    if after.get("source_version") != before.get("source_version", -2) + 1:
        raise HistoryError("history_diff_nonconsecutive_versions")
    # The after snapshot is the source transaction that made the exact diff
    # knowable; callers cannot advance that provenance clock independently.
    transaction_from = after.get("transaction_from")
    operations = exact_history_json_diff(before.get("canonical_study"), after.get("canonical_study"))
    if not operations:
        raise HistoryError("history_diff_requires_changed_source_content")
    seed = canonical_json_sha256(
        {
            "before_source_snapshot_ref": before.get("source_snapshot_id"),
            "after_source_snapshot_ref": after.get("source_snapshot_id"),
            "before_content_sha256": before.get("canonical_content_sha256"),
            "after_content_sha256": after.get("canonical_content_sha256"),
        }
    )
    payload = {
        "contract_id": "trial_history_exact_diff.v1",
        "schema_version": "1.0.0",
        "diff_id": f"trial_history_diff_{before.get('nct_id')}_{seed[:24]}",
        "nct_id": before.get("nct_id"),
        "before_source_snapshot_ref": before.get("source_snapshot_id"),
        "after_source_snapshot_ref": after.get("source_snapshot_id"),
        "before_source_version": before.get("source_version"),
        "after_source_version": after.get("source_version"),
        "before_content_sha256": before.get("canonical_content_sha256"),
        "after_content_sha256": after.get("canonical_content_sha256"),
        "source_record_refs": [before.get("source_record_ref"), after.get("source_record_ref")],
        "operations": operations,
        "retrieved_at": after.get("retrieved_at"),
        "source_fact": True,
        "current_only": False,
        "coverage_class": _COVERAGE_CLASS,
        "semantic_alignment": "exact_source_json_path_only",
        "interpretation": "registry_record_changed",
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "authority": _json_copy(_AUTHORITY),
        "transaction_from": transaction_from,
        "transaction_to": None,
        "hash_scope": "canonical_payload_excluding_diff_payload_sha256",
    }
    diff = _with_hash(payload, "diff_payload_sha256")
    validate_trial_history_diff_against_snapshots(diff, before, after)
    return diff


def _change_fact(
    *,
    diff: Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    kind: str,
    source_json_paths: Sequence[str],
    before_value: Any,
    after_value: Any,
) -> dict[str, Any]:
    paths = sorted(set(source_json_paths))
    seed = canonical_json_sha256(
        {
            "diff_ref": diff.get("diff_id"),
            "kind": kind,
            "source_json_paths": paths,
            "before_value": before_value,
            "after_value": after_value,
        }
    )
    payload = {
        "contract_id": "trial_registry_change_fact.v1",
        "schema_version": "1.0.0",
        "change_fact_id": f"trial_registry_change_{diff.get('nct_id')}_{seed[:24]}",
        "nct_id": diff.get("nct_id"),
        "diff_ref": diff.get("diff_id"),
        "before_source_snapshot_ref": before_snapshot.get("source_snapshot_id"),
        "after_source_snapshot_ref": after_snapshot.get("source_snapshot_id"),
        "before_source_version": before_snapshot.get("source_version"),
        "after_source_version": after_snapshot.get("source_version"),
        "kind": kind,
        "source_json_paths": paths,
        "before_value": _json_copy(before_value),
        "after_value": _json_copy(after_value),
        "semantic_method": "deterministic_registry_field_delta.v1",
        "interpretation": "registry_record_changed",
        "source_fact": True,
        "current_only": False,
        "coverage_class": _COVERAGE_CLASS,
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "authority": _json_copy(_AUTHORITY),
        "transaction_from": diff.get("transaction_from"),
        "transaction_to": None,
        "hash_scope": "canonical_payload_excluding_fact_payload_sha256",
    }
    fact = _with_hash(payload, "fact_payload_sha256")
    validate_trial_registry_change_fact_against_diff(
        fact, diff, before_snapshot, after_snapshot
    )
    return fact


def derive_history_change_facts(
    before_snapshot: Mapping[str, Any], after_snapshot: Mapping[str, Any], diff: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Derive bounded registry-field facts from a replay-validated exact diff.

    Ambiguous endpoint/intervention pairing remains exact-diff-only.  No fact
    states that a protocol, site, clinical endpoint, sponsor ownership, or
    real-world trial event changed.
    """

    validate_trial_history_diff_against_snapshots(diff, before_snapshot, after_snapshot)
    before_study = before_snapshot.get("canonical_study")
    after_study = after_snapshot.get("canonical_study")
    if not isinstance(before_study, Mapping) or not isinstance(after_study, Mapping):
        raise HistoryError("history_snapshot_missing_canonical_study")
    facts = [
        _change_fact(
            diff=diff,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            kind=descriptor["kind"],
            source_json_paths=descriptor["source_json_paths"],
            before_value=descriptor["before_value"],
            after_value=descriptor["after_value"],
        )
        for descriptor in derive_trial_registry_change_descriptors(
            before_study, after_study
        )
    ]

    return sorted(
        facts,
        key=lambda fact: (fact["after_source_version"], fact["kind"], fact["change_fact_id"]),
    )


def build_history_read_model(
    snapshots: Sequence[Mapping[str, Any]], facts: Sequence[Mapping[str, Any]], *, generated_at: str
) -> dict[str, Any]:
    """Build a public-safe history model from immutable B2 facts."""

    ordered_snapshots = sorted((_json_copy(item) for item in snapshots), key=lambda item: item["source_version"])
    ordered_facts = sorted((_json_copy(item) for item in facts), key=lambda item: (item["after_source_version"], item["kind"], item["change_fact_id"]))
    if not ordered_snapshots:
        raise HistoryError("history_read_model_requires_snapshots")
    nct_id = ordered_snapshots[0].get("nct_id")
    if any(snapshot.get("nct_id") != nct_id for snapshot in ordered_snapshots):
        raise HistoryError("history_read_model_cross_nct")
    if any(fact.get("nct_id") != nct_id for fact in ordered_facts):
        raise HistoryError("history_read_model_fact_cross_nct")
    seed = canonical_json_sha256(
        {"nct_id": nct_id, "snapshots": [snapshot["snapshot_payload_sha256"] for snapshot in ordered_snapshots], "facts": [fact["fact_payload_sha256"] for fact in ordered_facts]}
    )
    payload = {
        "contract_id": "trial_history_read_model.v1", "schema_version": "1.0.0",
        "history_model_id": f"trial_history_model_{nct_id}_{seed[:24]}", "nct_id": nct_id,
        "available": True, "source_name": "ClinicalTrials.gov",
        "source_history_url": f"https://clinicaltrials.gov/study/{nct_id}?tab=history",
        "coverage_class": _COVERAGE_CLASS, "current_only": False, "unavailable_reason": None,
        "retrieved_at": ordered_snapshots[-1]["retrieved_at"],
        "versions": [{"display_version": snapshot["display_version"], "source_submitted_at": snapshot["source_submitted_at"], "url": snapshot["source_uri"]} for snapshot in ordered_snapshots],
        "changes": [{"kind": fact["kind"], "before_display_version": fact["before_source_version"] + 1, "after_display_version": fact["after_source_version"] + 1, "before_value": fact["before_value"], "after_value": fact["after_value"]} for fact in ordered_facts],
        "authority": _json_copy(_AUTHORITY), "generated_at": generated_at,
        "hash_scope": "canonical_payload_excluding_model_payload_sha256",
    }
    model = _with_hash(payload, "model_payload_sha256")
    validate_trial_history_read_model(model, ordered_snapshots, ordered_facts)
    return model


def build_unavailable_history_read_model(
    nct_id: str, *, unavailable_reason: str, generated_at: str
) -> dict[str, Any]:
    """Build an explicit safe history artifact when no complete chain exists."""

    allowed = {"disabled", "not_collected", "incomplete_chain", "source_shape_drift", "last_good_unavailable"}
    if unavailable_reason not in allowed:
        raise HistoryError("invalid_history_unavailable_reason")
    seed = canonical_json_sha256({"nct_id": nct_id, "reason": unavailable_reason, "generated_at": generated_at})
    payload = {
        "contract_id": "trial_history_read_model.v1", "schema_version": "1.0.0",
        "history_model_id": f"trial_history_model_{nct_id}_{seed[:24]}", "nct_id": nct_id,
        "available": False, "source_name": "ClinicalTrials.gov",
        "source_history_url": f"https://clinicaltrials.gov/study/{nct_id}?tab=history",
        "coverage_class": "unavailable", "current_only": False,
        "unavailable_reason": unavailable_reason, "retrieved_at": None,
        "versions": [], "changes": [], "authority": _json_copy(_AUTHORITY),
        "generated_at": generated_at,
        "hash_scope": "canonical_payload_excluding_model_payload_sha256",
    }
    model = _with_hash(payload, "model_payload_sha256")
    validate_trial_history_read_model(model, [], [])
    return model
