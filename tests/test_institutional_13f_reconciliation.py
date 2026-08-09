from __future__ import annotations

import hashlib

import pytest

from engine.institutional_census.reconciliation import (
    BulkRevisionReceipt,
    load_bulk_revision,
    publish_bulk_revision,
)
from engine.research_vault.r2_store import LocalStore


def test_bulk_revisions_are_immutable_hash_bound_and_idempotent(tmp_path):
    store = LocalStore(tmp_path / "store")
    payload = b"PK\x03\x04official-sec-bulk"
    first = publish_bulk_revision(
        store,
        window_start="2026-03-01",
        window_end="2026-05-31",
        source_url="https://www.sec.gov/files/form13f.zip",
        payload=payload,
        retained_at="2026-06-01T12:00:00Z",
        producer_version="test/1",
    )
    second = publish_bulk_revision(
        store,
        window_start="2026-03-01",
        window_end="2026-05-31",
        source_url="https://www.sec.gov/files/form13f.zip",
        payload=payload,
        retained_at="2026-06-05T12:00:00Z",
        producer_version="test/2",
    )
    assert first == second
    assert second.retained_at == "2026-06-01T12:00:00Z"
    assert second.producer_version == "test/1"
    assert first.raw_object.sha256 == hashlib.sha256(payload).hexdigest()
    assert load_bulk_revision(store, first.object_key) == first

    receipts = list(
        (tmp_path / "store" / "smart-money/13f/evidence/v1/bulk/windows").rglob(
            "*.json"
        )
    )
    assert receipts == [tmp_path / "store" / first.object_key]


def test_bulk_revision_receipt_rejects_identity_tamper(tmp_path):
    store = LocalStore(tmp_path / "store")
    receipt = publish_bulk_revision(
        store,
        window_start="2025-12-01",
        window_end="2026-02-28",
        source_url="https://www.sec.gov/files/form13f.zip",
        payload=b"PK\x03\x04revision-one",
        retained_at="2026-03-01T12:00:00Z",
        producer_version="test/1",
    )
    value = receipt.to_dict()
    value["source_url"] = "https://www.sec.gov/files/other.zip"
    with pytest.raises(ValueError, match="identity"):
        BulkRevisionReceipt(**value)


def test_distinct_sec_zip_refresh_is_a_distinct_immutable_revision(tmp_path):
    store = LocalStore(tmp_path / "store")
    common = {
        "store": store,
        "window_start": "2026-03-01",
        "window_end": "2026-05-31",
        "source_url": "https://www.sec.gov/files/form13f.zip",
        "retained_at": "2026-06-01T12:00:00Z",
        "producer_version": "test/1",
    }
    one = publish_bulk_revision(payload=b"PK\x03\x04one", **common)
    two = publish_bulk_revision(payload=b"PK\x03\x04two", **common)
    assert one.revision_id != two.revision_id
    assert one.object_key != two.object_key
