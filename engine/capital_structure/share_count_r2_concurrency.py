"""Manual-only, non-production R2 concurrent-writer witness.

This module proves a deliberately narrow transport fact against eight fresh
objects in a disposable witness namespace.  It cannot enumerate, delete,
publish, or sign any share-count data.  The operator wrapper owns credentials
and OS processes; this reviewed core owns the closed protocol, evidence
classification, canonical receipt, and bounded verifier reads.

The witness is fail-closed.  In particular, a 409, an untyped exception, a
lost response, sequential worker spans, or an unavailable worker hook is not a
concurrency proof.  A worker timeout that could leave an RPC in flight is
represented by :class:`R2ConcurrencyInFlight` and must not produce a semantic
receipt or a readback while the write may still mutate remotely.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
import time
from typing import Any, Callable, Mapping, Protocol, Sequence

from botocore.exceptions import ClientError


RECEIPT_SCHEMA = "capital_structure.share_count_r2_concurrency_receipt/v1"
RECEIPT_ID_PREFIX = "r2-concurrency-witness:cs-share-count-v1:"
ROUND_COUNT = 8
MAX_OBJECT_BYTES = 4096
MAX_RECEIPT_BYTES = 256 * 1024
MAX_DEADLINE_SECONDS = 240.0
PROTOCOL_ID = "r2-conditional-concurrency-witness/v1"
CONCURRENCY_KEY_PREFIX = "capital_structure/share_counts/concurrency-witness/v1/"
DEPENDENCY_LOCK_NAME = "capital-share-r2-conformance-macos-arm64-py312.lock"

_KEY_RE = re.compile(
    r"^capital_structure/share_counts/concurrency-witness/v1/"
    r"[a-f0-9]{32}/round-[1-8]\.json$",
)
_HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
_HOST_RE = re.compile(
    r"^[a-f0-9]{32}\.(?:(?:eu|fedramp)\.)?r2\.cloudflarestorage\.com$",
)
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
_RUN_RE = re.compile(r"^[1-9][0-9]{0,19}$")
_ACTOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
_EXPECTED_REPOSITORY = "chriswong6031-creator/macro"
_WORKFLOW_NAME = "capital-share-count-r2-concurrency.yml"

_NO_AUTHORITY = {
    "is_context_only": True,
    "concurrency_witness_authority": False,
    "provider_security_authority": False,
    "publication_authority": False,
    "share_count_ledger_authority": False,
    "retention_authority": False,
    "instrument_authority": False,
    "capacity_authority": False,
    "runway_authority": False,
    "risk_authority": False,
    "rank_authority": False,
    "sizing_authority": False,
    "entry_authority": False,
    "trade_authority": False,
    "prophet_authority": False,
}

_NONCLAIMS = {
    "not_a_share_count_source": True,
    "not_a_publication_authority": True,
    "not_a_provider_security_or_linearizability_audit": True,
    "not_a_server_simultaneity_proof": True,
    "not_a_provider_wide_or_future_behavior_proof": True,
    "not_a_failure_domain_or_fault_injection_proof": True,
    "not_a_multi_key_atomicity_proof": True,
    "not_a_production_configuration_or_activation_proof": True,
    "not_a_provider_durability_or_availability_proof": True,
    "not_a_credential_authentication_proof": True,
    "not_a_retention_or_deletion_proof": True,
    "not_a_production_retry_semantics_proof": True,
    "not_a_trading_or_investment_signal": True,
}


class R2ConcurrencyError(RuntimeError):
    """The bounded concurrent-writer witness cannot establish its claim."""


class R2ConcurrencyInconclusive(R2ConcurrencyError):
    """An ambiguous transport or timing outcome is not a witness pass."""


class R2ConcurrencyInFlight(R2ConcurrencyInconclusive):
    """A child might still mutate remotely; do not read back or write a receipt."""

    workers_may_be_in_flight = True


class R2ConcurrencyObservedFailure(R2ConcurrencyInconclusive):
    """Closed stage/category evidence for a non-passing run."""

    def __init__(
        self,
        *,
        status: str,
        stage: str,
        category: str,
        completed_rounds: tuple[int, ...],
    ) -> None:
        super().__init__(f"R2 concurrency witness failed: {stage}/{category}")
        self.status = status
        self.failure_stage = stage
        self.failure_category = category
        self.completed_rounds = completed_rounds


class R2VerifierClient(Protocol):
    def head_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def get_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def put_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def reset_put_attempt_evidence(self) -> None: ...

    def take_put_attempt_evidence(self) -> "VerifierPutAttempt": ...


@dataclass(frozen=True)
class RoundPlan:
    """All key and candidate bytes fixed before any conditional race starts."""

    round_id: int
    run_nonce: str
    key: str
    genesis_left: bytes
    genesis_right: bytes
    successor_left: bytes
    successor_right: bytes


@dataclass(frozen=True)
class WorkerIdentity:
    worker_id: str
    process_id: int
    session_instance_sha256: str
    client_instance_sha256: str
    retry_mode: str
    total_max_attempts: int
    before_send_hook_installed: bool
    needs_retry_hook_installed: bool


@dataclass(frozen=True)
class WorkerAttempt:
    worker_id: str
    process_id: int
    issued_puts: int
    before_send_count: int
    needs_retry_attempts: tuple[int, ...]
    transport_started_ns: int | None
    completed_ns: int | None
    http_status: int | None
    error_code: str | None
    error_status: int | None
    retry_attempts: int | None
    exact_client_error: bool
    request_id_sha256: str | None
    outcome: str


@dataclass(frozen=True)
class VerifierPutAttempt:
    issued_puts: int
    before_send_count: int
    needs_retry_attempts: tuple[int, ...]
    retry_attempts: int | None
    exact_client_error: bool
    request_id_sha256: str | None


class PersistentRaceWorkers(Protocol):
    @property
    def identities(self) -> tuple[WorkerIdentity, WorkerIdentity]: ...

    def race(
        self,
        *,
        round_id: int,
        phase: str,
        key: str,
        left_body: bytes,
        right_body: bytes,
        condition_name: str,
        condition_value: str,
        deadline: float,
    ) -> tuple[WorkerAttempt, WorkerAttempt]: ...


@dataclass(frozen=True)
class _Deadline:
    deadline: float
    monotonic: Callable[[], float]

    def check(self, label: str) -> None:
        try:
            current = self.monotonic()
        except Exception as exc:  # noqa: BLE001
            raise R2ConcurrencyInconclusive(
                f"R2 concurrency monotonic clock failed during {label}",
            ) from exc
        if (
            isinstance(current, bool)
            or not isinstance(current, (int, float))
            or not math.isfinite(current)
        ):
            raise R2ConcurrencyInconclusive(
                f"R2 concurrency monotonic clock is invalid during {label}",
            )
        if current >= self.deadline:
            raise R2ConcurrencyInconclusive(
                f"R2 concurrency deadline exceeded during {label}",
            )

    def call(self, label: str, call: Callable[..., Any], /, **kwargs: Any) -> Any:
        self.check(f"before {label}")
        try:
            result = call(**kwargs)
        except Exception:
            self.check(f"after {label}")
            raise
        try:
            self.check(f"after {label}")
        except Exception:
            self._close_returned_body(result, label=label)
            raise
        return result

    @staticmethod
    def _close_returned_body(response: Any, *, label: str) -> None:
        stream = response.get("Body") if isinstance(response, Mapping) else None
        if not callable(getattr(stream, "close", None)):
            return
        try:
            stream.close()
        except Exception as exc:  # noqa: BLE001
            raise R2ConcurrencyInconclusive(
                f"R2 concurrency {label} body close failed after deadline",
            ) from exc


@dataclass(frozen=True)
class _Head:
    etag: str
    content_length: int
    content_type: str


def build_precommitted_plan(*, run_nonce: str) -> tuple[RoundPlan, ...]:
    """Build all eight fresh keys and all four candidate bodies before racing."""
    if not isinstance(run_nonce, str) or re.fullmatch(r"[a-f0-9]{32}", run_nonce) is None:
        raise R2ConcurrencyError("R2 concurrency run nonce is invalid")
    rounds: list[RoundPlan] = []
    for round_id in range(1, ROUND_COUNT + 1):
        key = f"{CONCURRENCY_KEY_PREFIX}{run_nonce}/round-{round_id}.json"
        candidates = {
            ("genesis", "left"): _candidate_body(run_nonce, round_id, "genesis", "left"),
            ("genesis", "right"): _candidate_body(run_nonce, round_id, "genesis", "right"),
            ("successor", "left"): _candidate_body(run_nonce, round_id, "successor", "left"),
            ("successor", "right"): _candidate_body(run_nonce, round_id, "successor", "right"),
        }
        rounds.append(
            RoundPlan(
                round_id=round_id,
                run_nonce=run_nonce,
                key=key,
                genesis_left=candidates[("genesis", "left")],
                genesis_right=candidates[("genesis", "right")],
                successor_left=candidates[("successor", "left")],
                successor_right=candidates[("successor", "right")],
            ),
        )
    return tuple(rounds)


def plan_commitment_sha256(rounds: Sequence[RoundPlan]) -> str:
    """Commit keys, candidate hashes, and protocol before the first race."""
    normalized = _validate_plan(rounds)
    record = {
        "protocol": PROTOCOL_ID,
        "round_count": ROUND_COUNT,
        "rounds": [
            {
                "round": item.round_id,
                "key_sha256": _hash_text(item.key),
                "genesis_candidate_sha256": [_hash_bytes(item.genesis_left), _hash_bytes(item.genesis_right)],
                "successor_candidate_sha256": [_hash_bytes(item.successor_left), _hash_bytes(item.successor_right)],
            }
            for item in normalized
        ],
    }
    return _hash_bytes(_canonical_json(record))


def run_concurrency_witness(
    *,
    workers: PersistentRaceWorkers,
    verifier: R2VerifierClient,
    bucket: str,
    endpoint_host: str,
    rounds: Sequence[RoundPlan],
    github_provenance: Mapping[str, Any],
    execution_provenance: Mapping[str, Any],
    observed_at: datetime,
    deadline_seconds: float = MAX_DEADLINE_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Run eight precommitted absent-key and same-E0 conditional races.

    E0 is intentionally *not* part of the global plan: it cannot exist before
    genesis.  The successor phase instead receives a distinct commitment only
    after the verifier has authenticated E0 and before either worker receives
    E0's opaque token.
    """
    validated_rounds = _validate_plan(rounds)
    _require_verifier(verifier)
    _require_bucket(bucket)
    host = _require_endpoint_host(endpoint_host)
    provenance = _normalize_github_provenance(github_provenance)
    execution = _normalize_execution_provenance(execution_provenance)
    created_at = _iso_timestamp(observed_at)
    seconds = _deadline_seconds(deadline_seconds)
    try:
        started = monotonic()
    except Exception as exc:  # noqa: BLE001
        raise R2ConcurrencyInconclusive("R2 concurrency monotonic clock failed") from exc
    if (
        isinstance(started, bool)
        or not isinstance(started, (int, float))
        or not math.isfinite(started)
    ):
        raise R2ConcurrencyInconclusive("R2 concurrency monotonic clock is invalid")
    deadline = _Deadline(float(started) + seconds, monotonic)
    global_commitment = plan_commitment_sha256(validated_rounds)
    identities = _validate_worker_identities(workers)
    completed_rounds: list[int] = []
    round_receipts: list[dict[str, Any]] = []
    for round_plan in validated_rounds:
        try:
            deadline.check(f"round {round_plan.round_id} absence preflight")
            _run_stage(
                "absence_preflight",
                completed_rounds,
                lambda: _expect_typed_absence(
                    deadline=deadline,
                    verifier=verifier,
                    bucket=bucket,
                    key=round_plan.key,
                ),
            )
            genesis_attempts = _run_stage(
                "genesis_race",
                completed_rounds,
                lambda: workers.race(
                    round_id=round_plan.round_id,
                    phase="genesis",
                    key=round_plan.key,
                    left_body=round_plan.genesis_left,
                    right_body=round_plan.genesis_right,
                    condition_name="IfNoneMatch",
                    condition_value="*",
                    deadline=deadline.deadline,
                ),
            )
            genesis = _verify_race(
                stage="genesis_race",
                attempts=genesis_attempts,
                identities=identities,
                left_body=round_plan.genesis_left,
                right_body=round_plan.genesis_right,
                completed_rounds=tuple(completed_rounds),
            )
            e0 = _run_stage(
                "genesis_verify",
                completed_rounds,
                lambda: _verify_exact_object(
                    deadline=deadline,
                    verifier=verifier,
                    bucket=bucket,
                    key=round_plan.key,
                    expected_body=genesis["winner_body"],
                    label=f"round {round_plan.round_id} E0 verifier",
                ),
            )
            successor_commitment = _successor_commitment(
                round_plan=round_plan,
                e0_etag=e0.etag,
            )
            successor_attempts = _run_stage(
                "successor_race",
                completed_rounds,
                lambda: workers.race(
                    round_id=round_plan.round_id,
                    phase="successor",
                    key=round_plan.key,
                    left_body=round_plan.successor_left,
                    right_body=round_plan.successor_right,
                    condition_name="IfMatch",
                    condition_value=e0.etag,
                    deadline=deadline.deadline,
                ),
            )
            successor = _verify_race(
                stage="successor_race",
                attempts=successor_attempts,
                identities=identities,
                left_body=round_plan.successor_left,
                right_body=round_plan.successor_right,
                completed_rounds=tuple(completed_rounds),
            )
            e1 = _run_stage(
                "successor_verify",
                completed_rounds,
                lambda: _verify_exact_object(
                    deadline=deadline,
                    verifier=verifier,
                    bucket=bucket,
                    key=round_plan.key,
                    expected_body=successor["winner_body"],
                    label=f"round {round_plan.round_id} E1 verifier",
                ),
            )
            if e1.etag == e0.etag:
                _raise_observed("successor_verify", "etag_not_new", completed_rounds)
            verifier.reset_put_attempt_evidence()
            _expect_typed_412(
                deadline=deadline,
                call=lambda: verifier.put_object(
                    Bucket=bucket,
                    Key=round_plan.key,
                    Body=genesis["loser_body"],
                    ContentType="application/json",
                    Metadata={"sha256": _hash_bytes(genesis["loser_body"])},
                    IfMatch=e0.etag,
                ),
                label=f"round {round_plan.round_id} stale verifier PUT",
                completed_rounds=completed_rounds,
            )
            stale_attempt = verifier.take_put_attempt_evidence()
            _validate_verifier_put_attempt(
                stale_attempt,
                completed_rounds=completed_rounds,
            )
            final = _run_stage(
                "stale_verify",
                completed_rounds,
                lambda: _verify_exact_object(
                    deadline=deadline,
                    verifier=verifier,
                    bucket=bucket,
                    key=round_plan.key,
                    expected_body=successor["winner_body"],
                    label=f"round {round_plan.round_id} final verifier",
                ),
            )
            if final.etag != e1.etag:
                _raise_observed("stale_verify", "post_hoc_rewrite", completed_rounds)
            round_receipts.append(
                _round_receipt(
                    round_plan=round_plan,
                    genesis=genesis,
                    e0=e0,
                    successor=successor,
                    successor_commitment=successor_commitment,
                    e1=e1,
                    final=final,
                    stale_attempt=stale_attempt,
                ),
            )
            completed_rounds.append(round_plan.round_id)
        except R2ConcurrencyInFlight:
            raise
        except R2ConcurrencyObservedFailure:
            raise
        except R2ConcurrencyError as exc:
            raise R2ConcurrencyObservedFailure(
                status="inconclusive",
                stage="probe",
                category="transport_or_deadline",
                completed_rounds=tuple(completed_rounds),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise R2ConcurrencyObservedFailure(
                status="inconclusive",
                stage="probe",
                category="transport_or_deadline",
                completed_rounds=tuple(completed_rounds),
            ) from exc
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": "",
        "status": "passed",
        "failure": None,
        "manual_only": True,
        "created_at": created_at,
        "deadline_seconds": seconds,
        "round_count": ROUND_COUNT,
        "plan_commitment_sha256": global_commitment,
        "scope": {
            "admitted": True,
            "endpoint_host": host,
            "bucket_sha256": _hash_text(bucket),
        },
        "github_provenance": provenance,
        "execution_provenance": execution,
        "worker_topology": _worker_topology_receipt(identities),
        "rounds": round_receipts,
        "output_authority": dict(_NO_AUTHORITY),
        "nonclaims": dict(_NONCLAIMS),
    }
    receipt["receipt_id"] = _receipt_id(receipt)
    validate_concurrency_receipt(receipt)
    return {"status": "passed", "receipt": receipt}


def build_failure_receipt(
    *,
    status: str,
    failure_stage: str,
    failure_category: str,
    bucket: str | None,
    endpoint_host: str | None,
    plan_commitment: str | None,
    github_provenance: Mapping[str, Any],
    execution_provenance: Mapping[str, Any],
    observed_at: datetime,
    deadline_seconds: float,
    completed_rounds: Sequence[int] = (),
) -> dict[str, Any]:
    """Build the sole safe artifact for failures that have no live workers."""
    if status not in {"failed", "inconclusive"}:
        raise R2ConcurrencyError("R2 concurrency failure status is invalid")
    if (bucket is None) != (endpoint_host is None):
        raise R2ConcurrencyError("R2 concurrency failure scope is partially admitted")
    admitted = bucket is not None
    host = _require_endpoint_host(endpoint_host) if admitted else None
    bucket_hash = _hash_text(_require_bucket(bucket)) if admitted else None
    failure = {"stage": failure_stage, "category": failure_category}
    _validate_failure(failure)
    prefix = _completed_prefix(completed_rounds)
    commitment = plan_commitment if plan_commitment is not None else None
    if commitment is not None and _HEX64_RE.fullmatch(commitment) is None:
        raise R2ConcurrencyError("R2 concurrency plan commitment is invalid")
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": "",
        "status": status,
        "failure": failure,
        "manual_only": True,
        "created_at": _iso_timestamp(observed_at),
        "deadline_seconds": _deadline_seconds(deadline_seconds),
        "round_count": ROUND_COUNT,
        "plan_commitment_sha256": commitment,
        "scope": {
            "admitted": admitted,
            "endpoint_host": host,
            "bucket_sha256": bucket_hash,
        },
        "github_provenance": _normalize_github_provenance(github_provenance),
        "execution_provenance": _normalize_execution_provenance(execution_provenance),
        "worker_topology": None,
        "rounds": {"completed_rounds": prefix},
        "output_authority": dict(_NO_AUTHORITY),
        "nonclaims": dict(_NONCLAIMS),
    }
    receipt["receipt_id"] = _receipt_id(receipt)
    validate_concurrency_receipt(receipt)
    return receipt


def failure_receipt_evidence(error: BaseException) -> dict[str, Any]:
    """Return only closed failure evidence; no raw SDK diagnostic escapes."""
    if isinstance(error, R2ConcurrencyObservedFailure):
        return {
            "status": error.status,
            "failure_stage": error.failure_stage,
            "failure_category": error.failure_category,
            "completed_rounds": error.completed_rounds,
        }
    return {
        "status": "inconclusive",
        "failure_stage": "probe",
        "failure_category": "transport_or_deadline",
        "completed_rounds": (),
    }


def canonical_receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    validate_concurrency_receipt(receipt)
    return _canonical_json(dict(receipt)) + b"\n"


def validate_concurrency_receipt(receipt: Mapping[str, Any]) -> None:
    fields = {
        "schema", "receipt_id", "status", "failure", "manual_only", "created_at",
        "deadline_seconds", "round_count", "plan_commitment_sha256", "scope",
        "github_provenance", "execution_provenance", "worker_topology", "rounds", "output_authority", "nonclaims",
    }
    if not isinstance(receipt, Mapping) or set(receipt) != fields:
        raise R2ConcurrencyError("R2 concurrency receipt is not closed")
    if (
        receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("status") not in {"passed", "failed", "inconclusive"}
        or receipt.get("manual_only") is not True
        or receipt.get("round_count") != ROUND_COUNT
    ):
        raise R2ConcurrencyError("R2 concurrency receipt identity/status is invalid")
    _iso_timestamp_value(receipt.get("created_at"), label="receipt created_at")
    _deadline_seconds(receipt.get("deadline_seconds"))
    scope = _validate_scope(receipt.get("scope"))
    _normalize_github_provenance(receipt.get("github_provenance"))
    _normalize_execution_provenance(receipt.get("execution_provenance"))
    if receipt.get("output_authority") != _NO_AUTHORITY or receipt.get("nonclaims") != _NONCLAIMS:
        raise R2ConcurrencyError("R2 concurrency receipt authority/nonclaims are invalid")
    commitment = receipt.get("plan_commitment_sha256")
    if commitment is not None and _HEX64_RE.fullmatch(commitment) is None:
        raise R2ConcurrencyError("R2 concurrency receipt plan commitment is invalid")
    if receipt["status"] == "passed":
        if scope["admitted"] is not True or receipt.get("failure") is not None:
            raise R2ConcurrencyError("passed R2 concurrency receipt is detached")
        if _HEX64_RE.fullmatch(commitment or "") is None:
            raise R2ConcurrencyError("passed R2 concurrency receipt lacks plan commitment")
        _validate_worker_topology(receipt.get("worker_topology"))
        _validate_passed_rounds(
            receipt.get("rounds"),
            plan_commitment=commitment,
        )
    else:
        _validate_failure(receipt.get("failure"))
        if receipt.get("worker_topology") is not None:
            raise R2ConcurrencyError("R2 concurrency failure receipt topology is invalid")
        if not isinstance(receipt.get("rounds"), Mapping) or set(receipt["rounds"]) != {"completed_rounds"}:
            raise R2ConcurrencyError("R2 concurrency failure rounds are invalid")
        _completed_prefix(receipt["rounds"]["completed_rounds"])
    if receipt.get("receipt_id") != _receipt_id(dict(receipt)):
        raise R2ConcurrencyError("R2 concurrency receipt identity is detached")


def _candidate_body(run_nonce: str, round_id: int, phase: str, worker: str) -> bytes:
    return _canonical_json(
        {
            "candidate": worker,
            "phase": phase,
            "round": round_id,
            "run_nonce": run_nonce,
            "schema": "capital_structure.share_count_r2_concurrency_payload/v1",
        },
    ) + b"\n"


def _validate_plan(rounds: Sequence[RoundPlan]) -> tuple[RoundPlan, ...]:
    if not isinstance(rounds, Sequence) or len(rounds) != ROUND_COUNT:
        raise R2ConcurrencyError("R2 concurrency plan must contain exactly eight rounds")
    normalized: list[RoundPlan] = []
    keys: set[str] = set()
    plan_nonce: str | None = None
    for expected_round, item in enumerate(rounds, start=1):
        if (
            not isinstance(item, RoundPlan)
            or item.round_id != expected_round
            or re.fullmatch(r"[a-f0-9]{32}", item.run_nonce or "") is None
        ):
            raise R2ConcurrencyError("R2 concurrency plan round identity is invalid")
        if plan_nonce is None:
            plan_nonce = item.run_nonce
        if item.run_nonce != plan_nonce or item.key != f"{CONCURRENCY_KEY_PREFIX}{item.run_nonce}/round-{item.round_id}.json":
            raise R2ConcurrencyError("R2 concurrency plan nonce/key binding is invalid")
        if _KEY_RE.fullmatch(item.key) is None or item.key in keys:
            raise R2ConcurrencyError("R2 concurrency plan key is invalid")
        keys.add(item.key)
        bodies = (item.genesis_left, item.genesis_right, item.successor_left, item.successor_right)
        if len(set(bodies)) != 4:
            raise R2ConcurrencyError("R2 concurrency candidate bodies must be unique")
        expected_slots = (
            (item.genesis_left, "genesis", "left"),
            (item.genesis_right, "genesis", "right"),
            (item.successor_left, "successor", "left"),
            (item.successor_right, "successor", "right"),
        )
        for body, phase, worker in expected_slots:
            if not isinstance(body, bytes) or not 1 <= len(body) <= MAX_OBJECT_BYTES:
                raise R2ConcurrencyError("R2 concurrency candidate body is invalid")
            parsed = _parse_canonical_body(body)
            expected = {
                "candidate": worker,
                "phase": phase,
                "round": item.round_id,
                "run_nonce": item.run_nonce,
                "schema": "capital_structure.share_count_r2_concurrency_payload/v1",
            }
            if parsed != expected:
                raise R2ConcurrencyError("R2 concurrency candidate body slot binding is invalid")
        normalized.append(item)
    return tuple(normalized)


def _validate_worker_identities(workers: PersistentRaceWorkers) -> tuple[WorkerIdentity, WorkerIdentity]:
    try:
        identities = workers.identities
    except Exception as exc:  # noqa: BLE001
        raise R2ConcurrencyError("R2 concurrency worker identities are unavailable") from exc
    if not isinstance(identities, tuple) or len(identities) != 2:
        raise R2ConcurrencyError("R2 concurrency worker identity count is invalid")
    expected_ids = {"left", "right"}
    pids: set[int] = set()
    sessions: set[str] = set()
    clients: set[str] = set()
    for identity in identities:
        if (
            not isinstance(identity, WorkerIdentity)
            or identity.worker_id not in expected_ids
            or isinstance(identity.process_id, bool)
            or not isinstance(identity.process_id, int)
            or identity.process_id <= 0
            or _HEX64_RE.fullmatch(identity.session_instance_sha256) is None
            or _HEX64_RE.fullmatch(identity.client_instance_sha256) is None
            or identity.retry_mode != "standard"
            or isinstance(identity.total_max_attempts, bool)
            or identity.total_max_attempts != 1
            or identity.before_send_hook_installed is not True
            or identity.needs_retry_hook_installed is not True
        ):
            raise R2ConcurrencyError("R2 concurrency worker identity is invalid")
        pids.add(identity.process_id)
        sessions.add(identity.session_instance_sha256)
        clients.add(identity.client_instance_sha256)
    if {item.worker_id for item in identities} != expected_ids or len(pids) != 2 or len(sessions) != 2 or len(clients) != 2:
        raise R2ConcurrencyError("R2 concurrency workers are not independent persistent processes")
    return identities


def _worker_topology_receipt(_identities: tuple[WorkerIdentity, WorkerIdentity]) -> dict[str, Any]:
    return {
        "persistent_children": True,
        "independent_processes": True,
        "independent_sessions": True,
        "independent_clients": True,
        "retry_mode": "standard",
        "total_max_attempts": 1,
        "needs_retry_hook_installed": True,
    }


def _validate_worker_topology(value: Any) -> None:
    expected = {
        "persistent_children": True,
        "independent_processes": True,
        "independent_sessions": True,
        "independent_clients": True,
        "retry_mode": "standard",
        "total_max_attempts": 1,
        "needs_retry_hook_installed": True,
    }
    if value != expected:
        raise R2ConcurrencyError("R2 concurrency receipt worker topology is invalid")


def _verify_race(
    *,
    stage: str,
    attempts: Any,
    identities: tuple[WorkerIdentity, WorkerIdentity],
    left_body: bytes,
    right_body: bytes,
    completed_rounds: tuple[int, ...],
) -> dict[str, Any]:
    if not isinstance(attempts, tuple) or len(attempts) != 2 or not all(isinstance(item, WorkerAttempt) for item in attempts):
        _raise_observed(stage, "worker_result_shape", completed_rounds)
    expected_pids = {item.worker_id: item.process_id for item in identities}
    by_id = {item.worker_id: item for item in attempts}
    if set(by_id) != {"left", "right"}:
        _raise_observed(stage, "worker_result_shape", completed_rounds)
    for worker_id, attempt in by_id.items():
        if (
            attempt.process_id != expected_pids[worker_id]
            or isinstance(attempt.issued_puts, bool)
            or attempt.issued_puts != 1
            or isinstance(attempt.before_send_count, bool)
            or attempt.before_send_count != 1
            or attempt.needs_retry_attempts != (1,)
            or not isinstance(attempt.transport_started_ns, int)
            or not isinstance(attempt.completed_ns, int)
            or isinstance(attempt.transport_started_ns, bool)
            or isinstance(attempt.completed_ns, bool)
            or attempt.transport_started_ns <= 0
            or attempt.completed_ns < attempt.transport_started_ns
            or (attempt.request_id_sha256 is not None and _HEX64_RE.fullmatch(attempt.request_id_sha256) is None)
            or not _consistent_worker_attempt(attempt)
        ):
            _raise_observed(stage, "missing_or_duplicate_attempt_evidence", completed_rounds)
    if max(item.transport_started_ns for item in attempts) >= min(item.completed_ns for item in attempts):
        _raise_observed(stage, "sequential_transport_spans", completed_rounds)
    successes = [item for item in attempts if _is_exact_put_success(item)]
    exact_conflicts = [item for item in attempts if _is_exact_412(item)]
    if len(successes) == 2:
        _raise_observed(stage, "both_writers_succeeded", completed_rounds, status="failed")
    if len(successes) != 1 or len(exact_conflicts) != 1:
        if any(item.outcome == "transport" for item in attempts):
            _raise_observed(stage, "lost_or_ambiguous_response", completed_rounds)
        _raise_observed(stage, "wrong_conflict_response", completed_rounds)
    winner = successes[0]
    loser = exact_conflicts[0]
    winner_body = left_body if winner.worker_id == "left" else right_body
    loser_body = left_body if loser.worker_id == "left" else right_body
    return {
        "winner_worker": winner.worker_id,
        "winner_body": winner_body,
        "loser_body": loser_body,
        "winner_attempt": winner,
        "loser_attempt": loser,
        "attempts": by_id,
    }


def _expect_typed_absence(
    *,
    deadline: _Deadline,
    verifier: R2VerifierClient,
    bucket: str,
    key: str,
) -> None:
    try:
        deadline.call("typed absence HEAD", verifier.head_object, Bucket=bucket, Key=key)
    except Exception as exc:  # noqa: BLE001
        code, status = _error_identity(exc)
        if (
            isinstance(exc, ClientError)
            and code in {"404", "NotFound", "NoSuchKey"}
            and status == 404
            and _error_retry_attempts(exc) == 0
        ):
            return
        raise R2ConcurrencyError("R2 concurrency absence preflight is not exact typed 404") from exc
    raise R2ConcurrencyError("R2 concurrency fresh-key absence preflight unexpectedly succeeded")


def _verify_exact_object(
    *,
    deadline: _Deadline,
    verifier: R2VerifierClient,
    bucket: str,
    key: str,
    expected_body: bytes,
    label: str,
) -> _Head:
    try:
        response = deadline.call(f"{label} HEAD", verifier.head_object, Bucket=bucket, Key=key)
    except Exception as exc:  # noqa: BLE001
        raise R2ConcurrencyError("R2 concurrency verifier HEAD failed") from exc
    expected_sha256 = _hash_bytes(expected_body)
    head = _parse_head(response, expected_sha256=expected_sha256)
    if head.content_length != len(expected_body) or head.content_type != "application/json":
        raise R2ConcurrencyError("R2 concurrency verifier HEAD metadata mismatched winner")
    try:
        response = deadline.call(
            f"{label} ranged GET",
            verifier.get_object,
            Bucket=bucket,
            Key=key,
            Range=f"bytes=0-{len(expected_body) - 1}",
            IfMatch=head.etag,
        )
    except Exception as exc:  # noqa: BLE001
        raise R2ConcurrencyError("R2 concurrency verifier ranged GET failed") from exc
    _parse_exact_get(
        deadline=deadline,
        response=response,
        head=head,
        expected_body=expected_body,
        expected_sha256=expected_sha256,
        label=label,
    )
    return head


def _expect_typed_412(
    *,
    deadline: _Deadline,
    call: Callable[[], Any],
    label: str,
    completed_rounds: Sequence[int],
) -> None:
    try:
        deadline.check(f"before {label}")
        call()
    except Exception as exc:  # noqa: BLE001
        deadline.check(f"after {label}")
        code, status = _error_identity(exc)
        if (
            _is_exact_client_error(exc)
            and code == "PreconditionFailed"
            and status == 412
            and _error_retry_attempts(exc) == 0
        ):
            return
        _raise_observed("stale_put", "wrong_conflict_response", completed_rounds)
    deadline.check(f"after {label}")
    _raise_observed("stale_put", "stale_write_succeeded", completed_rounds, status="failed")


def _parse_head(response: Any, *, expected_sha256: str) -> _Head:
    if not isinstance(response, Mapping) or _response_status(response) != 200:
        raise R2ConcurrencyError("R2 concurrency verifier HEAD response is invalid")
    length, content_type, etag = response.get("ContentLength"), response.get("ContentType"), response.get("ETag")
    metadata = response.get("Metadata")
    if (
        isinstance(length, bool)
        or not isinstance(length, int)
        or not 1 <= length <= MAX_OBJECT_BYTES
        or content_type != "application/json"
        or not _opaque_etag(etag)
        or not isinstance(metadata, Mapping)
        or dict(metadata) != {"sha256": expected_sha256}
    ):
        raise R2ConcurrencyError("R2 concurrency verifier HEAD metadata is invalid")
    return _Head(etag=etag, content_length=length, content_type=content_type)


def _parse_exact_get(
    *,
    deadline: _Deadline,
    response: Any,
    head: _Head,
    expected_body: bytes,
    expected_sha256: str,
    label: str,
) -> None:
    stream = response.get("Body") if isinstance(response, Mapping) else None
    try:
        if (
            not isinstance(response, Mapping)
            or _response_status(response) != 206
            or response.get("ContentLength") != head.content_length
            or response.get("ContentType") != head.content_type
            or response.get("ETag") != head.etag
            or response.get("ContentRange") != f"bytes 0-{head.content_length - 1}/{head.content_length}"
            or not isinstance(response.get("Metadata"), Mapping)
            or dict(response["Metadata"]) != {"sha256": expected_sha256}
        ):
            raise R2ConcurrencyError("R2 concurrency verifier ranged GET metadata is invalid")
        if not callable(getattr(stream, "read", None)) or not callable(getattr(stream, "close", None)):
            raise R2ConcurrencyError("R2 concurrency verifier ranged GET body is invalid")
        body = bytearray()
        while len(body) <= head.content_length:
            chunk = deadline.call(
                f"{label} body read",
                lambda: stream.read(min(1024, head.content_length + 1 - len(body))),
            )
            if not isinstance(chunk, bytes):
                raise R2ConcurrencyError("R2 concurrency verifier body chunk is invalid")
            if not chunk:
                break
            body.extend(chunk)
        if bytes(body) != expected_body:
            raise R2ConcurrencyError("R2 concurrency verifier body differs from winner")
    finally:
        try:
            if callable(getattr(stream, "close", None)):
                _close_owned_stream(deadline=deadline, label=f"{label} body", stream=stream)
        except R2ConcurrencyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise R2ConcurrencyError("R2 concurrency verifier body close failed") from exc


def _close_owned_stream(*, deadline: _Deadline, label: str, stream: Any) -> None:
    """Close a returned body even if the logical deadline has just elapsed."""
    deadline_error: R2ConcurrencyError | None = None
    try:
        deadline.check(f"before {label} close")
    except R2ConcurrencyError as exc:
        deadline_error = exc
    try:
        stream.close()
    except Exception as exc:  # noqa: BLE001
        raise R2ConcurrencyError("R2 concurrency verifier body close failed") from exc
    if deadline_error is not None:
        raise deadline_error
    deadline.check(f"after {label} close")


def _successor_commitment(*, round_plan: RoundPlan, e0_etag: str) -> str:
    return _hash_bytes(
        _canonical_json(
            {
                "protocol": PROTOCOL_ID,
                "round": round_plan.round_id,
                "e0_etag_sha256": _hash_text(e0_etag),
                "successor_candidate_sha256": [
                    _hash_bytes(round_plan.successor_left),
                    _hash_bytes(round_plan.successor_right),
                ],
            },
        ),
    )


def _round_receipt(
    *,
    round_plan: RoundPlan,
    genesis: Mapping[str, Any],
    e0: _Head,
    successor: Mapping[str, Any],
    successor_commitment: str,
    e1: _Head,
    final: _Head,
    stale_attempt: VerifierPutAttempt,
) -> dict[str, Any]:
    return {
        "round": round_plan.round_id,
        "key_sha256": _hash_text(round_plan.key),
        "genesis": {
            "absence_preflight_exact_typed_404": True,
            "transport_interval_overlap": True,
            "success_count": 1,
            "typed_412_precondition_failed_count": 1,
            "winner_candidate_sha256": _hash_bytes(genesis["winner_body"]),
            "loser_candidate_sha256": _hash_bytes(genesis["loser_body"]),
            "winner_etag_sha256": _hash_text(e0.etag),
            "verified_body_sha256": _hash_bytes(genesis["winner_body"]),
            "worker_attempts": _attempt_receipts(genesis["attempts"]),
        },
        "successor": {
            "commitment_sha256": successor_commitment,
            "transport_interval_overlap": True,
            "success_count": 1,
            "typed_412_precondition_failed_count": 1,
            "winner_candidate_sha256": _hash_bytes(successor["winner_body"]),
            "loser_candidate_sha256": _hash_bytes(successor["loser_body"]),
            "e0_etag_sha256": _hash_text(e0.etag),
            "winner_etag_sha256": _hash_text(e1.etag),
            "verified_body_sha256": _hash_bytes(successor["winner_body"]),
            "etag_changed_from_e0": True,
            "worker_attempts": _attempt_receipts(successor["attempts"]),
        },
        "stale": {
            "http_status": 412,
            "error_code": "PreconditionFailed",
            "final_etag_sha256": _hash_text(final.etag),
            "final_body_sha256": _hash_bytes(successor["winner_body"]),
            "final_unchanged": True,
            "issued_puts": 1,
            "before_send_count": 1,
            "needs_retry_attempts": [1],
            "response_retry_attempts": 0,
            "request_id_sha256": stale_attempt.request_id_sha256,
        },
    }


def _attempt_receipts(attempts: Mapping[str, WorkerAttempt]) -> dict[str, Any]:
    if set(attempts) != {"left", "right"}:
        raise R2ConcurrencyError("R2 concurrency writer evidence is invalid")
    origin = min(item.transport_started_ns for item in attempts.values())
    return {
        worker_id: {
            "issued_puts": attempt.issued_puts,
            "before_send_count": attempt.before_send_count,
            "needs_retry_attempts": list(attempt.needs_retry_attempts),
            "response_retry_attempts": attempt.retry_attempts,
            "outcome": attempt.outcome,
            "http_status": attempt.http_status,
            "error_code": attempt.error_code,
            "error_status": attempt.error_status,
            "exact_client_error": attempt.exact_client_error,
            "transport_start_offset_ns": attempt.transport_started_ns - origin,
            "completed_offset_ns": attempt.completed_ns - origin,
            "request_id_sha256": attempt.request_id_sha256,
        }
        for worker_id, attempt in attempts.items()
    }


def _validate_passed_rounds(value: Any, *, plan_commitment: str) -> None:
    if not isinstance(value, list) or len(value) != ROUND_COUNT:
        raise R2ConcurrencyError("passed R2 concurrency receipt has invalid rounds")
    expected_rounds = list(range(1, ROUND_COUNT + 1))
    if [item.get("round") if isinstance(item, Mapping) else None for item in value] != expected_rounds:
        raise R2ConcurrencyError("passed R2 concurrency receipt rounds are not complete")
    key_hashes: set[str] = set()
    committed_rounds: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"round", "key_sha256", "genesis", "successor", "stale"}:
            raise R2ConcurrencyError("passed R2 concurrency receipt round is not closed")
        if _HEX64_RE.fullmatch(item["key_sha256"]) is None or item["key_sha256"] in key_hashes:
            raise R2ConcurrencyError("passed R2 concurrency receipt key hash is invalid")
        key_hashes.add(item["key_sha256"])
        _validate_phase(item["genesis"], successor=False)
        _validate_phase(item["successor"], successor=True)
        genesis = item["genesis"]
        successor = item["successor"]
        genesis_candidates = _ordered_candidate_hashes(genesis)
        successor_candidates = _ordered_candidate_hashes(successor)
        if (
            genesis["winner_candidate_sha256"] == genesis["loser_candidate_sha256"]
            or successor["winner_candidate_sha256"] == successor["loser_candidate_sha256"]
            or len(
                {
                    genesis["winner_candidate_sha256"],
                    genesis["loser_candidate_sha256"],
                    successor["winner_candidate_sha256"],
                    successor["loser_candidate_sha256"],
                },
            ) != 4
            or genesis["verified_body_sha256"] != genesis["winner_candidate_sha256"]
            or successor["verified_body_sha256"] != successor["winner_candidate_sha256"]
            or successor["e0_etag_sha256"] != genesis["winner_etag_sha256"]
            or successor["winner_etag_sha256"] == successor["e0_etag_sha256"]
        ):
            raise R2ConcurrencyError("passed R2 concurrency round evidence is detached")
        expected_successor_commitment = _hash_bytes(
            _canonical_json(
                {
                    "protocol": PROTOCOL_ID,
                    "round": item["round"],
                    "e0_etag_sha256": successor["e0_etag_sha256"],
                    "successor_candidate_sha256": successor_candidates,
                },
            ),
        )
        if successor["commitment_sha256"] != expected_successor_commitment:
            raise R2ConcurrencyError("passed R2 concurrency successor commitment is detached")
        stale = item["stale"]
        if (
            not isinstance(stale, Mapping)
            or set(stale) != {"http_status", "error_code", "final_etag_sha256", "final_body_sha256", "final_unchanged", "issued_puts", "before_send_count", "needs_retry_attempts", "response_retry_attempts", "request_id_sha256"}
            or stale["http_status"] != 412
            or stale["error_code"] != "PreconditionFailed"
            or stale["final_unchanged"] is not True
            or isinstance(stale["issued_puts"], bool)
            or stale["issued_puts"] != 1
            or isinstance(stale["before_send_count"], bool)
            or stale["before_send_count"] != 1
            or stale["needs_retry_attempts"] != [1]
            or isinstance(stale["response_retry_attempts"], bool)
            or stale["response_retry_attempts"] != 0
            or (stale["request_id_sha256"] is not None and _HEX64_RE.fullmatch(stale["request_id_sha256"]) is None)
            or any(_HEX64_RE.fullmatch(stale[name]) is None for name in ("final_etag_sha256", "final_body_sha256"))
        ):
            raise R2ConcurrencyError("passed R2 concurrency stale evidence is invalid")
        if (
            stale["final_etag_sha256"] != successor["winner_etag_sha256"]
            or stale["final_body_sha256"] != successor["winner_candidate_sha256"]
        ):
            raise R2ConcurrencyError("passed R2 concurrency stale evidence is detached")
        committed_rounds.append(
            {
                "round": item["round"],
                "key_sha256": item["key_sha256"],
                "genesis_candidate_sha256": genesis_candidates,
                "successor_candidate_sha256": successor_candidates,
            },
        )
    expected_plan_commitment = _hash_bytes(
        _canonical_json(
            {
                "protocol": PROTOCOL_ID,
                "round_count": ROUND_COUNT,
                "rounds": committed_rounds,
            },
        ),
    )
    if plan_commitment != expected_plan_commitment:
        raise R2ConcurrencyError("passed R2 concurrency plan commitment is detached")


def _ordered_candidate_hashes(value: Mapping[str, Any]) -> list[str]:
    attempts = value["worker_attempts"]
    if attempts["left"]["outcome"] == "success":
        return [value["winner_candidate_sha256"], value["loser_candidate_sha256"]]
    return [value["loser_candidate_sha256"], value["winner_candidate_sha256"]]


def _validate_phase(value: Any, *, successor: bool) -> None:
    fields = {
        "transport_interval_overlap", "success_count", "typed_412_precondition_failed_count",
        "winner_candidate_sha256", "loser_candidate_sha256", "winner_etag_sha256", "verified_body_sha256", "worker_attempts",
    }
    if successor:
        fields |= {"commitment_sha256", "e0_etag_sha256", "etag_changed_from_e0"}
    else:
        fields |= {"absence_preflight_exact_typed_404"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise R2ConcurrencyError("passed R2 concurrency phase evidence is not closed")
    if (
        value["transport_interval_overlap"] is not True
        or value["success_count"] != 1
        or value["typed_412_precondition_failed_count"] != 1
    ):
        raise R2ConcurrencyError("passed R2 concurrency race evidence is invalid")
    if successor and value["etag_changed_from_e0"] is not True:
        raise R2ConcurrencyError("passed R2 concurrency successor ETag evidence is invalid")
    if not successor and value["absence_preflight_exact_typed_404"] is not True:
        raise R2ConcurrencyError("passed R2 concurrency absence evidence is invalid")
    hash_fields = {"winner_candidate_sha256", "loser_candidate_sha256", "winner_etag_sha256", "verified_body_sha256"}
    if successor:
        hash_fields |= {"commitment_sha256", "e0_etag_sha256"}
    if any(_HEX64_RE.fullmatch(value[name]) is None for name in hash_fields):
        raise R2ConcurrencyError("passed R2 concurrency phase hashes are invalid")
    _validate_attempt_receipts(value["worker_attempts"])


def _validate_attempt_receipts(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {"left", "right"}:
        raise R2ConcurrencyError("passed R2 concurrency writer evidence is invalid")
    fields = {
        "issued_puts", "before_send_count", "needs_retry_attempts",
        "response_retry_attempts", "outcome", "http_status", "error_code",
        "error_status", "exact_client_error", "transport_start_offset_ns",
        "completed_offset_ns", "request_id_sha256",
    }
    starts: list[int] = []
    completes: list[int] = []
    successes = 0
    conflicts = 0
    for item in value.values():
        if (
            not isinstance(item, Mapping)
            or set(item) != fields
            or isinstance(item.get("issued_puts"), bool)
            or item.get("issued_puts") != 1
            or isinstance(item.get("before_send_count"), bool)
            or item.get("before_send_count") != 1
            or item.get("needs_retry_attempts") != [1]
            or isinstance(item.get("response_retry_attempts"), bool)
            or item.get("response_retry_attempts") != 0
            or item.get("outcome") not in {"success", "conflict"}
            or isinstance(item.get("transport_start_offset_ns"), bool)
            or not isinstance(item.get("transport_start_offset_ns"), int)
            or isinstance(item.get("completed_offset_ns"), bool)
            or not isinstance(item.get("completed_offset_ns"), int)
            or item["transport_start_offset_ns"] < 0
            or item["completed_offset_ns"] < item["transport_start_offset_ns"]
            or (item.get("request_id_sha256") is not None and _HEX64_RE.fullmatch(item["request_id_sha256"]) is None)
        ):
            raise R2ConcurrencyError("passed R2 concurrency writer evidence is invalid")
        if item["outcome"] == "success":
            if (
                item["http_status"] != 200
                or item["error_code"] is not None
                or item["error_status"] is not None
                or item["exact_client_error"] is not False
            ):
                raise R2ConcurrencyError("passed R2 concurrency writer success evidence is invalid")
            successes += 1
        else:
            if (
                item["http_status"] is not None
                or item["error_code"] != "PreconditionFailed"
                or item["error_status"] != 412
                or item["exact_client_error"] is not True
            ):
                raise R2ConcurrencyError("passed R2 concurrency writer conflict evidence is invalid")
            conflicts += 1
        starts.append(item["transport_start_offset_ns"])
        completes.append(item["completed_offset_ns"])
    if min(starts) != 0 or max(starts) >= min(completes) or successes != 1 or conflicts != 1:
        raise R2ConcurrencyError("passed R2 concurrency writer overlap evidence is invalid")


def _validate_failure(value: Any) -> None:
    stages = {"setup", "absence_preflight", "genesis_race", "genesis_verify", "successor_race", "successor_verify", "stale_put", "stale_verify", "probe", "receipt"}
    categories = {"configuration", "transport_or_deadline", "malformed_response", "readback_mismatch", "close_failure", "missing_or_duplicate_attempt_evidence", "sequential_transport_spans", "both_writers_succeeded", "lost_or_ambiguous_response", "wrong_conflict_response", "etag_not_new", "stale_write_succeeded", "post_hoc_rewrite", "worker_result_shape"}
    if not isinstance(value, Mapping) or set(value) != {"stage", "category"} or value.get("stage") not in stages or value.get("category") not in categories:
        raise R2ConcurrencyError("R2 concurrency failure evidence is invalid")


def _validate_scope(value: Any) -> dict[str, Any]:
    fields = {"admitted", "endpoint_host", "bucket_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields or not isinstance(value.get("admitted"), bool):
        raise R2ConcurrencyError("R2 concurrency receipt scope is invalid")
    admitted = value["admitted"]
    host, bucket_hash = value.get("endpoint_host"), value.get("bucket_sha256")
    if admitted:
        if _HOST_RE.fullmatch(host or "") is None or _HEX64_RE.fullmatch(bucket_hash or "") is None:
            raise R2ConcurrencyError("R2 concurrency admitted receipt scope is invalid")
    elif host is not None or bucket_hash is not None:
        raise R2ConcurrencyError("R2 concurrency unadmitted receipt scope is invalid")
    return dict(value)


def _normalize_github_provenance(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"repository", "workflow_ref", "run_id", "run_attempt", "commit_sha", "event_name", "actor"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise R2ConcurrencyError("R2 concurrency GitHub provenance is invalid")
    normalized = dict(value)
    if (
        normalized["repository"] != _EXPECTED_REPOSITORY
        or normalized["workflow_ref"] != f"{_EXPECTED_REPOSITORY}/.github/workflows/{_WORKFLOW_NAME}@refs/heads/main"
        or not isinstance(normalized["run_id"], str)
        or _RUN_RE.fullmatch(normalized["run_id"]) is None
        or not isinstance(normalized["run_attempt"], int)
        or not 1 <= normalized["run_attempt"] <= 1000
        or not isinstance(normalized["commit_sha"], str)
        or _SHA_RE.fullmatch(normalized["commit_sha"]) is None
        or normalized["event_name"] != "workflow_dispatch"
        or not isinstance(normalized["actor"], str)
        or _ACTOR_RE.fullmatch(normalized["actor"]) is None
    ):
        raise R2ConcurrencyError("R2 concurrency GitHub provenance is invalid")
    return normalized


def _normalize_execution_provenance(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"source_archive_sha256", "dependency_lock_sha256", "dependency_lock_name"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise R2ConcurrencyError("R2 concurrency execution provenance is invalid")
    normalized = dict(value)
    if (
        _HEX64_RE.fullmatch(normalized.get("source_archive_sha256", "")) is None
        or _HEX64_RE.fullmatch(normalized.get("dependency_lock_sha256", "")) is None
        or normalized.get("dependency_lock_name") != DEPENDENCY_LOCK_NAME
    ):
        raise R2ConcurrencyError("R2 concurrency execution provenance is invalid")
    return normalized


def _completed_prefix(value: Sequence[int]) -> list[int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise R2ConcurrencyError("R2 concurrency completed-round prefix is invalid")
    normalized = list(value)
    if normalized != list(range(1, len(normalized) + 1)) or len(normalized) > ROUND_COUNT:
        raise R2ConcurrencyError("R2 concurrency completed-round prefix is invalid")
    return normalized


def _require_verifier(verifier: Any) -> None:
    if not all(
        callable(getattr(verifier, name, None))
        for name in (
            "head_object", "get_object", "put_object", "reset_put_attempt_evidence",
            "take_put_attempt_evidence",
        )
    ):
        raise R2ConcurrencyError("R2 concurrency verifier capability is invalid")


def _require_bucket(bucket: Any) -> str:
    if not isinstance(bucket, str) or _BUCKET_RE.fullmatch(bucket) is None or ".." in bucket:
        raise R2ConcurrencyError("R2 concurrency bucket is invalid")
    return bucket


def _require_endpoint_host(host: Any) -> str:
    if not isinstance(host, str) or _HOST_RE.fullmatch(host) is None:
        raise R2ConcurrencyError("R2 concurrency endpoint host is invalid")
    return host


def _deadline_seconds(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < float(value) <= MAX_DEADLINE_SECONDS:
        raise R2ConcurrencyError("R2 concurrency deadline is invalid")
    return float(value)


def _response_status(response: Mapping[str, Any]) -> int | None:
    metadata = response.get("ResponseMetadata")
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, Mapping) else None
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _error_identity(error: BaseException) -> tuple[str | None, int | None]:
    response = getattr(error, "response", None)
    details = response.get("Error") if isinstance(response, Mapping) else None
    metadata = response.get("ResponseMetadata") if isinstance(response, Mapping) else None
    code = details.get("Code") if isinstance(details, Mapping) else None
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, Mapping) else None
    return (code if isinstance(code, str) else None, status if isinstance(status, int) and not isinstance(status, bool) else None)


def _error_retry_attempts(error: BaseException) -> int | None:
    response = getattr(error, "response", None)
    metadata = response.get("ResponseMetadata") if isinstance(response, Mapping) else None
    attempts = metadata.get("RetryAttempts") if isinstance(metadata, Mapping) else None
    return attempts if isinstance(attempts, int) and not isinstance(attempts, bool) else None


def _is_exact_client_error(error: BaseException) -> bool:
    return type(error) is ClientError


def _is_2xx(status: Any) -> bool:
    return isinstance(status, int) and not isinstance(status, bool) and 200 <= status < 300


def _is_exact_412(attempt: WorkerAttempt) -> bool:
    return (
        attempt.outcome == "conflict"
        and attempt.exact_client_error is True
        and attempt.error_code == "PreconditionFailed"
        and attempt.error_status == 412
        and attempt.retry_attempts == 0
    )


def _consistent_worker_attempt(attempt: WorkerAttempt) -> bool:
    if attempt.outcome == "success":
        return (
            attempt.error_code is None
            and attempt.error_status is None
            and attempt.exact_client_error is False
            and attempt.http_status == 200
            and attempt.retry_attempts == 0
        )
    if attempt.outcome == "conflict":
        return (
            attempt.http_status is None
            and isinstance(attempt.error_code, str)
            and isinstance(attempt.error_status, int)
            and not isinstance(attempt.error_status, bool)
            and attempt.exact_client_error is True
            and attempt.retry_attempts == 0
        )
    if attempt.outcome == "error":
        return (
            attempt.http_status is None
            and isinstance(attempt.error_code, str)
            and bool(attempt.error_code)
            and isinstance(attempt.error_status, int)
            and not isinstance(attempt.error_status, bool)
            and isinstance(attempt.exact_client_error, bool)
            and attempt.retry_attempts == 0
        )
    if attempt.outcome == "unknown":
        return (
            isinstance(attempt.http_status, int)
            and not isinstance(attempt.http_status, bool)
            and attempt.error_code is None
            and attempt.error_status is None
            and attempt.exact_client_error is False
            and attempt.retry_attempts == 0
        )
    if attempt.outcome == "transport":
        return (
            attempt.http_status is None
            and attempt.error_code is None
            and attempt.error_status is None
            and attempt.exact_client_error is False
            and attempt.retry_attempts is None
        )
    return False


def _validate_verifier_put_attempt(
    attempt: Any,
    *,
    completed_rounds: Sequence[int],
) -> None:
    if (
        not isinstance(attempt, VerifierPutAttempt)
        or isinstance(attempt.issued_puts, bool)
        or attempt.issued_puts != 1
        or isinstance(attempt.before_send_count, bool)
        or attempt.before_send_count != 1
        or attempt.needs_retry_attempts != (1,)
        or isinstance(attempt.retry_attempts, bool)
        or attempt.retry_attempts != 0
        or attempt.exact_client_error is not True
        or (attempt.request_id_sha256 is not None and _HEX64_RE.fullmatch(attempt.request_id_sha256) is None)
    ):
        _raise_observed("stale_put", "missing_or_duplicate_attempt_evidence", completed_rounds)


def _is_exact_put_success(attempt: WorkerAttempt) -> bool:
    return (
        attempt.outcome == "success"
        and attempt.http_status == 200
        and attempt.error_code is None
        and attempt.error_status is None
        and attempt.exact_client_error is False
        and attempt.retry_attempts == 0
    )


def _opaque_etag(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value.encode("utf-8")) <= 1024 and not any(ord(char) < 32 or ord(char) == 127 for char in value)


def _parse_canonical_body(body: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(body)
    except Exception as exc:  # noqa: BLE001
        raise R2ConcurrencyError("R2 concurrency candidate body is unreadable") from exc
    if not isinstance(parsed, Mapping) or _canonical_json(parsed) + b"\n" != body:
        raise R2ConcurrencyError("R2 concurrency candidate body is not canonical")
    return dict(parsed)


def _iso_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise R2ConcurrencyError("R2 concurrency timestamp is invalid")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _iso_timestamp_value(value: Any, *, label: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise R2ConcurrencyError(f"R2 concurrency {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise R2ConcurrencyError(f"R2 concurrency {label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or _iso_timestamp(parsed) != value:
        raise R2ConcurrencyError(f"R2 concurrency {label} is not canonical")


def _receipt_id(receipt: Mapping[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned["receipt_id"] = ""
    return RECEIPT_ID_PREFIX + _hash_bytes(_canonical_json(unsigned))


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise R2ConcurrencyError("R2 concurrency value is not canonical JSON") from exc


def _hash_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _hash_text(value: str) -> str:
    return _hash_bytes(value.encode("utf-8"))


def _run_stage(
    stage: str,
    completed_rounds: Sequence[int],
    call: Callable[[], Any],
) -> Any:
    try:
        return call()
    except R2ConcurrencyInFlight:
        raise
    except R2ConcurrencyObservedFailure:
        raise
    except R2ConcurrencyError as exc:
        _raise_observed(stage, _failure_category(exc), completed_rounds)
    except Exception:
        _raise_observed(stage, "transport_or_deadline", completed_rounds)


def _failure_category(error: R2ConcurrencyError) -> str:
    message = str(error).lower()
    if "close" in message:
        return "close_failure"
    if "differs" in message or "mismatched" in message or "detached" in message:
        return "readback_mismatch"
    if "metadata" in message or "body" in message or "response" in message:
        return "malformed_response"
    return "transport_or_deadline"


def _raise_observed(stage: str, category: str, completed_rounds: Sequence[int], *, status: str = "inconclusive") -> None:
    raise R2ConcurrencyObservedFailure(
        status=status,
        stage=stage,
        category=category,
        completed_rounds=tuple(_completed_prefix(completed_rounds)),
    )


__all__ = [
    "CONCURRENCY_KEY_PREFIX", "DEPENDENCY_LOCK_NAME", "MAX_DEADLINE_SECONDS", "MAX_OBJECT_BYTES",
    "PROTOCOL_ID", "ROUND_COUNT", "RECEIPT_SCHEMA", "PersistentRaceWorkers", "R2ConcurrencyError",
    "R2ConcurrencyInFlight", "R2ConcurrencyInconclusive", "R2ConcurrencyObservedFailure", "R2VerifierClient",
    "RoundPlan", "VerifierPutAttempt", "WorkerAttempt", "WorkerIdentity", "build_failure_receipt", "build_precommitted_plan",
    "canonical_receipt_bytes", "failure_receipt_evidence", "plan_commitment_sha256", "run_concurrency_witness",
    "validate_concurrency_receipt",
]
