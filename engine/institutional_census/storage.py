"""Fail-closed object storage for the institutional 13F evidence plane."""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from typing import Mapping

from engine.research_vault.r2_store import (
    LocalStore,
    R2Store,
    StrictBoundedReadStore,
    StrictConditionalWriteStore,
)

from .models import (
    EvidenceClocks,
    Institutional13FError,
    RawEvidenceReceipt,
    StoredObject,
    content_object_key,
    validate_owned_key,
)


HARD_MAX_RAW_EVIDENCE_BYTES = 512 * 1024 * 1024
HARD_MAX_RAW_RECEIPT_BYTES = 128 * 1024

_DEDICATED_ENVIRONMENT = (
    "INSTITUTIONAL_13F_R2_ENDPOINT",
    "INSTITUTIONAL_13F_R2_ACCESS_KEY_ID",
    "INSTITUTIONAL_13F_R2_SECRET_ACCESS_KEY",
    "INSTITUTIONAL_13F_R2_BUCKET",
)


class Institutional13FStorageError(Institutional13FError):
    """The dedicated 13F evidence store failed a strict operation."""


class Institutional13FR2Store(R2Store):
    """R2Store bound to credentials built only from the dedicated namespace."""

    credential_namespace = "INSTITUTIONAL_13F_R2"

    def __init__(self, bucket: str, *, client: object) -> None:
        if not isinstance(bucket, str) or not bucket.strip():
            raise Institutional13FStorageError("dedicated institutional 13F bucket is required")
        if client is None:
            raise Institutional13FStorageError("dedicated institutional 13F client is required")
        super().__init__(bucket.strip(), client=client)


def _dedicated_r2_client(*, endpoint: str, access_key: str, secret_key: str):
    """Construct a client without consulting any generic or research R2 setting."""
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover - production dependency is pinned.
        raise Institutional13FStorageError("boto3 is required for institutional 13F R2") from exc
    options = dict(
        region_name="auto",
        signature_version="s3v4",
        max_pool_connections=32,
        retries={"max_attempts": 5, "mode": "adaptive"},
        connect_timeout=15,
        read_timeout=60,
    )
    try:
        config = Config(
            **options,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    except TypeError:  # pragma: no cover - compatibility with an older botocore.
        config = Config(**options)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=config,
    )


def build_institutional_13f_store(
    *,
    local_dir: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> StrictConditionalWriteStore:
    """Build the explicit local test store or the dedicated production R2 store.

    There is intentionally no environment-selected local mode and no fallback
    to ``R2_*`` or ``R2_RESEARCH_*`` credentials.  An operator must either pass
    ``local_dir`` directly or configure every dedicated variable.
    """
    if local_dir is not None:
        if str(local_dir) == "":
            raise Institutional13FStorageError("local_dir cannot be empty")
        return LocalStore(local_dir)

    source = os.environ if environment is None else environment
    configured = {name: source.get(name) for name in _DEDICATED_ENVIRONMENT}
    missing = [
        name
        for name, value in configured.items()
        if not isinstance(value, str) or not value
    ]
    if missing:
        raise Institutional13FStorageError(
            "dedicated institutional 13F R2 configuration is incomplete: " + ", ".join(missing)
        )
    client = _dedicated_r2_client(
        endpoint=str(configured["INSTITUTIONAL_13F_R2_ENDPOINT"]),
        access_key=str(configured["INSTITUTIONAL_13F_R2_ACCESS_KEY_ID"]),
        secret_key=str(configured["INSTITUTIONAL_13F_R2_SECRET_ACCESS_KEY"]),
    )
    return Institutional13FR2Store(
        str(configured["INSTITUTIONAL_13F_R2_BUCKET"]), client=client
    )


def _require_conditional_store(store: object) -> StrictConditionalWriteStore:
    if not isinstance(store, StrictConditionalWriteStore):
        raise Institutional13FStorageError(
            "institutional 13F publication requires a StrictConditionalWriteStore"
        )
    try:
        store.validate_strict_conditional_write_capability()
    except Exception as exc:  # noqa: BLE001 - capability is a hard pre-write gate.
        raise Institutional13FStorageError(
            "institutional 13F conditional-write capability validation failed"
        ) from exc
    return store


def _read_bounded_optional(
    store: StrictBoundedReadStore,
    key: str,
    *,
    maximum_bytes: int,
) -> bytes | None:
    validate_owned_key(key)
    if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int) or maximum_bytes < 0:
        raise Institutional13FStorageError("bounded read maximum is invalid")
    try:
        payload = store.get_bytes_strict_bounded(key, maximum_bytes)
    except Exception as exc:  # noqa: BLE001 - an outage is never object absence.
        raise Institutional13FStorageError(f"bounded read failed for {key}") from exc
    if payload is not None and type(payload) is not bytes:
        raise Institutional13FStorageError(f"bounded read returned non-bytes for {key}")
    if payload is not None and len(payload) > maximum_bytes:
        raise Institutional13FStorageError(f"bounded read limit was ignored for {key}")
    return payload


def read_verified_object(
    store: StrictBoundedReadStore,
    descriptor: StoredObject,
    *,
    maximum_bytes: int,
) -> bytes:
    """Read one manifest-bound immutable object and prove length and digest."""
    if not isinstance(descriptor, StoredObject):
        raise TypeError("descriptor must be StoredObject")
    if descriptor.byte_length > maximum_bytes:
        raise Institutional13FStorageError("stored object exceeds its role byte ceiling")
    payload = _read_bounded_optional(store, descriptor.object_key, maximum_bytes=maximum_bytes)
    if payload is None:
        raise Institutional13FStorageError(f"required object is missing: {descriptor.object_key}")
    if len(payload) != descriptor.byte_length or sha256(payload).hexdigest() != descriptor.sha256:
        raise Institutional13FStorageError(
            f"stored object digest or byte length mismatch: {descriptor.object_key}"
        )
    return payload


def create_verified_immutable(
    store: StrictConditionalWriteStore,
    *,
    key: str,
    payload: bytes,
    content_type: str,
    maximum_bytes: int,
    expected_sha256: str | None = None,
) -> bool:
    """Create an immutable object and reconcile only by exact bounded readback.

    Returns ``True`` only when this call received the accepted create.  An
    existing byte-identical object is idempotent and returns ``False``.  A
    different object at the same immutable key is a terminal collision; it is
    never overwritten.
    """
    store = _require_conditional_store(store)
    key = validate_owned_key(key)
    if type(payload) is not bytes:
        raise Institutional13FStorageError("immutable payload must be exact bytes")
    if (
        isinstance(maximum_bytes, bool)
        or not isinstance(maximum_bytes, int)
        or maximum_bytes < 0
        or len(payload) > maximum_bytes
    ):
        raise Institutional13FStorageError("immutable payload exceeds its byte ceiling")
    digest = sha256(payload).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise Institutional13FStorageError("immutable payload does not match expected digest")

    # The probe is only an optimization for exact idempotency (especially for
    # large local test objects).  Correctness still comes from the conditional
    # create below when the probe reports absence.
    existing = _read_bounded_optional(store, key, maximum_bytes=maximum_bytes)
    if existing is not None:
        if existing == payload:
            return False
        raise Institutional13FStorageError(f"immutable object collision: {key}")

    failure: BaseException | None = None
    try:
        written = store.put_bytes_strict_conditional(
            key,
            payload,
            expected_version=None,
            content_type=content_type,
        )
    except Exception as exc:  # noqa: BLE001 - commit acknowledgement may have been lost.
        written = None
        failure = exc

    try:
        echoed = _read_bounded_optional(store, key, maximum_bytes=maximum_bytes)
    except Institutional13FStorageError as exc:
        raise Institutional13FStorageError(f"immutable write outcome is unknown: {key}") from (
            failure if failure is not None else exc
        )
    if echoed == payload:
        return written is True
    if echoed is not None:
        error = Institutional13FStorageError(f"immutable object collision: {key}")
    else:
        error = Institutional13FStorageError(f"immutable object read-back mismatch: {key}")
    if failure is not None:
        raise error from failure
    raise error


def publish_raw_evidence(
    store: StrictConditionalWriteStore,
    *,
    accession: str,
    filer_cik: str | int,
    form: str,
    report_period: str,
    accepted_at: str,
    retained_at: str,
    source_url: str,
    payload: bytes,
    producer_version: str,
) -> RawEvidenceReceipt:
    """Persist SEC bytes first, then their immutable canonical receipt."""
    store = _require_conditional_store(store)
    if type(payload) is not bytes or not payload:
        raise Institutional13FStorageError("raw SEC evidence must be non-empty exact bytes")
    if len(payload) > HARD_MAX_RAW_EVIDENCE_BYTES:
        raise Institutional13FStorageError("raw SEC evidence exceeds its byte ceiling")
    digest = sha256(payload).hexdigest()
    raw = StoredObject(
        role="raw_submission",
        object_key=content_object_key(digest, content_type="application/octet-stream"),
        sha256=digest,
        byte_length=len(payload),
        content_type="application/octet-stream",
    )
    try:
        clocks = EvidenceClocks(
            report_period=report_period,
            accepted_at=accepted_at,
            retained_at=retained_at,
        )
        receipt = RawEvidenceReceipt.build(
            accession=accession,
            filer_cik=filer_cik,
            form=form,
            source_url=source_url,
            producer_version=producer_version,
            clocks=clocks,
            raw_object=raw,
        )
    except Institutional13FError as exc:
        raise Institutional13FStorageError(str(exc)) from exc
    create_verified_immutable(
        store,
        key=raw.object_key,
        payload=payload,
        content_type=raw.content_type,
        maximum_bytes=HARD_MAX_RAW_EVIDENCE_BYTES,
        expected_sha256=raw.sha256,
    )
    receipt_payload = receipt.to_json_bytes()
    create_verified_immutable(
        store,
        key=receipt.object_key,
        payload=receipt_payload,
        content_type="application/json",
        maximum_bytes=HARD_MAX_RAW_RECEIPT_BYTES,
        expected_sha256=sha256(receipt_payload).hexdigest(),
    )
    verified, echoed = load_raw_evidence(store, receipt.object_key)
    if verified != receipt or echoed != payload:  # pragma: no cover - load proves both.
        raise Institutional13FStorageError("raw evidence local verification failed")
    return receipt


def load_raw_evidence(
    store: StrictBoundedReadStore,
    receipt_key: str,
) -> tuple[RawEvidenceReceipt, bytes]:
    """Load one canonical receipt and its exact content-addressed source bytes."""
    if not isinstance(store, StrictBoundedReadStore):
        raise Institutional13FStorageError(
            "raw evidence load requires a StrictBoundedReadStore"
        )
    key = validate_owned_key(receipt_key)
    receipt_payload = _read_bounded_optional(
        store, key, maximum_bytes=HARD_MAX_RAW_RECEIPT_BYTES
    )
    if receipt_payload is None:
        raise Institutional13FStorageError(f"raw evidence receipt is missing: {key}")
    try:
        receipt = RawEvidenceReceipt.from_json_bytes(receipt_payload)
    except Institutional13FError as exc:
        raise Institutional13FStorageError(str(exc)) from exc
    if receipt.object_key != key:
        raise Institutional13FStorageError("raw evidence receipt key does not bind its identity")
    payload = read_verified_object(
        store,
        receipt.raw_object,
        maximum_bytes=HARD_MAX_RAW_EVIDENCE_BYTES,
    )
    return receipt, payload
