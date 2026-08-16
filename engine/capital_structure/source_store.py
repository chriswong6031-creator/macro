"""Immutable source-document storage for Capital Structure Intelligence.

This module deliberately knows nothing about SEC downloading.  A nightly
collector supplies bytes it has already retrieved; this module gives those
bytes a content address, writes them through the repository's small object
store protocol, and returns a verified receipt only after a read-back check.
Stable ``store_id`` aliases must never be rebound to a different physical
bucket without a verified object copy and migration receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import logging
import os
from pathlib import Path
from typing import Any

from engine.research_vault.r2_store import BoundedStrictReadStore, LocalStore, R2Store, Store


log = logging.getLogger("capital_structure.source_store")

SEC_OBJECT_PREFIX = "capital_structure/sec/sha256"
STORE_ID_LOCAL = "capital_structure_local"
STORE_ID_DEDICATED_R2 = "r2_capital_structure"
STORE_ID_RESEARCH_R2 = "r2_research"
STORE_ID_SHARED_R2 = "r2_shared"
STORE_BACKENDS = {
    STORE_ID_LOCAL: "local",
    STORE_ID_DEDICATED_R2: "r2",
    STORE_ID_RESEARCH_R2: "r2",
    STORE_ID_SHARED_R2: "r2",
}


@dataclass(frozen=True)
class SourceReceipt:
    """Verified storage receipt used to build the strict source manifest."""

    object_key: str
    sha256: str
    byte_length: int
    media_type: str
    backend: str
    store_id: str


class SourceStoreVerificationError(RuntimeError):
    """An immutable source object could not be verified exactly."""


class SourceStoreIdentityError(SourceStoreVerificationError, ValueError):
    """The requested content address and digest disagree."""


class SourceStoreBoundsError(SourceStoreVerificationError, ValueError):
    """The requested strict-read length boundary is invalid."""


class SourceStoreCapabilityError(SourceStoreVerificationError):
    """The backend does not implement bounded fail-closed reads."""


class SourceStoreLengthError(SourceStoreVerificationError):
    """The backend returned a non-exact byte count."""


class SourceStoreDigestError(SourceStoreVerificationError):
    """The backend returned bytes with the wrong SHA-256 digest."""


class ContentAddressedSourceStore:
    """Fail-closed content-addressed wrapper around the repository Store API.

    ``Store`` itself is intentionally fail-open. Evidence manifests require a
    stronger promise: bytes must be written and read back with the exact digest
    before a receipt is returned.
    """

    def __init__(
        self,
        store: Store,
        *,
        backend: str | None = None,
        store_id: str | None = None,
    ) -> None:
        self.store = store
        if backend is not None:
            self.backend = backend
        elif isinstance(store, LocalStore):
            self.backend = "local"
        else:
            self.backend = "r2"
        if store_id is None and isinstance(store, LocalStore):
            store_id = STORE_ID_LOCAL
        if store_id not in STORE_BACKENDS:
            raise ValueError(
                "a stable non-secret store_id is required for non-local source storage"
            )
        if STORE_BACKENDS[store_id] != self.backend:
            raise ValueError(
                f"store_id {store_id!r} does not match backend {self.backend!r}"
            )
        self.store_id = store_id
        self.last_failure: dict[str, Any] | None = None

    def put_verified(
        self, raw_bytes: bytes, *, media_type: str = "application/octet-stream"
    ) -> SourceReceipt | None:
        self.last_failure = None
        if not isinstance(raw_bytes, bytes):
            raise TypeError("raw_bytes must be bytes")
        digest = sha256(raw_bytes).hexdigest()
        key = object_key_for_sha256(digest)
        if not self.store.put_bytes(key, raw_bytes, content_type=media_type):
            inner = getattr(self.store, "last_put_error", None)
            self.last_failure = _store_failure(
                operation="PutObject",
                reason="put-failed",
                store_id=self.store_id,
                exc=inner if isinstance(inner, BaseException) else None,
                detail=None if inner else "put_bytes returned False",
            )
            log.warning("capital_structure source-store defer key=%s reason=put-failed", key)
            return None
        try:
            if not isinstance(self.store, BoundedStrictReadStore):
                raise RuntimeError("source store lacks bounded strict-read capability")
            readback = self.store.get_bytes_strict_bounded(
                key, expected_byte_length=len(raw_bytes), max_byte_length=len(raw_bytes),
            )
        except Exception as exc:  # noqa: BLE001 - no legacy fail-open readback fallback
            self.last_failure = _store_failure(
                operation="GetObject",
                reason="bounded-readback-failed",
                store_id=self.store_id,
                exc=exc,
            )
            log.warning(
                "capital_structure source-store defer key=%s reason=bounded-readback-failed: %s",
                key, exc,
            )
            return None
        if readback != raw_bytes or sha256(readback or b"").hexdigest() != digest:
            self.last_failure = _store_failure(
                operation="GetObject",
                reason="readback-mismatch",
                store_id=self.store_id,
                detail="readback bytes or digest did not match the put payload",
            )
            log.warning("capital_structure source-store defer key=%s reason=readback-mismatch", key)
            return None
        return SourceReceipt(
            object_key=key,
            sha256=digest,
            byte_length=len(raw_bytes),
            media_type=media_type,
            backend=self.backend,
            store_id=self.store_id,
        )

    def get_verified(self, object_key: str, expected_sha256: str) -> bytes | None:
        """Read bytes only when both the key shape and content digest agree."""
        if object_key != object_key_for_sha256(expected_sha256):
            return None
        raw = self.store.get_bytes(object_key)
        if raw is None or sha256(raw).hexdigest() != expected_sha256:
            return None
        return raw

    def get_verified_strict_bounded(
        self, object_key: str, expected_sha256: str, *,
        expected_byte_length: int, max_byte_length: int,
    ) -> bytes | None:
        """Verify one exact object without permitting an unbounded legacy read."""
        try:
            expected_key = object_key_for_sha256(expected_sha256)
        except (TypeError, ValueError) as exc:
            raise SourceStoreIdentityError("expected digest is not lowercase SHA-256") from exc
        if object_key != expected_key:
            raise SourceStoreIdentityError("source object key does not bind expected digest")
        if (
            isinstance(expected_byte_length, bool)
            or not isinstance(expected_byte_length, int)
            or expected_byte_length < 0
            or isinstance(max_byte_length, bool)
            or not isinstance(max_byte_length, int)
            or max_byte_length < 0
            or expected_byte_length > max_byte_length
        ):
            raise SourceStoreBoundsError(
                "source strict-read bounds must satisfy 0 <= expected <= maximum"
            )
        if not isinstance(self.store, BoundedStrictReadStore):
            raise SourceStoreCapabilityError("source store lacks bounded strict-read capability")
        raw = self.store.get_bytes_strict_bounded(
            object_key,
            expected_byte_length=expected_byte_length,
            max_byte_length=max_byte_length,
        )
        if raw is None:
            return None
        if not isinstance(raw, bytes) or len(raw) != expected_byte_length:
            raise SourceStoreLengthError("source store returned a non-exact byte count")
        if sha256(raw).hexdigest() != expected_sha256:
            raise SourceStoreDigestError("source store returned bytes with the wrong digest")
        return raw


WRITE_PROBE_PAYLOAD = b"capital-structure-write-probe/v1\n"


def http_status_from_error(exc: BaseException | None) -> int | None:
    """Extract an HTTP status from a boto/requests exception without guessing."""
    if exc is None:
        return None
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        meta = response.get("ResponseMetadata") or {}
        status = meta.get("HTTPStatusCode")
        if isinstance(status, int) and not isinstance(status, bool):
            return status
    status = getattr(response, "status_code", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return status
    return None


def _store_failure(
    *,
    operation: str,
    reason: str,
    store_id: str,
    exc: BaseException | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    message = detail
    error_class = reason
    if exc is not None:
        error_class = type(exc).__name__
        message = f"{type(exc).__name__}: {exc}"
    return {
        "operation": operation,
        "reason": reason,
        "store_id": store_id,
        "error_class": error_class,
        "error": message or reason,
        "http_status": http_status_from_error(exc),
    }


def format_store_failure(failure: dict[str, Any] | None) -> str:
    """Stable collector error string carrying store operation and HTTP status."""
    if not failure:
        return "source-store write/readback verification failed"
    status = failure.get("http_status")
    status_bit = f" http_status={status}" if status is not None else ""
    return (
        "source-store write/readback verification failed "
        f"(operation={failure.get('operation')} store_id={failure.get('store_id')}"
        f"{status_bit} reason={failure.get('reason')}): {failure.get('error')}"
    )


def _probe_writable(store: ContentAddressedSourceStore) -> bool:
    """Return True only when put+readback of a tiny probe object succeeds."""
    try:
        return store.put_verified(WRITE_PROBE_PAYLOAD, media_type="text/plain") is not None
    except Exception as exc:  # noqa: BLE001 - a probe must never abort store selection
        log.warning(
            "capital_structure source-store write probe raised store_id=%s: %s",
            store.store_id, exc,
        )
        return False


def build_source_store(
    *, local_dir: str | Path | None = None, require_writable: bool = False
) -> ContentAddressedSourceStore | None:
    """Build the nightly SEC evidence store.

    Local storage is explicit. Production prefers a dedicated bucket but can
    use the existing private-research bucket or the main R2 bucket so Wave 1
    does not require a new secret before it can accrue public SEC evidence.

    ``require_writable=True`` (the collector write path) probes put+readback
    and falls through when the preferred store is constructed but cannot
    PutObject. Measured 2026-08-08→08-14: ``R2_CAPITAL_STRUCTURE_BUCKET`` was
    set, the client constructed, and every PutObject returned AccessDenied,
    so preferring dedicated without a write probe froze the source ledger
    while workflows stayed green.
    """
    resolved_local = local_dir or os.environ.get("CAPITAL_STRUCTURE_LOCAL_STORE")
    if resolved_local:
        local = ContentAddressedSourceStore(
            LocalStore(resolved_local), backend="local", store_id=STORE_ID_LOCAL
        )
        if not require_writable or _probe_writable(local):
            return local
        return None

    candidates: list[tuple[str, ContentAddressedSourceStore]] = []
    capital_bucket = os.environ.get("R2_CAPITAL_STRUCTURE_BUCKET")
    if capital_bucket:
        capital = R2Store(capital_bucket, client=_capital_structure_r2_client())
        if capital.available:
            candidates.append((
                STORE_ID_DEDICATED_R2,
                ContentAddressedSourceStore(
                    capital, backend="r2", store_id=STORE_ID_DEDICATED_R2
                ),
            ))
        else:
            log.info(
                "R2_CAPITAL_STRUCTURE_BUCKET set but capital/shared R2 creds absent "
                "-- trying the next configured store"
            )

    research_bucket = os.environ.get("R2_RESEARCH_BUCKET")
    if research_bucket:
        research = R2Store(research_bucket)
        if research.available:
            candidates.append((
                STORE_ID_RESEARCH_R2,
                ContentAddressedSourceStore(
                    research, backend="r2", store_id=STORE_ID_RESEARCH_R2
                ),
            ))

    shared_bucket = os.environ.get("R2_BUCKET")
    if shared_bucket:
        shared = R2Store(shared_bucket, client=_shared_r2_client())
        if shared.available:
            candidates.append((
                STORE_ID_SHARED_R2,
                ContentAddressedSourceStore(
                    shared, backend="r2", store_id=STORE_ID_SHARED_R2
                ),
            ))

    for store_id, wrapper in candidates:
        if not require_writable:
            return wrapper
        if _probe_writable(wrapper):
            if store_id != STORE_ID_DEDICATED_R2 and capital_bucket:
                print(
                    "::warning title=capital-structure-store-fallback::"
                    f"preferred dedicated store failed the write probe; "
                    f"using {store_id} so SEC evidence can still be retained",
                    flush=True,
                )
            return wrapper
        log.warning(
            "capital_structure source-store %s failed write probe — trying next store",
            store_id,
        )
        print(
            f"::warning title=capital-structure-store-unwritable::"
            f"{store_id} put/readback probe failed"
            + (
                f": {format_store_failure(wrapper.last_failure)}"
                if wrapper.last_failure
                else ""
            ),
            flush=True,
        )
    return None


def build_source_stores(
    *, local_dir: str | Path | None = None
) -> dict[str, ContentAddressedSourceStore]:
    """Resolve every configured immutable manifest namespace independently.

    The collector writes to one preferred store, but offline consumers can meet
    a ledger spanning an older shared bucket and a newer dedicated bucket. They
    must select by the manifest's stable ``store_id``; using whichever bucket
    happens to be preferred today would silently rebind source identity.
    """
    stores: dict[str, ContentAddressedSourceStore] = {}
    resolved_local = local_dir or os.environ.get("CAPITAL_STRUCTURE_LOCAL_STORE")
    if resolved_local:
        stores[STORE_ID_LOCAL] = ContentAddressedSourceStore(
            LocalStore(resolved_local), backend="local", store_id=STORE_ID_LOCAL
        )

    capital_bucket = os.environ.get("R2_CAPITAL_STRUCTURE_BUCKET")
    if capital_bucket:
        capital = R2Store(capital_bucket, client=_capital_structure_r2_client())
        if capital.available:
            stores[STORE_ID_DEDICATED_R2] = ContentAddressedSourceStore(
                capital, backend="r2", store_id=STORE_ID_DEDICATED_R2
            )

    research_bucket = os.environ.get("R2_RESEARCH_BUCKET")
    if research_bucket:
        research = R2Store(research_bucket)
        if research.available:
            stores[STORE_ID_RESEARCH_R2] = ContentAddressedSourceStore(
                research, backend="r2", store_id=STORE_ID_RESEARCH_R2
            )

    shared_bucket = os.environ.get("R2_BUCKET")
    if shared_bucket:
        shared = R2Store(shared_bucket, client=_shared_r2_client())
        if shared.available:
            stores[STORE_ID_SHARED_R2] = ContentAddressedSourceStore(
                shared, backend="r2", store_id=STORE_ID_SHARED_R2
            )
    return stores


def _normalize_r2_endpoint(endpoint: str) -> str:
    """Repair the endpoint shapes a re-provisioned secret realistically arrives in.

    2026-08-08: the nightly document-terms step died at boto3 client
    construction (``ValueError: Invalid endpoint``) the first night after the
    ``R2_CAPITAL_STRUCTURE_*`` secrets were re-provisioned — botocore validates
    the URL shape before any request is signed, so a stored value with stray
    whitespace/quotes or a missing ``https://`` scheme kills the job outright.
    Normalize exactly those pasteboard defects and nothing else: a wrong
    hostname must still fail loudly at request time, never get rewritten here.
    """
    cleaned = endpoint.strip().strip("'\"").strip()
    if cleaned and "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    return cleaned


def _make_r2_client(
    *, endpoint: str | None, access_key: str | None, secret_key: str | None
):
    """Construct the repository-standard R2 client, or ``None`` if incomplete."""
    if not (endpoint and access_key and secret_key):
        return None
    normalized = _normalize_r2_endpoint(endpoint)
    access_key = access_key.strip()
    secret_key = secret_key.strip()
    if not (normalized and access_key and secret_key):
        return None
    if normalized != endpoint:
        # Line-start bare print, never a logger: the prefixing formats every
        # builder logger uses would make GitHub drop the annotation silently.
        print(
            "::warning title=capital-structure-r2-endpoint-normalized::the stored"
            " R2 endpoint needed normalization (stray whitespace/quotes or a"
            " missing https:// scheme). The client was constructed from the"
            " repaired value; re-set R2_CAPITAL_STRUCTURE_ENDPOINT (or"
            " R2_ENDPOINT) to the exact https account root to clear this.",
            flush=True,
        )
    endpoint = normalized
    import boto3
    from botocore.config import Config

    kwargs = dict(
        region_name="auto",
        signature_version="s3v4",
        max_pool_connections=32,
        retries={"max_attempts": 5, "mode": "adaptive"},
        connect_timeout=15,
        read_timeout=60,
    )
    try:
        config = Config(
            **kwargs,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    except TypeError:
        config = Config(**kwargs)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=config,
    )


def _capital_structure_r2_client():
    """Use a dedicated capital-structure account, falling back to shared R2 creds."""
    return _make_r2_client(
        endpoint=(
            os.environ.get("R2_CAPITAL_STRUCTURE_ENDPOINT")
            or os.environ.get("R2_ENDPOINT")
        ),
        access_key=(
            os.environ.get("R2_CAPITAL_STRUCTURE_ACCESS_KEY_ID")
            or os.environ.get("R2_ACCESS_KEY_ID")
        ),
        secret_key=(
            os.environ.get("R2_CAPITAL_STRUCTURE_SECRET_ACCESS_KEY")
            or os.environ.get("R2_SECRET_ACCESS_KEY")
        ),
    )


def _shared_r2_client():
    """Use only the shared account for the main ``R2_BUCKET`` fallback."""
    return _make_r2_client(
        endpoint=os.environ.get("R2_ENDPOINT"),
        access_key=os.environ.get("R2_ACCESS_KEY_ID"),
        secret_key=os.environ.get("R2_SECRET_ACCESS_KEY"),
    )


def object_key_for_sha256(digest: str) -> str:
    """Return the immutable SEC object key for a hexadecimal SHA-256 digest."""
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("digest must be a lowercase SHA-256 hex string")
    return f"{SEC_OBJECT_PREFIX}/{digest[:2]}/{digest}"
