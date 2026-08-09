"""Run the manual, review-only institutional 13F R2 CAS witness.

The witness owns one run-unique key under the institutional evidence prefix.
It performs no listing, deletion, catalog publication, or selector mutation.
Success proves only the bounded conditional-write sequence encoded below; the
retained successor object and canonical local receipt are the review evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import re
import secrets
from typing import Any, Mapping, Sequence

from engine.institutional_census.models import (
    EVIDENCE_PREFIX,
    canonical_json_bytes,
    normalize_utc,
    validate_owned_key,
)
from engine.institutional_census.storage import build_institutional_13f_store
from engine.research_vault.r2_store import StrictConditionalWriteStore, VersionedBytes


RECEIPT_SCHEMA = "institutional_13f.r2_conformance_receipt/v1"
RECEIPT_ID_PREFIX = "i13fr2proof_"
PROTOCOL_ID = "institutional-13f-strict-conditional-write/v1"
CONFORMANCE_KEY_PREFIX = f"{EVIDENCE_PREFIX}/conformance/v1"
MAX_CONFORMANCE_OBJECT_BYTES = 4 * 1024
MAX_RECEIPT_BYTES = 128 * 1024
RECEIPT_FILENAME = "institutional_13f_r2_conformance_receipt.json"

_EXPECTED_REPOSITORY = "mastermindx-market-intelligence/macro"
_EXPECTED_WORKFLOW = ".github/workflows/smart-money-13f-r2-conformance.yml"
_HEX32_RE = re.compile(r"^[a-f0-9]{32}$")
_HEX40_RE = re.compile(r"^[a-f0-9]{40}$")
_HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
_RUN_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
_ACTOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")

_AUTHORITY = {
    "is_context_only": True,
    "provider_conformance_authority": False,
    "evidence_publication_authority": False,
    "catalog_publication_authority": False,
    "retention_authority": False,
    "ranking_authority": False,
    "signal_authority": False,
    "trade_authority": False,
    "prophet_authority": False,
}

_NONCLAIMS = {
    "not_a_provider_security_audit": True,
    "not_a_provider_durability_or_availability_proof": True,
    "not_a_concurrent_linearizability_proof": True,
    "not_a_multi_key_atomicity_proof": True,
    "not_a_production_retry_semantics_proof": True,
    "not_a_retention_or_deletion_proof": True,
    "not_a_catalog_or_filing_publication": True,
    "not_a_trading_or_investment_signal": True,
}


class Institutional13FR2ConformanceError(RuntimeError):
    """The provider witness could not prove its complete bounded protocol."""


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _payload(*, phase: str, revision: int, run_nonce: str) -> bytes:
    return canonical_json_bytes(
        {
            "schema": "institutional_13f.r2_conformance_payload/v1",
            "phase": phase,
            "revision": revision,
            "run_nonce": run_nonce,
        }
    )


def conformance_key(*, run_id: str, run_attempt: int, run_nonce: str) -> str:
    if _RUN_ID_RE.fullmatch(str(run_id or "")) is None:
        raise Institutional13FR2ConformanceError("run_id is invalid")
    if isinstance(run_attempt, bool) or not isinstance(run_attempt, int) or run_attempt <= 0:
        raise Institutional13FR2ConformanceError("run_attempt is invalid")
    if _HEX32_RE.fullmatch(str(run_nonce or "")) is None:
        raise Institutional13FR2ConformanceError("run_nonce must be 128 random bits in hex")
    return validate_owned_key(
        f"{CONFORMANCE_KEY_PREFIX}/{run_id}-{run_attempt}-{run_nonce}.json"
    )


def github_provenance_from_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    source = os.environ if environment is None else environment
    return {
        "repository": source.get("GITHUB_REPOSITORY", ""),
        "workflow_ref": source.get("GITHUB_WORKFLOW_REF", ""),
        "run_id": source.get("GITHUB_RUN_ID", ""),
        "run_attempt": source.get("GITHUB_RUN_ATTEMPT", ""),
        "commit_sha": source.get("GITHUB_SHA", ""),
        "event_name": source.get("GITHUB_EVENT_NAME", ""),
        "actor": source.get("GITHUB_ACTOR", ""),
    }


def _normalize_provenance(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "repository",
        "workflow_ref",
        "run_id",
        "run_attempt",
        "commit_sha",
        "event_name",
        "actor",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise Institutional13FR2ConformanceError("GitHub provenance shape is invalid")
    repository = value.get("repository")
    workflow_ref = value.get("workflow_ref")
    run_id = str(value.get("run_id") or "")
    attempt_text = str(value.get("run_attempt") or "")
    commit_sha = value.get("commit_sha")
    actor = value.get("actor")
    expected_ref = f"{_EXPECTED_REPOSITORY}/{_EXPECTED_WORKFLOW}@refs/heads/main"
    if (
        repository != _EXPECTED_REPOSITORY
        or workflow_ref != expected_ref
        or _RUN_ID_RE.fullmatch(run_id) is None
        or not attempt_text.isdigit()
        or int(attempt_text) <= 0
        or int(attempt_text) > 1000
        or not isinstance(commit_sha, str)
        or _HEX40_RE.fullmatch(commit_sha) is None
        or value.get("event_name") != "workflow_dispatch"
        or not isinstance(actor, str)
        or _ACTOR_RE.fullmatch(actor) is None
    ):
        raise Institutional13FR2ConformanceError(
            "provider proof requires a reviewed main-branch workflow_dispatch"
        )
    return {
        "repository": repository,
        "workflow_ref": workflow_ref,
        "run_id": run_id,
        "run_attempt": int(attempt_text),
        "commit_sha": commit_sha,
        "event_name": "workflow_dispatch",
        "actor": actor,
    }


def _read_versioned_exact(
    store: StrictConditionalWriteStore,
    *,
    key: str,
    expected: bytes,
    label: str,
) -> VersionedBytes:
    try:
        observed = store.get_bytes_strict_bounded_versioned(
            key, MAX_CONFORMANCE_OBJECT_BYTES
        )
    except Exception as exc:  # noqa: BLE001 - no ambiguous read can pass.
        raise Institutional13FR2ConformanceError(f"{label} versioned read failed") from exc
    if type(observed) is not VersionedBytes:
        raise Institutional13FR2ConformanceError(f"{label} versioned read is malformed")
    if observed.data != expected or not isinstance(observed.version, str) or not observed.version:
        raise Institutional13FR2ConformanceError(f"{label} exact readback failed")
    return observed


def _put_conditional(
    store: StrictConditionalWriteStore,
    *,
    key: str,
    body: bytes,
    expected_version: str | None,
    label: str,
) -> bool:
    try:
        result = store.put_bytes_strict_conditional(
            key,
            body,
            expected_version=expected_version,
            content_type="application/json",
        )
    except Exception as exc:  # noqa: BLE001 - transport ambiguity cannot pass proof.
        raise Institutional13FR2ConformanceError(f"{label} conditional write failed") from exc
    if type(result) is not bool:
        raise Institutional13FR2ConformanceError(f"{label} returned a non-boolean result")
    return result


def _receipt_identity(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body["receipt_id"] = ""
    return RECEIPT_ID_PREFIX + sha256(canonical_json_bytes(body)).hexdigest()


def validate_receipt(value: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "receipt_id",
        "status",
        "manual_only",
        "observed_at",
        "provenance",
        "scope",
        "protocol",
        "evidence",
        "authority",
        "nonclaims",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise Institutional13FR2ConformanceError("conformance receipt shape is invalid")
    if (
        value.get("schema") != RECEIPT_SCHEMA
        or value.get("status") != "passed"
        or value.get("manual_only") is not True
        or value.get("authority") != _AUTHORITY
        or value.get("nonclaims") != _NONCLAIMS
    ):
        raise Institutional13FR2ConformanceError("conformance receipt contract is invalid")
    if normalize_utc(str(value.get("observed_at") or ""), field="observed_at") != value.get(
        "observed_at"
    ):
        raise Institutional13FR2ConformanceError("conformance receipt clock is invalid")
    provenance = _normalize_provenance(value.get("provenance"))
    if provenance != value.get("provenance"):
        raise Institutional13FR2ConformanceError("conformance receipt provenance is invalid")

    scope = value.get("scope")
    if not isinstance(scope, Mapping) or set(scope) != {
        "owned_prefix", "key_sha256", "bucket_sha256"
    }:
        raise Institutional13FR2ConformanceError("conformance receipt scope is invalid")
    if scope.get("owned_prefix") != CONFORMANCE_KEY_PREFIX:
        raise Institutional13FR2ConformanceError("conformance receipt prefix is invalid")
    for field in ("key_sha256", "bucket_sha256"):
        if not isinstance(scope.get(field), str) or _HEX64_RE.fullmatch(scope[field]) is None:
            raise Institutional13FR2ConformanceError(f"conformance receipt {field} is invalid")

    protocol = value.get("protocol")
    if protocol != {
        "id": PROTOCOL_ID,
        "maximum_object_bytes": MAX_CONFORMANCE_OBJECT_BYTES,
        "steps": [
            "create_if_absent",
            "versioned_read_a",
            "duplicate_create_rejection",
            "exact_predecessor_successor",
            "versioned_read_b",
            "stale_predecessor_rejection",
            "final_exact_read_b",
        ],
    }:
        raise Institutional13FR2ConformanceError("conformance receipt protocol is invalid")

    evidence = value.get("evidence")
    expected_evidence_keys = {
        "payload_a",
        "payload_b",
        "payload_c",
        "version_a_sha256",
        "version_b_sha256",
        "duplicate_create_rejected",
        "successor_cas_accepted",
        "stale_predecessor_rejected",
        "final_payload_sha256",
        "no_list_or_delete_performed",
    }
    if not isinstance(evidence, Mapping) or set(evidence) != expected_evidence_keys:
        raise Institutional13FR2ConformanceError("conformance receipt evidence is invalid")
    for payload_field in ("payload_a", "payload_b", "payload_c"):
        descriptor = evidence.get(payload_field)
        if not isinstance(descriptor, Mapping) or set(descriptor) != {"sha256", "byte_length"}:
            raise Institutional13FR2ConformanceError("conformance payload descriptor is invalid")
        if (
            not isinstance(descriptor.get("sha256"), str)
            or _HEX64_RE.fullmatch(descriptor["sha256"]) is None
            or isinstance(descriptor.get("byte_length"), bool)
            or not isinstance(descriptor.get("byte_length"), int)
            or not 1 <= descriptor["byte_length"] <= MAX_CONFORMANCE_OBJECT_BYTES
        ):
            raise Institutional13FR2ConformanceError("conformance payload descriptor is invalid")
    if len({evidence[item]["sha256"] for item in ("payload_a", "payload_b", "payload_c")}) != 3:
        raise Institutional13FR2ConformanceError("conformance payloads must be distinct")
    for field in ("version_a_sha256", "version_b_sha256", "final_payload_sha256"):
        if not isinstance(evidence.get(field), str) or _HEX64_RE.fullmatch(evidence[field]) is None:
            raise Institutional13FR2ConformanceError(f"conformance {field} is invalid")
    if evidence["version_a_sha256"] == evidence["version_b_sha256"]:
        raise Institutional13FR2ConformanceError("successor did not advance the version token")
    if evidence["final_payload_sha256"] != evidence["payload_b"]["sha256"]:
        raise Institutional13FR2ConformanceError("final evidence does not retain successor bytes")
    for field in (
        "duplicate_create_rejected",
        "successor_cas_accepted",
        "stale_predecessor_rejected",
        "no_list_or_delete_performed",
    ):
        if evidence.get(field) is not True:
            raise Institutional13FR2ConformanceError(f"conformance proof did not establish {field}")
    if value.get("receipt_id") != _receipt_identity(value):
        raise Institutional13FR2ConformanceError("conformance receipt identity is invalid")


def canonical_receipt_bytes(value: Mapping[str, Any]) -> bytes:
    validate_receipt(value)
    payload = canonical_json_bytes(dict(value))
    if len(payload) > MAX_RECEIPT_BYTES:
        raise Institutional13FR2ConformanceError("conformance receipt exceeds byte ceiling")
    return payload


def run_conformance(
    store: StrictConditionalWriteStore,
    *,
    run_nonce: str,
    observed_at: str | datetime,
    provenance: Mapping[str, Any],
    bucket_name: str,
) -> dict[str, Any]:
    """Prove the strict conditional protocol on one fresh, retained object."""
    if not isinstance(store, StrictConditionalWriteStore):
        raise Institutional13FR2ConformanceError(
            "provider proof requires a StrictConditionalWriteStore"
        )
    normalized_provenance = _normalize_provenance(provenance)
    if not isinstance(bucket_name, str) or not bucket_name or len(bucket_name) > 255:
        raise Institutional13FR2ConformanceError("bucket_name is invalid")
    key = conformance_key(
        run_id=normalized_provenance["run_id"],
        run_attempt=normalized_provenance["run_attempt"],
        run_nonce=run_nonce,
    )
    observed_text = normalize_utc(observed_at, field="observed_at")
    body_a = _payload(phase="A", revision=1, run_nonce=run_nonce)
    body_b = _payload(phase="B", revision=2, run_nonce=run_nonce)
    body_c = _payload(phase="STALE", revision=3, run_nonce=run_nonce)
    if any(len(item) > MAX_CONFORMANCE_OBJECT_BYTES for item in (body_a, body_b, body_c)):
        raise Institutional13FR2ConformanceError("conformance payload exceeds byte ceiling")

    try:
        store.validate_strict_conditional_write_capability()
    except Exception as exc:  # noqa: BLE001 - capability is a pre-I/O hard gate.
        raise Institutional13FR2ConformanceError(
            "strict conditional-write capability validation failed"
        ) from exc

    if not _put_conditional(
        store,
        key=key,
        body=body_a,
        expected_version=None,
        label="create_if_absent",
    ):
        raise Institutional13FR2ConformanceError("run-unique conformance key already exists")
    version_a = _read_versioned_exact(
        store, key=key, expected=body_a, label="versioned_read_a"
    )
    if _put_conditional(
        store,
        key=key,
        body=body_c,
        expected_version=None,
        label="duplicate_create_rejection",
    ):
        raise Institutional13FR2ConformanceError("create-if-absent accepted an existing key")
    version_a_after_conflict = _read_versioned_exact(
        store, key=key, expected=body_a, label="read_after_duplicate_create"
    )
    if version_a_after_conflict.version != version_a.version:
        raise Institutional13FR2ConformanceError("duplicate create changed predecessor version")

    if not _put_conditional(
        store,
        key=key,
        body=body_b,
        expected_version=version_a.version,
        label="exact_predecessor_successor",
    ):
        raise Institutional13FR2ConformanceError("exact predecessor CAS was rejected")
    version_b = _read_versioned_exact(
        store, key=key, expected=body_b, label="versioned_read_b"
    )
    if version_b.version == version_a.version:
        raise Institutional13FR2ConformanceError("successor did not advance version token")
    if _put_conditional(
        store,
        key=key,
        body=body_c,
        expected_version=version_a.version,
        label="stale_predecessor_rejection",
    ):
        raise Institutional13FR2ConformanceError("stale predecessor CAS was accepted")
    final = _read_versioned_exact(
        store, key=key, expected=body_b, label="final_exact_read_b"
    )
    if final.version != version_b.version:
        raise Institutional13FR2ConformanceError("stale CAS changed successor version")

    def descriptor(payload: bytes) -> dict[str, Any]:
        return {"sha256": sha256(payload).hexdigest(), "byte_length": len(payload)}

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": "",
        "status": "passed",
        "manual_only": True,
        "observed_at": observed_text,
        "provenance": normalized_provenance,
        "scope": {
            "owned_prefix": CONFORMANCE_KEY_PREFIX,
            "key_sha256": _hash_text(key),
            "bucket_sha256": _hash_text(bucket_name),
        },
        "protocol": {
            "id": PROTOCOL_ID,
            "maximum_object_bytes": MAX_CONFORMANCE_OBJECT_BYTES,
            "steps": [
                "create_if_absent",
                "versioned_read_a",
                "duplicate_create_rejection",
                "exact_predecessor_successor",
                "versioned_read_b",
                "stale_predecessor_rejection",
                "final_exact_read_b",
            ],
        },
        "evidence": {
            "payload_a": descriptor(body_a),
            "payload_b": descriptor(body_b),
            "payload_c": descriptor(body_c),
            "version_a_sha256": _hash_text(str(version_a.version)),
            "version_b_sha256": _hash_text(str(version_b.version)),
            "duplicate_create_rejected": True,
            "successor_cas_accepted": True,
            "stale_predecessor_rejected": True,
            "final_payload_sha256": sha256(final.data or b"").hexdigest(),
            "no_list_or_delete_performed": True,
        },
        "authority": dict(_AUTHORITY),
        "nonclaims": dict(_NONCLAIMS),
    }
    receipt["receipt_id"] = _receipt_identity(receipt)
    validate_receipt(receipt)
    return receipt


def _write_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    payload = canonical_receipt_bytes(receipt)
    destination = path.expanduser().resolve()
    if destination.exists():
        raise Institutional13FR2ConformanceError("refusing to overwrite receipt output")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise Institutional13FR2ConformanceError("receipt temporary path already exists")
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=RECEIPT_FILENAME,
        help="Local canonical receipt path for review artifact upload",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    provenance = github_provenance_from_environment()
    store = build_institutional_13f_store()
    receipt = run_conformance(
        store,
        run_nonce=secrets.token_hex(16),
        observed_at=datetime.now(timezone.utc),
        provenance=provenance,
        bucket_name=os.environ.get("INSTITUTIONAL_13F_R2_BUCKET", ""),
    )
    _write_receipt(Path(args.output), receipt)
    print(
        f"institutional 13F R2 conformance passed: {receipt['receipt_id']} "
        f"({receipt['scope']['key_sha256']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
