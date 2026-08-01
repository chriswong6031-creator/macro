from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import engine.capital_structure.source_store as source_store_module
from engine.capital_structure.source_store import (
    ContentAddressedSourceStore,
    STORE_ID_DEDICATED_R2,
    STORE_ID_LOCAL,
    STORE_ID_RESEARCH_R2,
    STORE_ID_SHARED_R2,
    build_source_store,
    object_key_for_sha256,
)
from engine.research_vault.r2_store import LocalStore


FIXTURES = Path(__file__).parent / "fixtures" / "capital_structure" / "source_store"


class PutFailure:
    def put_bytes(self, key, data, content_type="application/octet-stream"):
        return False

    def get_bytes(self, key):
        return None


def test_content_addressed_write_readback_returns_verified_receipt(tmp_path):
    raw = (FIXTURES / "sample_filing.txt").read_bytes()
    local = LocalStore(tmp_path / "objects")
    store = ContentAddressedSourceStore(local, backend="local")
    receipt = store.put_verified(raw, media_type="text/plain")

    digest = sha256(raw).hexdigest()
    assert receipt is not None
    assert receipt.sha256 == digest
    assert receipt.object_key == f"capital_structure/sec/sha256/{digest[:2]}/{digest}"
    assert receipt.media_type == "text/plain"
    assert receipt.store_id == STORE_ID_LOCAL
    assert local.get_bytes(receipt.object_key) == raw


def test_changed_bytes_create_another_immutable_object(tmp_path):
    local = LocalStore(tmp_path / "objects")
    store = ContentAddressedSourceStore(local, backend="local")
    first = store.put_verified(b"first")
    second = store.put_verified(b"corrected bytes")

    assert first is not None and second is not None
    assert first.object_key != second.object_key
    assert local.get_bytes(first.object_key) == b"first"
    assert local.get_bytes(second.object_key) == b"corrected bytes"


def test_store_failure_defers_without_manifest_and_logs_reason(caplog):
    caplog.set_level("INFO")
    store = ContentAddressedSourceStore(
        PutFailure(), backend="r2", store_id=STORE_ID_SHARED_R2
    )
    result = store.put_verified(b"document")

    assert result is None
    assert "source-store defer" in caplog.text
    assert "put-failed" in caplog.text


def test_non_local_store_requires_explicit_stable_namespace():
    try:
        ContentAddressedSourceStore(PutFailure(), backend="r2")
    except ValueError as exc:
        assert "store_id" in str(exc)
    else:
        raise AssertionError("non-local source store accepted without store_id")


def test_object_key_rejects_non_sha256_values():
    try:
        object_key_for_sha256("not-a-hash")
    except ValueError:
        pass
    else:
        raise AssertionError("expected invalid digest to raise")


def test_verified_wrapper_returns_receipt_and_rejects_wrong_read_key(tmp_path):
    wrapper = ContentAddressedSourceStore(LocalStore(tmp_path / "objects"), backend="local")
    receipt = wrapper.put_verified(b"exact evidence", media_type="text/plain")
    assert receipt is not None
    assert receipt.backend == "local"
    assert receipt.store_id == STORE_ID_LOCAL
    assert receipt.byte_length == len(b"exact evidence")
    assert wrapper.get_verified(receipt.object_key, receipt.sha256) == b"exact evidence"
    assert wrapper.get_verified(receipt.object_key, "0" * 64) is None


def test_source_store_factory_is_explicit_local_or_none(tmp_path, monkeypatch):
    for name in (
        "CAPITAL_STRUCTURE_LOCAL_STORE", "R2_CAPITAL_STRUCTURE_BUCKET",
        "R2_CAPITAL_STRUCTURE_ENDPOINT", "R2_CAPITAL_STRUCTURE_ACCESS_KEY_ID",
        "R2_CAPITAL_STRUCTURE_SECRET_ACCESS_KEY", "R2_RESEARCH_BUCKET", "R2_BUCKET",
        "R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert build_source_store() is None
    monkeypatch.setenv("CAPITAL_STRUCTURE_LOCAL_STORE", str(tmp_path / "source-store"))
    wrapper = build_source_store()
    assert wrapper is not None
    assert wrapper.backend == "local"
    assert wrapper.store_id == STORE_ID_LOCAL


def test_dedicated_capital_structure_bucket_uses_dedicated_client(monkeypatch):
    sentinel = object()
    captured = {}

    class FakeR2Store:
        def __init__(self, bucket, client=None):
            captured.update(bucket=bucket, client=client)
            self.available = client is not None and bool(bucket)

    monkeypatch.delenv("CAPITAL_STRUCTURE_LOCAL_STORE", raising=False)
    monkeypatch.setenv("R2_CAPITAL_STRUCTURE_BUCKET", "capital-evidence")
    monkeypatch.setattr(source_store_module, "_capital_structure_r2_client", lambda: sentinel)
    monkeypatch.setattr(source_store_module, "R2Store", FakeR2Store)

    wrapper = build_source_store()

    assert wrapper is not None
    assert wrapper.backend == "r2"
    assert wrapper.store_id == STORE_ID_DEDICATED_R2
    assert captured == {"bucket": "capital-evidence", "client": sentinel}


def test_research_and_shared_bucket_fallbacks_have_distinct_store_ids(monkeypatch):
    calls = []
    sentinel = object()

    class FakeR2Store:
        def __init__(self, bucket, client=None):
            calls.append((bucket, client))
            self.available = True

    for name in (
        "CAPITAL_STRUCTURE_LOCAL_STORE",
        "R2_CAPITAL_STRUCTURE_BUCKET",
        "R2_RESEARCH_BUCKET",
        "R2_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(source_store_module, "R2Store", FakeR2Store)
    monkeypatch.setattr(source_store_module, "_shared_r2_client", lambda: sentinel)

    monkeypatch.setenv("R2_RESEARCH_BUCKET", "private-research")
    research = build_source_store()
    monkeypatch.delenv("R2_RESEARCH_BUCKET")
    monkeypatch.setenv("R2_BUCKET", "primary")
    shared = build_source_store()

    assert research is not None and research.store_id == STORE_ID_RESEARCH_R2
    assert shared is not None and shared.store_id == STORE_ID_SHARED_R2
    assert calls == [("private-research", None), ("primary", sentinel)]


def test_dedicated_r2_credentials_fall_back_per_field_to_shared(monkeypatch):
    captured = {}

    def fake_make_r2_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setenv("R2_CAPITAL_STRUCTURE_ENDPOINT", "https://capital.example")
    monkeypatch.delenv("R2_CAPITAL_STRUCTURE_ACCESS_KEY_ID", raising=False)
    monkeypatch.setenv("R2_CAPITAL_STRUCTURE_SECRET_ACCESS_KEY", "capital-secret")
    monkeypatch.setenv("R2_ENDPOINT", "https://shared.example")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "shared-access")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "shared-secret")
    monkeypatch.setattr(source_store_module, "_make_r2_client", fake_make_r2_client)

    source_store_module._capital_structure_r2_client()

    assert captured == {
        "endpoint": "https://capital.example",
        "access_key": "shared-access",
        "secret_key": "capital-secret",
    }
