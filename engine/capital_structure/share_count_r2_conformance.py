"""Manual-only, isolated Cloudflare R2 conditional-write conformance witness.

This module is intentionally a tiny capability boundary.  It accepts an
already-configured client whose only usable operations are ``head_object``,
``get_object``, and ``put_object``.  It neither discovers credentials nor
imports the production publication lane.  The one supplied key must be fresh
inside the disposable conformance namespace, and the witness never lists or
deletes objects.

Success is deliberately difficult: each conditional conflict must be an exact
typed 412 ``PreconditionFailed`` response and every successful read is an exact
bounded read-back.  A timeout, transport failure, malformed result, or
surprising status is inconclusive and cannot return a passing receipt.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
import time
from typing import Any, Callable, Mapping, Protocol


RECEIPT_SCHEMA = "capital_structure.share_count_r2_conformance_receipt/v1"
RECEIPT_ID_PREFIX = "r2-cas-conformance:cs-share-count-v1:"
CONFORMANCE_KEY_PREFIX = "capital_structure/share_counts/conformance/v1/"
CONFORMANCE_DEADLINE_SECONDS = 90.0
MAX_CONFORMANCE_OBJECT_BYTES = 4 * 1024

# The values are intentionally small, stable, and different lengths.  A
# successful stale conditional PUT of A would therefore be caught by the final
# exact read-back of B even if a broken transport falsely reported a conflict.
_BODY_A = (
    b'{"schema":"capital_structure.share_count_r2_conformance_payload/v1",'
    b'"phase":"A"}\n'
)
_BODY_B = (
    b'{"schema":"capital_structure.share_count_r2_conformance_payload/v1",'
    b'"phase":"B","revision":2}\n'
)
_KEY_RE = re.compile(
    r"^capital_structure/share_counts/conformance/v1/[a-f0-9]{32}\.json$",
)
_HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
_COMMIT_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
_RUN_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
_ACTOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_HOST_RE = re.compile(
    r"^[a-f0-9]{32}\.(?:(?:eu|fedramp)\.)?r2\.cloudflarestorage\.com$",
)
_EXPECTED_REPOSITORY = "chriswong6031-creator/macro"

_NO_AUTHORITY = {
    "is_context_only": True,
    "conformance_authority": False,
    "share_count_ledger_authority": False,
    "publication_authority": False,
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
    "not_a_provider_security_audit": True,
    "not_a_provider_durability_or_availability_proof": True,
    "not_a_credential_authentication_proof": True,
    "not_a_retention_or_deletion_proof": True,
    "not_a_concurrent_linearizability_proof": True,
    "not_a_production_retry_semantics_proof": True,
    "not_a_python_sandbox_or_credential_isolation_proof": True,
    "not_a_trading_or_investment_signal": True,
}


class R2CasConformanceError(RuntimeError):
    """The isolated R2 CAS witness cannot prove the required behavior."""


class R2CasConformanceInconclusive(R2CasConformanceError):
    """A transport/result ambiguity prevents a passing conformance receipt."""


class R2CasConformanceObservedFailure(R2CasConformanceInconclusive):
    """Closed, redaction-safe stage evidence for a non-passing probe."""

    def __init__(
        self,
        *,
        stage: str,
        category: str,
        completed_steps: tuple[str, ...],
    ) -> None:
        super().__init__(f"R2 CAS conformance stage failed: {stage}/{category}")
        self.failure_stage = stage
        self.failure_category = category
        self.completed_steps = completed_steps


class R2CasConformanceClient(Protocol):
    """The complete object-store capability needed by this witness.

    Production callers may pass an SDK client, but this witness must never use
    any method other than these three.  In particular, it cannot list, delete,
    or mutate a production selector.
    """

    def head_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def get_object(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def put_object(self, **kwargs: Any) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class _Deadline:
    deadline: float
    monotonic: Callable[[], float]

    def check(self, label: str) -> None:
        try:
            current = self.monotonic()
        except Exception as exc:  # noqa: BLE001
            raise R2CasConformanceInconclusive(
                f"R2 CAS conformance monotonic clock failed during {label}",
            ) from exc
        if isinstance(current, bool) or not isinstance(current, (int, float)) or not math.isfinite(current):
            raise R2CasConformanceInconclusive(
                f"R2 CAS conformance monotonic clock is invalid during {label}",
            )
        if current >= self.deadline:
            raise R2CasConformanceInconclusive(
                f"R2 CAS conformance deadline exceeded during {label}",
            )

    def call(self, label: str, call: Callable[..., Any], /, **kwargs: Any) -> Any:
        """Call an SDK method with the required pre- and post-call checks."""
        self.check(f"before {label}")
        try:
            result = call(**kwargs)
        except Exception as exc:
            try:
                self.check(f"after {label}")
            except Exception as check_exc:
                self._close_returned_body(getattr(exc, "response", None), label=label)
                if getattr(check_exc, "conformance_deadline_exceeded", False):
                    raise R2CasConformanceInconclusive(
                        f"R2 CAS conformance deadline exceeded after {label}",
                    ) from check_exc
                raise
            raise
        try:
            self.check(f"after {label}")
        except Exception as exc:
            # The caller never receives result on this path, so ownership of a
            # returned StreamingBody must be discharged here.
            self._close_returned_body(result, label=label)
            if getattr(exc, "conformance_deadline_exceeded", False):
                raise R2CasConformanceInconclusive(
                    f"R2 CAS conformance deadline exceeded after {label}",
                ) from exc
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
            raise R2CasConformanceInconclusive(
                f"R2 CAS conformance {label} body close failed after post-call deadline",
            ) from exc

    def read(self, label: str, stream: Any, size: int) -> Any:
        self.check(f"before {label} read")
        try:
            chunk = stream.read(size)
        except Exception:
            self.check(f"after {label} read")
            raise
        self.check(f"after {label} read")
        return chunk

    def close(self, label: str, stream: Any) -> None:
        deadline_error: R2CasConformanceError | None = None
        try:
            self.check(f"before {label} close")
        except Exception as exc:
            # Once GET returns, cleanup owns the stream. An elapsed deadline
            # still fails the witness, but it must not skip close().
            if isinstance(exc, R2CasConformanceError):
                deadline_error = exc
            elif getattr(exc, "conformance_deadline_exceeded", False):
                deadline_error = R2CasConformanceInconclusive(
                    f"R2 CAS conformance deadline exceeded before {label} close",
                )
                deadline_error.__cause__ = exc
            else:
                raise
        try:
            stream.close()
        except Exception:
            if deadline_error is None:
                self.check(f"after {label} close")
            raise
        if deadline_error is not None:
            raise deadline_error
        try:
            self.check(f"after {label} close")
        except Exception as exc:
            if getattr(exc, "conformance_deadline_exceeded", False):
                raise R2CasConformanceInconclusive(
                    f"R2 CAS conformance deadline exceeded after {label} close",
                ) from exc
            raise


def run_conformance(
    *,
    client: R2CasConformanceClient,
    bucket: str,
    key: str,
    endpoint_host: str,
    github_provenance: Mapping[str, Any],
    execution_provenance: Mapping[str, Any],
    observed_at: datetime,
    deadline_seconds: float = CONFORMANCE_DEADLINE_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Run the bounded manual R2 CAS witness and return a passed receipt.

    ``deadline_seconds`` may only shorten the fixed 90-second cap when an outer
    manual wrapper has already spent part of its own budget.  The core itself
    does not create clients, inspect environment variables, or write receipts.
    It raises :class:`R2CasConformanceError` for every non-proven outcome.
    """
    _require_client(client)
    _require_bucket(bucket)
    _require_conformance_key(key)
    host = _require_endpoint_host(endpoint_host)
    provenance = _normalize_github_provenance(github_provenance)
    execution = _normalize_execution_provenance(execution_provenance)
    created_at = _iso_timestamp(observed_at)
    seconds = _deadline_seconds(deadline_seconds)
    try:
        started = monotonic()
    except Exception as exc:  # noqa: BLE001
        raise R2CasConformanceInconclusive("R2 CAS conformance monotonic clock failed") from exc
    if isinstance(started, bool) or not isinstance(started, (int, float)) or not math.isfinite(started):
        raise R2CasConformanceInconclusive("R2 CAS conformance monotonic clock is invalid")
    deadline = _Deadline(deadline=float(started) + seconds, monotonic=monotonic)

    completed_steps: list[str] = []
    with _observed_stage("create_a", completed_steps):
        create_a = _put_success(
            deadline=deadline,
            client=client,
            bucket=bucket,
            key=key,
            body=_BODY_A,
            condition_name="IfNoneMatch",
            condition_value="*",
            label="IfNoneMatch create A",
        )
    with _observed_stage("head_a", completed_steps):
        head_a = _head(deadline=deadline, client=client, bucket=bucket, key=key, label="HEAD A")
        _assert_metadata(head_a, body=_BODY_A, label="HEAD A")
    with _observed_stage("get_a", completed_steps):
        get_a = _get_exact(
            deadline=deadline, client=client, bucket=bucket, key=key,
            etag=head_a.etag, body=_BODY_A, label="IfMatch ranged GET A",
        )

    with _observed_stage("duplicate_create", completed_steps):
        duplicate_create = _authoritative_conflict(
            deadline=deadline,
            call=lambda: client.put_object(
                Bucket=bucket, Key=key, Body=_BODY_B, ContentType="application/json",
                IfNoneMatch="*",
            ),
            label="duplicate IfNoneMatch create B",
        )
    with _observed_stage("head_a_after_duplicate", completed_steps):
        head_a_after_duplicate = _head(
            deadline=deadline, client=client, bucket=bucket, key=key,
            label="HEAD A after duplicate conflict",
        )
        _assert_same_metadata(head_a_after_duplicate, head_a, label="duplicate create preservation")
    with _observed_stage("get_a_after_duplicate", completed_steps):
        get_a_after_duplicate = _get_exact(
            deadline=deadline, client=client, bucket=bucket, key=key,
            etag=head_a.etag, body=_BODY_A, label="IfMatch ranged GET A after duplicate conflict",
        )

    with _observed_stage("update_b", completed_steps):
        update_b = _put_success(
            deadline=deadline,
            client=client,
            bucket=bucket,
            key=key,
            body=_BODY_B,
            condition_name="IfMatch",
            condition_value=head_a.etag,
            label="IfMatch update B",
        )
    with _observed_stage("head_b", completed_steps):
        head_b = _head(deadline=deadline, client=client, bucket=bucket, key=key, label="HEAD B")
        _assert_metadata(head_b, body=_BODY_B, label="HEAD B")
        if head_b.etag == head_a.etag:
            raise R2CasConformanceInconclusive(
                "R2 CAS conformance update B did not produce a new opaque ETag",
            )

    with _observed_stage("stale_get", completed_steps):
        stale_get = _authoritative_conflict(
            deadline=deadline,
            call=lambda: client.get_object(
                Bucket=bucket, Key=key, Range=f"bytes=0-{len(_BODY_B) - 1}", IfMatch=head_a.etag,
            ),
            label="stale IfMatch ranged GET",
        )
    with _observed_stage("stale_put", completed_steps):
        stale_put = _authoritative_conflict(
            deadline=deadline,
            call=lambda: client.put_object(
                Bucket=bucket, Key=key, Body=_BODY_A, ContentType="application/json",
                IfMatch=head_a.etag,
            ),
            label="stale IfMatch PUT",
        )
    with _observed_stage("get_b", completed_steps):
        get_b = _get_exact(
            deadline=deadline, client=client, bucket=bucket, key=key,
            etag=head_b.etag, body=_BODY_B, label="IfMatch ranged GET B",
        )

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": "",
        "status": "passed",
        "failure": None,
        "manual_only": True,
        "created_at": created_at,
        "deadline_seconds": seconds,
        "scope": {
            "admitted": True,
            "endpoint_host": host,
            "bucket_sha256": _hash_text(bucket),
            "key_sha256": _hash_text(key),
        },
        "github_provenance": provenance,
        "execution_provenance": execution,
        "steps": {
            "create_a": create_a,
            "head_a": _head_receipt(head_a),
            "get_a": get_a,
            "duplicate_create": duplicate_create,
            "head_a_after_duplicate": _head_receipt(head_a_after_duplicate),
            "get_a_after_duplicate": get_a_after_duplicate,
            "update_b": update_b,
            "head_b": _head_receipt(head_b),
            "stale_get": stale_get,
            "stale_put": stale_put,
            "get_b": get_b,
        },
        "output_authority": dict(_NO_AUTHORITY),
        "nonclaims": dict(_NONCLAIMS),
    }
    receipt["receipt_id"] = _receipt_id(receipt)
    validate_conformance_receipt(receipt)
    return {"status": "passed", "receipt": receipt}


@dataclass(frozen=True)
class _Head:
    content_length: int
    content_type: str
    etag: str


def canonical_receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    """Return the only serialized form accepted for a conformance receipt."""
    validate_conformance_receipt(receipt)
    return _canonical_json(dict(receipt)) + b"\n"


def validate_conformance_receipt(receipt: Mapping[str, Any]) -> None:
    """Validate the closed receipt shape without any publication dependency."""
    fields = {
        "schema", "receipt_id", "status", "failure", "manual_only", "created_at",
        "deadline_seconds", "scope", "github_provenance", "execution_provenance", "steps",
        "output_authority", "nonclaims",
    }
    if not isinstance(receipt, Mapping) or set(receipt) != fields:
        raise R2CasConformanceError("R2 CAS conformance receipt is not closed")
    if (
        receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("status") not in {"passed", "failed", "inconclusive"}
        or receipt.get("manual_only") is not True
    ):
        raise R2CasConformanceError("R2 CAS conformance receipt identity/status is invalid")
    _iso_timestamp_value(receipt.get("created_at"), label="receipt created_at")
    _deadline_seconds(receipt.get("deadline_seconds"))
    scope = _validate_receipt_scope(receipt.get("scope"))
    _normalize_github_provenance(receipt.get("github_provenance"))
    _normalize_execution_provenance(receipt.get("execution_provenance"))
    if receipt.get("output_authority") != _NO_AUTHORITY or receipt.get("nonclaims") != _NONCLAIMS:
        raise R2CasConformanceError("R2 CAS conformance receipt authority/nonclaims are invalid")
    if receipt["status"] == "passed":
        if scope["admitted"] is not True:
            raise R2CasConformanceError("passed R2 CAS conformance receipt has no admitted scope")
        if receipt.get("failure") is not None:
            raise R2CasConformanceError("passed R2 CAS conformance receipt has a failure")
        _validate_passed_steps(receipt.get("steps"))
    else:
        _validate_failure(receipt.get("failure"))
        _validate_partial_steps(receipt.get("steps"))
    expected_id = _receipt_id(dict(receipt))
    if receipt.get("receipt_id") != expected_id:
        raise R2CasConformanceError("R2 CAS conformance receipt identity is detached")


def build_failure_receipt(
    *,
    status: str,
    failure_stage: str,
    failure_category: str,
    bucket: str | None,
    key: str,
    endpoint_host: str | None,
    github_provenance: Mapping[str, Any],
    execution_provenance: Mapping[str, Any],
    observed_at: datetime,
    deadline_seconds: float = CONFORMANCE_DEADLINE_SECONDS,
    completed_steps: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build a canonical redacted local-review receipt after a non-pass run.

    The helper deliberately accepts neither an exception message nor a request
    body.  The wrapper may record a classified failure but cannot accidentally
    serialize credentials, object names, ETags, or transport diagnostics.
    """
    if status not in {"failed", "inconclusive"}:
        raise R2CasConformanceError("non-pass R2 CAS receipt status is invalid")
    _require_conformance_key(key)
    if (bucket is None) != (endpoint_host is None):
        raise R2CasConformanceError("R2 CAS conformance failure scope is partially admitted")
    scope_admitted = bucket is not None
    if scope_admitted:
        _require_bucket(bucket)
        host = _require_endpoint_host(endpoint_host)
        bucket_sha256: str | None = _hash_text(bucket)
    else:
        host = None
        bucket_sha256 = None
    provenance = _normalize_github_provenance(github_provenance)
    execution = _normalize_execution_provenance(execution_provenance)
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": "",
        "status": status,
        "failure": {"stage": failure_stage, "category": failure_category},
        "manual_only": True,
        "created_at": _iso_timestamp(observed_at),
        "deadline_seconds": _deadline_seconds(deadline_seconds),
        "scope": {
            "admitted": scope_admitted,
            "endpoint_host": host,
            "bucket_sha256": bucket_sha256,
            "key_sha256": _hash_text(key),
        },
        "github_provenance": provenance,
        "execution_provenance": execution,
        "steps": {"completed_steps": list(completed_steps)},
        "output_authority": dict(_NO_AUTHORITY),
        "nonclaims": dict(_NONCLAIMS),
    }
    receipt["receipt_id"] = _receipt_id(receipt)
    validate_conformance_receipt(receipt)
    return receipt


_STEP_NAMES = (
    "create_a",
    "head_a",
    "get_a",
    "duplicate_create",
    "head_a_after_duplicate",
    "get_a_after_duplicate",
    "update_b",
    "head_b",
    "stale_get",
    "stale_put",
    "get_b",
)
_FAILURE_STAGES = {"setup", "probe", *_STEP_NAMES, "receipt"}
_FAILURE_CATEGORIES = {
    "configuration", "deadline", "transport", "unexpected_status",
    "malformed_response", "readback_mismatch", "close_failure",
    "protocol_violation", "unknown",
}


def _failure_category(error: R2CasConformanceError) -> str:
    message = str(error).lower()
    if "deadline" in message or "clock" in message:
        return "deadline"
    if "transport" in message:
        return "transport"
    if "close" in message:
        return "close_failure"
    if any(token in message for token in (
        "read-back", "read bounds", "ended before", "exceeded its declared length",
    )):
        return "readback_mismatch"
    if "http status" in message or "preconditionfailed" in message:
        return "unexpected_status"
    if any(token in message for token in (
        "malformed", "metadata", "etag", "range", "unreadable", "content length",
        "content type",
    )):
        return "malformed_response"
    return "protocol_violation"


@contextmanager
def _observed_stage(stage: str, completed_steps: list[str]) -> Any:
    if (
        len(completed_steps) >= len(_STEP_NAMES)
        or tuple(completed_steps) != _STEP_NAMES[:len(completed_steps)]
        or stage != _STEP_NAMES[len(completed_steps)]
    ):
        raise R2CasConformanceError("R2 CAS conformance internal stage order is invalid")
    try:
        yield
    except R2CasConformanceObservedFailure:
        raise
    except R2CasConformanceError as exc:
        raise R2CasConformanceObservedFailure(
            stage=stage,
            category=_failure_category(exc),
            completed_steps=tuple(completed_steps),
        ) from exc
    else:
        completed_steps.append(stage)


def failure_receipt_evidence(error: BaseException) -> dict[str, Any]:
    """Return only closed, non-secret evidence suitable for a failure receipt."""
    if isinstance(error, R2CasConformanceObservedFailure):
        return {
            "status": "inconclusive",
            "failure_stage": error.failure_stage,
            "failure_category": error.failure_category,
            "completed_steps": error.completed_steps,
        }
    return {
        "status": "inconclusive",
        "failure_stage": "probe",
        "failure_category": "deadline" if getattr(
            error, "conformance_deadline_exceeded", False
        ) else "unknown",
        "completed_steps": (),
    }


def _validate_failure(value: Any) -> None:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"stage", "category"}
        or value.get("stage") not in _FAILURE_STAGES
        or value.get("category") not in _FAILURE_CATEGORIES
    ):
        raise R2CasConformanceError("R2 CAS conformance receipt failure is invalid")


def _validate_receipt_scope(value: Any) -> dict[str, Any]:
    expected = {"admitted", "endpoint_host", "bucket_sha256", "key_sha256"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise R2CasConformanceError("R2 CAS conformance receipt scope is invalid")
    scope = dict(value)
    if scope.get("admitted") is True:
        _require_endpoint_host(scope.get("endpoint_host"))
        bucket_hash = scope.get("bucket_sha256")
        if not isinstance(bucket_hash, str) or not _HEX64_RE.fullmatch(bucket_hash):
            raise R2CasConformanceError("R2 CAS conformance receipt bucket scope is invalid")
    elif scope.get("admitted") is False:
        if scope.get("endpoint_host") is not None or scope.get("bucket_sha256") is not None:
            raise R2CasConformanceError("R2 CAS conformance unadmitted scope is not redacted")
    else:
        raise R2CasConformanceError("R2 CAS conformance receipt scope admission is invalid")
    key_hash = scope.get("key_sha256")
    if not isinstance(key_hash, str) or not _HEX64_RE.fullmatch(key_hash):
        raise R2CasConformanceError("R2 CAS conformance receipt key scope is invalid")
    return scope


def _validate_partial_steps(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {"completed_steps"}:
        raise R2CasConformanceError("R2 CAS conformance receipt partial steps are invalid")
    completed = value.get("completed_steps")
    if not isinstance(completed, list) or len(completed) > len(_STEP_NAMES):
        raise R2CasConformanceError("R2 CAS conformance receipt partial steps are invalid")
    if any(not isinstance(step, str) for step in completed) or tuple(completed) != _STEP_NAMES[:len(completed)]:
        raise R2CasConformanceError("R2 CAS conformance receipt partial steps are not an ordered prefix")


def _validate_passed_steps(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != set(_STEP_NAMES):
        raise R2CasConformanceError("R2 CAS conformance receipt passed steps are invalid")
    for name in ("create_a", "update_b"):
        if value.get(name) != {"http_status": 200}:
            raise R2CasConformanceError("R2 CAS conformance receipt PUT evidence is invalid")
    for name in ("duplicate_create", "stale_get", "stale_put"):
        conflict = value.get(name)
        if not isinstance(conflict, Mapping) or conflict != {
            "http_status": 412,
            "error_code": "PreconditionFailed",
        }:
            raise R2CasConformanceError("R2 CAS conformance receipt conflict evidence is invalid")

    head_a = _validate_head_step(value.get("head_a"), label="head_a", expected_length=len(_BODY_A))
    head_a_after = _validate_head_step(
        value.get("head_a_after_duplicate"),
        label="head_a_after_duplicate",
        expected_length=len(_BODY_A),
    )
    if head_a_after != head_a:
        raise R2CasConformanceError("R2 CAS conformance receipt duplicate-create preservation is invalid")
    head_b = _validate_head_step(value.get("head_b"), label="head_b", expected_length=len(_BODY_B))
    if head_b["etag_sha256"] == head_a["etag_sha256"]:
        raise R2CasConformanceError("R2 CAS conformance receipt update ETag evidence is invalid")

    get_a = _validate_readback_step(
        value.get("get_a"), label="get_a", expected_body=_BODY_A, expected_head=head_a,
    )
    get_a_after = _validate_readback_step(
        value.get("get_a_after_duplicate"),
        label="get_a_after_duplicate", expected_body=_BODY_A, expected_head=head_a,
    )
    if get_a_after != get_a:
        raise R2CasConformanceError("R2 CAS conformance receipt duplicate-create read-back is invalid")
    _validate_readback_step(value.get("get_b"), label="get_b", expected_body=_BODY_B, expected_head=head_b)


def _validate_head_step(value: Any, *, label: str, expected_length: int) -> dict[str, Any]:
    expected_fields = {
        "http_status", "content_length", "content_type", "etag_sha256", "metadata_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise R2CasConformanceError(f"R2 CAS conformance receipt {label} evidence is invalid")
    if (
        value.get("http_status") != 200
        or value.get("content_length") != expected_length
        or value.get("content_type") != "application/json"
        or not isinstance(value.get("etag_sha256"), str)
        or not _HEX64_RE.fullmatch(value["etag_sha256"])
        or not isinstance(value.get("metadata_sha256"), str)
        or not _HEX64_RE.fullmatch(value["metadata_sha256"])
    ):
        raise R2CasConformanceError(f"R2 CAS conformance receipt {label} evidence is invalid")
    return dict(value)


def _validate_readback_step(
    value: Any, *, label: str, expected_body: bytes, expected_head: Mapping[str, Any],
) -> dict[str, Any]:
    expected_fields = {
        "http_status", "content_length", "content_type", "etag_sha256", "metadata_sha256",
        "range", "exact_range_verified", "body_sha256",
    }
    expected_range = f"bytes 0-{len(expected_body) - 1}/{len(expected_body)}"
    if (
        not isinstance(value, Mapping)
        or set(value) != expected_fields
        or value.get("http_status") != 206
        or value.get("content_length") != len(expected_body)
        or value.get("content_type") != "application/json"
        or value.get("etag_sha256") != expected_head["etag_sha256"]
        or value.get("metadata_sha256") != expected_head["metadata_sha256"]
        or value.get("range") != expected_range
        or value.get("exact_range_verified") is not True
        or value.get("body_sha256") != _hash_bytes(expected_body)
    ):
        raise R2CasConformanceError(f"R2 CAS conformance receipt {label} evidence is invalid")
    return dict(value)


def _require_client(client: Any) -> None:
    if client is None or any(not callable(getattr(client, method, None)) for method in ("head_object", "get_object", "put_object")):
        raise R2CasConformanceError("R2 CAS conformance requires a narrow head/get/put client")


def _require_bucket(bucket: Any) -> None:
    if not isinstance(bucket, str) or not _BUCKET_RE.fullmatch(bucket) or ".." in bucket:
        raise R2CasConformanceError("R2 CAS conformance bucket is invalid")


def _require_conformance_key(key: Any) -> None:
    if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
        raise R2CasConformanceError("R2 CAS conformance key must be a fresh v1 UUID-style object key")


def _require_endpoint_host(endpoint_host: Any) -> str:
    if not isinstance(endpoint_host, str) or not _HOST_RE.fullmatch(endpoint_host):
        raise R2CasConformanceError("R2 CAS conformance endpoint must be an exact account-bound R2 host")
    return endpoint_host


def _deadline_seconds(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= CONFORMANCE_DEADLINE_SECONDS:
        raise R2CasConformanceError("R2 CAS conformance deadline must be within the fixed 90-second budget")
    return float(value)


def _iso_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise R2CasConformanceError("R2 CAS conformance observed_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _iso_timestamp_value(value: Any, *, label: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise R2CasConformanceError(f"R2 CAS conformance {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise R2CasConformanceError(f"R2 CAS conformance {label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise R2CasConformanceError(f"R2 CAS conformance {label} is invalid")


def _normalize_github_provenance(value: Any) -> dict[str, Any]:
    expected = {"repository", "workflow_ref", "run_id", "run_attempt", "commit_sha", "event_name", "actor"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise R2CasConformanceError("R2 CAS conformance GitHub provenance is not closed")
    provenance = dict(value)
    expected_workflow_ref = (
        f"{provenance.get('repository', '')}/.github/workflows/"
        "capital-share-count-r2-conformance.yml@refs/heads/main"
    )
    if (
        provenance["repository"] != _EXPECTED_REPOSITORY
        or provenance["workflow_ref"] != expected_workflow_ref
        or not isinstance(provenance["run_id"], str)
        or not _RUN_ID_RE.fullmatch(provenance["run_id"])
        or isinstance(provenance["run_attempt"], bool)
        or not isinstance(provenance["run_attempt"], int)
        or not 1 <= provenance["run_attempt"] <= 1000
        or not isinstance(provenance["commit_sha"], str)
        or not _COMMIT_SHA_RE.fullmatch(provenance["commit_sha"])
        or provenance["event_name"] != "workflow_dispatch"
        or not isinstance(provenance["actor"], str)
        or not _ACTOR_RE.fullmatch(provenance["actor"])
    ):
        raise R2CasConformanceError("R2 CAS conformance GitHub provenance is invalid")
    return provenance


def _normalize_execution_provenance(value: Any) -> dict[str, str]:
    expected = {"source_archive_sha256", "dependency_lock_sha256"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise R2CasConformanceError("R2 CAS conformance execution provenance is not closed")
    normalized = dict(value)
    if any(
        not isinstance(normalized[field], str) or not _HEX64_RE.fullmatch(normalized[field])
        for field in expected
    ):
        raise R2CasConformanceError("R2 CAS conformance execution provenance is invalid")
    return normalized


def _put_success(
    *, deadline: _Deadline, client: R2CasConformanceClient, bucket: str, key: str,
    body: bytes, condition_name: str, condition_value: str, label: str,
) -> dict[str, int]:
    response = _safe_call(
        deadline=deadline,
        label=label,
        call=client.put_object,
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        **{condition_name: condition_value},
    )
    _require_status(response, expected=200, label=label)
    return {"http_status": 200}


def _head(
    *, deadline: _Deadline, client: R2CasConformanceClient, bucket: str, key: str, label: str,
) -> _Head:
    response = _safe_call(
        deadline=deadline, label=label, call=client.head_object, Bucket=bucket, Key=key,
    )
    _require_status(response, expected=200, label=label)
    if not isinstance(response, Mapping):
        raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} response is malformed")
    length = response.get("ContentLength")
    if isinstance(length, bool) or not isinstance(length, int) or not 1 <= length <= MAX_CONFORMANCE_OBJECT_BYTES:
        raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} content length is invalid")
    if response.get("ContentType") != "application/json":
        raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} content type is detached")
    return _Head(
        content_length=length,
        content_type="application/json",
        etag=_opaque_etag(response.get("ETag"), label=label),
    )


def _get_exact(
    *, deadline: _Deadline, client: R2CasConformanceClient, bucket: str, key: str,
    etag: str, body: bytes, label: str,
) -> dict[str, Any]:
    if not 1 <= len(body) <= MAX_CONFORMANCE_OBJECT_BYTES:
        raise R2CasConformanceError("R2 CAS conformance internal body bound is invalid")
    response = _safe_call(
        deadline=deadline,
        label=label,
        call=client.get_object,
        Bucket=bucket,
        Key=key,
        Range=f"bytes=0-{len(body) - 1}",
        IfMatch=etag,
    )
    stream = response.get("Body") if isinstance(response, Mapping) else None
    handed_to_reader = False
    try:
        _require_status(response, expected=206, label=label)
        if not isinstance(response, Mapping):
            raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} response is malformed")
        if (
            response.get("ContentLength") != len(body)
            or response.get("ContentType") != "application/json"
            or response.get("ETag") != etag
        ):
            raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} metadata is detached")
        if response.get("ContentRange") != f"bytes 0-{len(body) - 1}/{len(body)}":
            raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} range metadata is detached")
        if not callable(getattr(stream, "read", None)) or not callable(getattr(stream, "close", None)):
            raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} body is unreadable")
        handed_to_reader = True
        observed = _read_exact_body(deadline=deadline, stream=stream, expected=body, label=label)
    finally:
        if stream is not None and not handed_to_reader and callable(getattr(stream, "close", None)):
            try:
                deadline.close(label, stream)
            except R2CasConformanceError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise R2CasConformanceInconclusive(
                    f"R2 CAS conformance {label} body close failed",
                ) from exc
    return {
        "http_status": 206,
        "content_length": len(observed),
        "content_type": "application/json",
        "etag_sha256": _hash_text(etag),
        "metadata_sha256": _metadata_sha256(
            content_length=len(observed), content_type="application/json", etag=etag,
        ),
        "range": f"bytes 0-{len(body) - 1}/{len(body)}",
        "exact_range_verified": True,
        "body_sha256": _hash_bytes(observed),
    }


def _read_exact_body(*, deadline: _Deadline, stream: Any, expected: bytes, label: str) -> bytes:
    chunks: list[bytes] = []
    observed = 0
    try:
        while observed < len(expected):
            wanted = min(64 * 1024, len(expected) - observed)
            chunk = deadline.read(label, stream, wanted)
            if not isinstance(chunk, bytes) or len(chunk) > wanted:
                raise R2CasConformanceInconclusive(
                    f"R2 CAS conformance {label} body violated read bounds",
                )
            if not chunk:
                raise R2CasConformanceInconclusive(
                    f"R2 CAS conformance {label} body ended before its declared length",
                )
            chunks.append(chunk)
            observed += len(chunk)
        extra = deadline.read(label, stream, 1)
        if not isinstance(extra, bytes) or extra:
            raise R2CasConformanceInconclusive(
                f"R2 CAS conformance {label} body exceeded its declared length",
            )
        body = b"".join(chunks)
        if body != expected:
            raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} read-back bytes differ")
        return body
    except R2CasConformanceError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} body read failed") from exc
    finally:
        try:
            deadline.close(label, stream)
        except R2CasConformanceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} body close failed") from exc


def _authoritative_conflict(*, deadline: _Deadline, call: Callable[[], Any], label: str) -> dict[str, Any]:
    try:
        response = deadline.call(label, lambda: call())
    except R2CasConformanceError:
        raise
    except Exception as exc:  # noqa: BLE001
        if getattr(exc, "conformance_deadline_exceeded", False):
            raise R2CasConformanceInconclusive(
                f"R2 CAS conformance deadline exceeded during {label}",
            ) from exc
        is_client_error = (
            type(exc).__module__ == "botocore.exceptions"
            and type(exc).__name__ == "ClientError"
        )
        status = _status_from_exception(exc)
        response = getattr(exc, "response", None)
        error = response.get("Error") if isinstance(response, Mapping) else None
        code = error.get("Code") if isinstance(error, Mapping) else None
        if is_client_error and status == 412 and code == "PreconditionFailed":
            return {"http_status": 412, "error_code": "PreconditionFailed"}
        raise R2CasConformanceInconclusive(
            f"R2 CAS conformance {label} did not return an authoritative 412 PreconditionFailed",
        ) from exc
    if isinstance(response, Mapping):
        stream = response.get("Body")
        if callable(getattr(stream, "close", None)):
            try:
                deadline.close(label, stream)
            except R2CasConformanceError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise R2CasConformanceInconclusive(
                    f"R2 CAS conformance {label} body close failed",
                ) from exc
    raise R2CasConformanceInconclusive(
        f"R2 CAS conformance {label} unexpectedly succeeded instead of returning 412 PreconditionFailed",
    )


def _safe_call(*, deadline: _Deadline, label: str, call: Callable[..., Any], **kwargs: Any) -> Any:
    try:
        return deadline.call(label, call, **kwargs)
    except R2CasConformanceError:
        raise
    except Exception as exc:  # noqa: BLE001
        if getattr(exc, "conformance_deadline_exceeded", False):
            raise R2CasConformanceInconclusive(
                f"R2 CAS conformance deadline exceeded during {label}",
            ) from exc
        raise R2CasConformanceInconclusive(
            f"R2 CAS conformance {label} transport result is inconclusive",
        ) from exc


def _require_status(response: Any, *, expected: int, label: str) -> None:
    if _status(response) != expected:
        raise R2CasConformanceInconclusive(
            f"R2 CAS conformance {label} returned an unexpected HTTP status",
        )


def _status(response: Any) -> int | None:
    if not isinstance(response, Mapping):
        return None
    metadata = response.get("ResponseMetadata")
    if not isinstance(metadata, Mapping):
        return None
    status = metadata.get("HTTPStatusCode")
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _status_from_exception(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    return _status(response)


def _opaque_etag(value: Any, *, label: str) -> str:
    # ETags are deliberately not parsed, stripped, unquoted, or normalized.
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 1024
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} has no opaque ETag")
    return value


def _assert_metadata(head: _Head, *, body: bytes, label: str) -> None:
    if head.content_length != len(body):
        raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} content length does not match")


def _assert_same_metadata(actual: _Head, expected: _Head, *, label: str) -> None:
    if actual != expected:
        raise R2CasConformanceInconclusive(f"R2 CAS conformance {label} changed the object")


def _head_receipt(head: _Head) -> dict[str, Any]:
    return {
        "http_status": 200,
        "content_length": head.content_length,
        "content_type": head.content_type,
        "etag_sha256": _hash_text(head.etag),
        "metadata_sha256": _metadata_sha256(
            content_length=head.content_length, content_type=head.content_type, etag=head.etag,
        ),
    }


def _hash_text(value: str) -> str:
    return _hash_bytes(value.encode("utf-8"))


def _hash_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _metadata_sha256(*, content_length: int, content_type: str, etag: str) -> str:
    return _hash_bytes(_canonical_json({
        "content_length": content_length,
        "content_type": content_type,
        "etag": etag,
    }))


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise R2CasConformanceError("R2 CAS conformance receipt is not canonical JSON data") from exc


def _receipt_id(receipt: Mapping[str, Any]) -> str:
    material = dict(receipt)
    material.pop("receipt_id", None)
    return RECEIPT_ID_PREFIX + _hash_bytes(_canonical_json(material))


__all__ = [
    "CONFORMANCE_DEADLINE_SECONDS",
    "CONFORMANCE_KEY_PREFIX",
    "MAX_CONFORMANCE_OBJECT_BYTES",
    "R2CasConformanceClient",
    "R2CasConformanceError",
    "R2CasConformanceInconclusive",
    "R2CasConformanceObservedFailure",
    "RECEIPT_SCHEMA",
    "build_failure_receipt",
    "canonical_receipt_bytes",
    "failure_receipt_evidence",
    "run_conformance",
    "validate_conformance_receipt",
]
