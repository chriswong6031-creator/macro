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

from engine.research_vault.r2_store import LocalStore, R2Store, Store


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

    def put_verified(
        self, raw_bytes: bytes, *, media_type: str = "application/octet-stream"
    ) -> SourceReceipt | None:
        if not isinstance(raw_bytes, bytes):
            raise TypeError("raw_bytes must be bytes")
        digest = sha256(raw_bytes).hexdigest()
        key = object_key_for_sha256(digest)
        if not self.store.put_bytes(key, raw_bytes, content_type=media_type):
            log.warning("capital_structure source-store defer key=%s reason=put-failed", key)
            return None
        readback = self.store.get_bytes(key)
        if readback != raw_bytes or sha256(readback or b"").hexdigest() != digest:
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


def build_source_store(
    *, local_dir: str | Path | None = None
) -> ContentAddressedSourceStore | None:
    """Build the nightly SEC evidence store.

    Local storage is explicit. Production prefers a dedicated bucket but can
    use the existing private-research bucket or the main R2 bucket so Wave 1
    does not require a new secret before it can accrue public SEC evidence.
    """
    resolved_local = local_dir or os.environ.get("CAPITAL_STRUCTURE_LOCAL_STORE")
    if resolved_local:
        return ContentAddressedSourceStore(
            LocalStore(resolved_local), backend="local", store_id=STORE_ID_LOCAL
        )
    capital_bucket = os.environ.get("R2_CAPITAL_STRUCTURE_BUCKET")
    if capital_bucket:
        store = R2Store(capital_bucket, client=_capital_structure_r2_client())
        if not store.available:
            log.info(
                "R2_CAPITAL_STRUCTURE_BUCKET set but capital/shared R2 creds absent -- no store"
            )
            return None
        return ContentAddressedSourceStore(
            store, backend="r2", store_id=STORE_ID_DEDICATED_R2
        )

    research_bucket = os.environ.get("R2_RESEARCH_BUCKET")
    if research_bucket:
        store = R2Store(research_bucket)
    else:
        shared_bucket = os.environ.get("R2_BUCKET")
        if not shared_bucket:
            return None
        # R2Store's default client deliberately prefers R2_RESEARCH_* credentials.
        # The main bucket fallback must use the shared R2_* account explicitly.
        store = R2Store(shared_bucket, client=_shared_r2_client())
    if not store.available:
        return None
    store_id = STORE_ID_RESEARCH_R2 if research_bucket else STORE_ID_SHARED_R2
    return ContentAddressedSourceStore(store, backend="r2", store_id=store_id)


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


def _make_r2_client(
    *, endpoint: str | None, access_key: str | None, secret_key: str | None
):
    """Construct the repository-standard R2 client, or ``None`` if incomplete."""
    if not (endpoint and access_key and secret_key):
        return None
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
