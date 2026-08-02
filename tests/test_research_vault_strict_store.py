"""Fail-closed object reads used by immutable research snapshot publication."""
from __future__ import annotations

import sys
from types import ModuleType
from pathlib import Path

import pytest

from engine.research_vault import r2_store as store_mod
from engine.research_vault.r2_store import (
    LocalStore,
    R2Store,
    Store,
    StrictBoundedReadStore,
    StrictReadStore,
)


class _Body:
    def __init__(self, payload: bytes | Exception):
        self.payload = payload
        self.offset = 0
        self.read_sizes: list[int | None] = []
        self.closed = False

    def read(self, maximum: int | None = None) -> bytes:
        self.read_sizes.append(maximum)
        if isinstance(self.payload, Exception):
            raise self.payload
        if maximum is None:
            content = self.payload[self.offset :]
            self.offset = len(self.payload)
            return content
        content = self.payload[self.offset : self.offset + maximum]
        self.offset += len(content)
        return content

    def close(self) -> None:
        self.closed = True


class _FakeS3:
    def __init__(self, result: bytes | Exception):
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        self.calls.append((Bucket, Key))
        if isinstance(self.result, Exception):
            raise self.result
        return {"Body": _Body(self.result)}


class _BoundedFakeS3:
    def __init__(self, payload: bytes | Exception, *, content_length: int | None = None):
        self.payload = payload
        self.content_length = content_length
        self.body: _Body | None = None

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        self.body = _Body(self.payload)
        result: dict[str, object] = {"Body": self.body}
        if self.content_length is not None:
            result["ContentLength"] = self.content_length
        return result


class _ShortChunkBody:
    def __init__(self, chunks: list[bytes]):
        self.chunks = list(chunks)
        self.read_sizes: list[int | None] = []
        self.closed = False

    def read(self, maximum: int | None = None) -> bytes:
        self.read_sizes.append(maximum)
        return self.chunks.pop(0) if self.chunks else b""

    def close(self) -> None:
        self.closed = True


class _BodyClient:
    def __init__(self, body, *, content_length: int | None = None):
        self.body = body
        self.content_length = content_length

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        result: dict[str, object] = {"Body": self.body}
        if self.content_length is not None:
            result["ContentLength"] = self.content_length
        return result


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
    assert isinstance(local, StrictBoundedReadStore)
    assert isinstance(remote, Store)
    assert isinstance(remote, StrictReadStore)
    assert isinstance(remote, StrictBoundedReadStore)


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

    real_open = store_mod.os.open

    def denied(path, flags, *args, **kwargs):
        if path == "one.json":
            raise PermissionError("read denied")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(store_mod.os, "open", denied)
    with pytest.raises(PermissionError, match="read denied"):
        store.get_bytes_strict("snapshots/one.json")


def test_local_strict_bounded_read_caps_before_buffering_and_keeps_missing_narrow(tmp_path):
    store = LocalStore(tmp_path / "store")
    store.put_bytes("snapshots/exact.bin", b"1234")
    store.put_bytes("snapshots/large.bin", b"12345")

    assert store.get_bytes_strict_bounded("snapshots/exact.bin", 4) == b"1234"
    assert store.get_bytes_strict_bounded("snapshots/missing.bin", 4) is None
    with pytest.raises(ValueError, match="bounded read limit"):
        store.get_bytes_strict_bounded("snapshots/large.bin", 4)
    with pytest.raises(ValueError, match="unsafe key"):
        store.get_bytes_strict_bounded("../escape.bin", 4)


def test_local_strict_reads_reject_symlinks_that_escape_store_root(tmp_path):
    store = LocalStore(tmp_path / "store")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside-secret")
    (store.root / "linked.bin").symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        store.get_bytes_strict("linked.bin")
    with pytest.raises(ValueError, match="symlink"):
        store.get_bytes_strict_bounded("linked.bin", 64)


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


def test_r2_strict_bounded_read_uses_header_then_max_plus_one_and_closes_body():
    exact_client = _BoundedFakeS3(b"1234", content_length=4)
    exact = R2Store("research", client=exact_client)
    assert exact.get_bytes_strict_bounded("snapshots/exact.bin", 4) == b"1234"
    assert exact_client.body is not None
    assert exact_client.body.read_sizes == [5, 1]
    assert exact_client.body.closed

    # A malicious/incorrect header cannot evade the streaming ``max + 1`` cap.
    lied_client = _BoundedFakeS3(b"12345", content_length=4)
    with pytest.raises(ValueError, match="bounded read limit"):
        R2Store("research", client=lied_client).get_bytes_strict_bounded(
            "snapshots/too-large.bin", 4
        )
    assert lied_client.body is not None
    assert lied_client.body.read_sizes == [5]
    assert lied_client.body.closed

    # An honest oversized header is rejected before body buffering, but the
    # response stream is still closed deterministically.
    announced_client = _BoundedFakeS3(b"12345", content_length=5)
    with pytest.raises(ValueError, match="bounded read limit"):
        R2Store("research", client=announced_client).get_bytes_strict_bounded(
            "snapshots/too-large.bin", 4
        )
    assert announced_client.body is not None
    assert announced_client.body.read_sizes == []
    assert announced_client.body.closed


def test_r2_strict_bounded_read_drains_short_chunks_before_accepting_exact_length():
    exact_body = _ShortChunkBody([b"12", b"34", b""])
    assert R2Store(
        "research", client=_BodyClient(exact_body, content_length=4)
    ).get_bytes_strict_bounded("snapshots/exact.bin", 4) == b"1234"
    assert exact_body.read_sizes == [5, 3, 1]
    assert exact_body.closed

    # The first short chunk equals the trusted object and hash prefix, but a
    # trailing byte still has to be observed before exact presence is claimed.
    trailing_body = _ShortChunkBody([b"1234", b"5"])
    with pytest.raises(ValueError, match="bounded read limit"):
        R2Store(
            "research", client=_BodyClient(trailing_body, content_length=4)
        ).get_bytes_strict_bounded("snapshots/trailing.bin", 4)
    assert trailing_body.read_sizes == [5, 1]
    assert trailing_body.closed


def test_r2_strict_reads_require_closeable_response_bodies():
    class NoCloseBody:
        def read(self, maximum=None):
            return b"payload"

    client = _BodyClient(NoCloseBody(), content_length=7)
    with pytest.raises(RuntimeError, match="not closeable"):
        R2Store("research", client=client).get_bytes_strict_bounded("snapshots/one.bin", 7)
    with pytest.raises(RuntimeError, match="not closeable"):
        R2Store("research", client=client).get_bytes_strict("snapshots/one.bin")


def test_r2_strict_bounded_read_rejects_oversized_chunks_and_pathological_fragmentation():
    class OversizedChunkBody:
        closed = False

        def read(self, maximum):
            return b"x" * (maximum + 1)

        def close(self):
            self.closed = True

    oversized = OversizedChunkBody()
    with pytest.raises(RuntimeError, match="more bytes than requested"):
        R2Store("research", client=_BodyClient(oversized)).get_bytes_strict_bounded(
            "snapshots/oversized-chunk.bin", 16
        )
    assert oversized.closed

    class OneByteBody:
        closed = False

        def read(self, maximum):
            return b"x"

        def close(self):
            self.closed = True

    fragmented = OneByteBody()
    with pytest.raises(RuntimeError, match="iteration limit"):
        R2Store("research", client=_BodyClient(fragmented)).get_bytes_strict_bounded(
            "snapshots/fragmented.bin", 16_384
        )
    assert fragmented.closed


def test_r2_strict_bounded_read_propagates_body_failure_after_closing():
    client = _BoundedFakeS3(RuntimeError("timeout"))
    with pytest.raises(RuntimeError, match="timeout"):
        R2Store("research", client=client).get_bytes_strict_bounded(
            "snapshots/one.bin", 16
        )
    assert client.body is not None
    assert client.body.read_sizes == [17]
    assert client.body.closed


def test_r2_strict_bounded_read_softens_only_authoritative_not_found(monkeypatch):
    ClientError = _install_fake_botocore(monkeypatch)
    assert R2Store("research", client=_FakeS3(ClientError("NoSuchKey"))).get_bytes_strict_bounded(
        "snapshots/missing.bin", 16
    ) is None
    with pytest.raises(ClientError):
        R2Store("research", client=_FakeS3(ClientError("AccessDenied"))).get_bytes_strict_bounded(
            "snapshots/forbidden.bin", 16
        )
