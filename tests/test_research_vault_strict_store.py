"""Fail-closed object reads used by immutable research snapshot publication."""
from __future__ import annotations

import sys
from types import ModuleType
from pathlib import Path

import pytest

from engine.research_vault import r2_store as store_mod
from engine.research_vault.r2_store import LocalStore, R2Store, Store, StrictReadStore


class _Body:
    def __init__(self, payload: bytes | Exception):
        self.payload = payload

    def read(self) -> bytes:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class _FakeS3:
    def __init__(self, result: bytes | Exception):
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        self.calls.append((Bucket, Key))
        if isinstance(self.result, Exception):
            raise self.result
        return {"Body": _Body(self.result)}


def _install_fake_botocore(monkeypatch):
    """Install only the ``ClientError`` identity the production guard imports."""
    fake_botocore = ModuleType("botocore")
    fake_exceptions = ModuleType("botocore.exceptions")

    class FakeClientError(Exception):
        def __init__(self, code: str):
            super().__init__(code)
            self.response = {"Error": {"Code": code}}

    fake_exceptions.ClientError = FakeClientError
    fake_botocore.exceptions = fake_exceptions
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_exceptions)
    return FakeClientError


class _LegacyFailOpenStore:
    """The pre-strict structural shape used by existing fail-open consumers."""

    def get_bytes(self, key: str) -> bytes | None:
        return None

    def put_bytes(self, key: str, data: bytes,
                  content_type: str = "application/octet-stream") -> bool:
        return True

    def list_prefix(self, prefix: str) -> list[str]:
        return []

    def exists(self, key: str) -> bool:
        return False

    def upload_time(self, key: str) -> str | None:
        return None


def test_strict_read_protocol_preserves_legacy_store_runtime_compatibility(tmp_path):
    legacy = _LegacyFailOpenStore()
    local = LocalStore(tmp_path / "store")
    remote = R2Store("research", client=_FakeS3(b"payload"))

    assert isinstance(legacy, Store)
    assert not isinstance(legacy, StrictReadStore)
    assert isinstance(local, Store)
    assert isinstance(local, StrictReadStore)
    assert isinstance(remote, Store)
    assert isinstance(remote, StrictReadStore)


def test_local_strict_read_returns_bytes_or_authoritative_missing(tmp_path):
    store = LocalStore(tmp_path / "store")
    store.put_bytes("snapshots/one.json", b'{"version": 1}')

    assert store.get_bytes_strict("snapshots/one.json") == b'{"version": 1}'
    assert store.get_bytes_strict("snapshots/missing.json") is None


def test_local_strict_read_propagates_traversal_and_read_errors(tmp_path, monkeypatch):
    store = LocalStore(tmp_path / "store")
    with pytest.raises(ValueError, match="unsafe key"):
        store.get_bytes_strict("../escape.json")

    store.put_bytes("snapshots/one.json", b"payload")

    def denied(_path):
        raise PermissionError("read denied")

    monkeypatch.setattr(Path, "read_bytes", denied)
    with pytest.raises(PermissionError, match="read denied"):
        store.get_bytes_strict("snapshots/one.json")


def test_r2_strict_read_softens_only_explicit_client_not_found(monkeypatch):
    ClientError = _install_fake_botocore(monkeypatch)
    for code in ("404", "NoSuchKey", "NotFound"):
        store = R2Store("research", client=_FakeS3(ClientError(code)))
        assert store.get_bytes_strict("snapshots/one.json") is None


def test_r2_strict_read_returns_payload_and_propagates_other_failures(monkeypatch):
    ClientError = _install_fake_botocore(monkeypatch)
    client = _FakeS3(b"immutable bytes")
    store = R2Store("research", client=client)
    assert store.get_bytes_strict("snapshots/one.json") == b"immutable bytes"
    assert client.calls == [("research", "snapshots/one.json")]

    with pytest.raises(ClientError):
        R2Store("research", client=_FakeS3(ClientError("AccessDenied"))).get_bytes_strict(
            "snapshots/one.json")
    # The established read primitive remains deliberately fail-open for legacy
    # research ingestion callers; immutable snapshots opt into the strict one.
    assert R2Store("research", client=_FakeS3(ClientError("AccessDenied"))).get_bytes(
        "snapshots/one.json") is None
    with pytest.raises(OSError, match="network down"):
        R2Store("research", client=_FakeS3(OSError("network down"))).get_bytes_strict(
            "snapshots/one.json")
    with pytest.raises(RuntimeError, match="body failed"):
        R2Store("research", client=_FakeS3(RuntimeError("body failed"))).get_bytes_strict(
            "snapshots/one.json")


def test_r2_strict_read_rejects_unavailable_store(monkeypatch):
    monkeypatch.setattr(store_mod, "_r2_client", lambda: None)
    with pytest.raises(RuntimeError, match="unavailable"):
        R2Store("research").get_bytes_strict("snapshots/one.json")
