"""Immutable SEC quarterly-bulk revision receipts.

SEC can refresh a published filing-month ZIP.  Each byte revision is retained;
bulk reconciliation never overwrites accession evidence or a prior ZIP revision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Any

from engine.institutional_census.models import (
    StoredObject,
    canonical_json_bytes,
    content_object_key,
    decode_canonical_json,
    normalize_report_period,
    normalize_utc,
    validate_source_url,
    validate_version,
)
from engine.institutional_census.storage import (
    HARD_MAX_RAW_EVIDENCE_BYTES,
    Institutional13FStorageError,
    create_verified_immutable,
    read_verified_object,
)
from engine.research_vault.r2_store import (
    StrictBoundedReadStore,
    StrictConditionalWriteStore,
)

BULK_REVISION_SCHEMA = "institutional_13f.bulk_revision_receipt/v1"
HARD_MAX_BULK_RECEIPT_BYTES = 64 * 1024


@dataclass(frozen=True)
class BulkRevisionReceipt:
    revision_id: str
    window_start: str
    window_end: str
    source_url: str
    retained_at: str
    producer_version: str
    raw_object: StoredObject
    schema: str = BULK_REVISION_SCHEMA

    def __post_init__(self) -> None:
        start = normalize_report_period(self.window_start)
        end = normalize_report_period(self.window_end)
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise ValueError("bulk window start follows window end")
        object.__setattr__(self, "window_start", start)
        object.__setattr__(self, "window_end", end)
        object.__setattr__(self, "source_url", validate_source_url(self.source_url))
        object.__setattr__(
            self, "retained_at", normalize_utc(self.retained_at, field="retained_at")
        )
        object.__setattr__(
            self, "producer_version", validate_version(self.producer_version)
        )
        if not isinstance(self.raw_object, StoredObject):
            object.__setattr__(
                self, "raw_object", StoredObject.from_dict(self.raw_object)
            )
        if self.raw_object.role != "sec_form13f_bulk_zip":
            raise ValueError("bulk revision raw object has the wrong role")
        expected = (
            "i13fbulk_"
            + sha256(canonical_json_bytes(self._identity_body())).hexdigest()
        )
        if self.revision_id != expected:
            raise ValueError("bulk revision identity mismatch")

    @classmethod
    def build(
        cls,
        *,
        window_start: str,
        window_end: str,
        source_url: str,
        retained_at: str,
        producer_version: str,
        raw_object: StoredObject,
    ) -> BulkRevisionReceipt:
        normalized = {
            "window_start": normalize_report_period(window_start),
            "window_end": normalize_report_period(window_end),
            "source_url": validate_source_url(source_url),
            "retained_at": normalize_utc(retained_at, field="retained_at"),
            "producer_version": validate_version(producer_version),
            "raw_object": raw_object,
        }
        identity = {
            "schema": BULK_REVISION_SCHEMA,
            "window_start": normalized["window_start"],
            "window_end": normalized["window_end"],
            "source_url": normalized["source_url"],
            "raw_object": raw_object.to_dict(),
        }
        revision_id = "i13fbulk_" + sha256(canonical_json_bytes(identity)).hexdigest()
        return cls(revision_id=revision_id, **normalized)

    def _identity_body(self) -> dict[str, Any]:
        # Retention and producer clocks describe the first verified encounter;
        # they are deliberately not identity.  Re-fetching the same SEC window
        # and exact ZIP bytes on later reconciliation days must resolve to the
        # first immutable receipt instead of minting daily duplicates.
        return {
            "schema": self.schema,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "source_url": self.source_url,
            "raw_object": self.raw_object.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "revision_id": self.revision_id,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "source_url": self.source_url,
            "retained_at": self.retained_at,
            "producer_version": self.producer_version,
            "raw_object": self.raw_object.to_dict(),
        }

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> BulkRevisionReceipt:
        value = decode_canonical_json(payload, label="institutional 13F bulk revision")
        expected = {
            "schema",
            "revision_id",
            "window_start",
            "window_end",
            "source_url",
            "retained_at",
            "producer_version",
            "raw_object",
        }
        if set(value) != expected or value.get("schema") != BULK_REVISION_SCHEMA:
            raise ValueError("bulk revision receipt shape mismatch")
        return cls(**value)

    @property
    def object_key(self) -> str:
        window = f"{self.window_start}_{self.window_end}"
        return (
            "smart-money/13f/evidence/v1/bulk/windows/"
            f"{window}/revisions/{self.raw_object.sha256}/{self.revision_id}.json"
        )


def publish_bulk_revision(
    store: StrictConditionalWriteStore,
    *,
    window_start: str,
    window_end: str,
    source_url: str,
    payload: bytes,
    retained_at: str,
    producer_version: str,
) -> BulkRevisionReceipt:
    if not isinstance(store, StrictConditionalWriteStore):
        raise Institutional13FStorageError(
            "bulk publication requires a conditional-write store"
        )
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > HARD_MAX_RAW_EVIDENCE_BYTES
    ):
        raise Institutional13FStorageError(
            "bulk ZIP bytes are absent or exceed the evidence ceiling"
        )
    digest = sha256(payload).hexdigest()
    raw = StoredObject(
        role="sec_form13f_bulk_zip",
        object_key=content_object_key(digest, content_type="application/octet-stream"),
        sha256=digest,
        byte_length=len(payload),
        content_type="application/octet-stream",
    )
    candidate = BulkRevisionReceipt.build(
        window_start=window_start,
        window_end=window_end,
        source_url=source_url,
        retained_at=retained_at,
        producer_version=producer_version,
        raw_object=raw,
    )
    existing_payload = store.get_bytes_strict_bounded(
        candidate.object_key, HARD_MAX_BULK_RECEIPT_BYTES
    )
    if existing_payload is not None:
        existing = load_bulk_revision(store, candidate.object_key)
        if existing.revision_id != candidate.revision_id or existing.raw_object != raw:
            raise Institutional13FStorageError(
                "bulk revision deterministic identity collision"
            )
        return existing
    create_verified_immutable(
        store,
        key=raw.object_key,
        payload=payload,
        content_type=raw.content_type,
        maximum_bytes=HARD_MAX_RAW_EVIDENCE_BYTES,
        expected_sha256=digest,
    )
    encoded = candidate.to_json_bytes()
    try:
        create_verified_immutable(
            store,
            key=candidate.object_key,
            payload=encoded,
            content_type="application/json",
            maximum_bytes=HARD_MAX_BULK_RECEIPT_BYTES,
            expected_sha256=sha256(encoded).hexdigest(),
        )
    except Institutional13FStorageError:
        # A concurrent reconciler can win the same deterministic receipt key
        # with an earlier retained_at between our absence probe and create.
        # Accept only that fully verified winner; all other failures remain loud.
        loaded = load_bulk_revision(store, candidate.object_key)
        if loaded.revision_id != candidate.revision_id or loaded.raw_object != raw:
            raise
        return loaded
    loaded = load_bulk_revision(store, candidate.object_key)
    if loaded != candidate:
        raise Institutional13FStorageError("bulk revision readback mismatch")
    return candidate


def load_bulk_revision(
    store: StrictBoundedReadStore,
    receipt_key: str,
) -> BulkRevisionReceipt:
    payload = store.get_bytes_strict_bounded(receipt_key, HARD_MAX_BULK_RECEIPT_BYTES)
    if payload is None:
        raise Institutional13FStorageError("bulk revision receipt is missing")
    receipt = BulkRevisionReceipt.from_json_bytes(payload)
    if receipt.object_key != receipt_key:
        raise Institutional13FStorageError(
            "bulk revision key does not bind its identity"
        )
    read_verified_object(
        store, receipt.raw_object, maximum_bytes=HARD_MAX_RAW_EVIDENCE_BYTES
    )
    return receipt
