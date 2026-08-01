"""Tests for the private Filing Forensics gzip/local/R2 transport."""
from __future__ import annotations

import gzip
import json

import pytest

from engine.fundamental_forensics import private_state as ps


def _document(*, generated_at: str = "2026-08-01T12:00:00Z") -> dict:
    return {
        "schema": ps.STATE_SCHEMA,
        "generated_at": generated_at,
        "companies": {
            "AAPL": {
                "ticker": "AAPL",
                "findings": [{"detector_id": "receivables_stretch", "state": "clear"}],
            }
        },
    }


def _blob(document: dict | None = None) -> bytes:
    payload = json.dumps(document or _document(), sort_keys=True, separators=(",", ":"))
    return gzip.compress(payload.encode("utf-8"), mtime=0)


class _MemoryStore:
    def __init__(self, *, read_back: bytes | None = None, put_ok: bool = True):
        self.read_back = read_back
        self.put_ok = put_ok
        self.put_calls: list[tuple[str, bytes, str]] = []
        self.get_calls: list[str] = []

    def put_bytes(self, key: str, body: bytes, content_type: str) -> bool:
        self.put_calls.append((key, body, content_type))
        if self.read_back is None:
            self.read_back = body
        return self.put_ok

    def get_bytes(self, key: str) -> bytes | None:
        self.get_calls.append(key)
        return self.read_back


@pytest.fixture(autouse=True)
def _isolated_cache():
    ps.clear_state_cache()
    yield
    ps.clear_state_cache()


def test_decode_valid_gzip_returns_validated_document() -> None:
    document = _document()
    assert ps.decode_state_blob(_blob(document)) == document


@pytest.mark.parametrize(
    "payload",
    [
        b"not-a-gzip-stream",
        _blob({"schema": "wrong.v1", "generated_at": "now", "companies": {}}),
        _blob({"schema": ps.STATE_SCHEMA, "generated_at": "now", "companies": []}),
        _blob({"schema": ps.STATE_SCHEMA, "companies": {}}),
    ],
)
def test_decode_rejects_invalid_gzip_or_envelope(payload: bytes) -> None:
    with pytest.raises((OSError, ValueError, json.JSONDecodeError)):
        ps.decode_state_blob(payload)


def test_local_load_wins_without_opening_private_store(tmp_path) -> None:
    expected = _blob()
    path = ps.local_state_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(expected)

    def store_must_not_open():
        raise AssertionError("valid local state must win before R2")

    assert ps.load_state_blob(tmp_path, store_factory=store_must_not_open) == expected
    assert ps.load_state(tmp_path, store_factory=store_must_not_open) == _document()


def test_invalid_local_state_falls_through_to_valid_private_store(tmp_path) -> None:
    path = ps.local_state_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"broken")
    expected = _blob()
    store = _MemoryStore(read_back=expected)
    assert ps.load_state_blob(
        tmp_path,
        store_factory=lambda: store,
        cache_seconds=0,
    ) == expected
    assert store.get_calls == [ps.STATE_KEY]


def test_r2_load_validates_and_reuses_the_validated_cache(tmp_path) -> None:
    expected = _blob()
    store = _MemoryStore(read_back=expected)
    factory_calls = 0

    def factory():
        nonlocal factory_calls
        factory_calls += 1
        return store

    first = ps.load_state_blob(tmp_path, store_factory=factory, cache_seconds=60)
    second = ps.load_state_blob(tmp_path, store_factory=factory, cache_seconds=60)
    assert first == expected == second
    assert factory_calls == 1
    assert store.get_calls == [ps.STATE_KEY]


def test_publish_writes_private_key_and_verifies_read_back(tmp_path) -> None:
    expected = _blob()
    source = tmp_path / "state.json.gz"
    source.write_bytes(expected)
    store = _MemoryStore()

    assert ps.publish_state_blob(source, store_factory=lambda: store) is True
    assert store.put_calls == [(ps.STATE_KEY, expected, "application/gzip")]
    assert store.get_calls == [ps.STATE_KEY]


def test_publish_fails_closed_on_read_back_checksum_mismatch(tmp_path) -> None:
    expected = _blob()
    source = tmp_path / "state.json.gz"
    source.write_bytes(expected)
    different_valid_blob = _blob(_document(generated_at="2026-08-01T12:00:01Z"))
    store = _MemoryStore(read_back=different_valid_blob)

    assert ps.publish_state_blob(source, store_factory=lambda: store) is False
    assert store.put_calls == [(ps.STATE_KEY, expected, "application/gzip")]
    assert store.get_calls == [ps.STATE_KEY]


def test_publish_rejects_invalid_source_before_store_creation(tmp_path) -> None:
    source = tmp_path / "state.json.gz"
    source.write_bytes(b"not-gzip")

    def store_must_not_open():
        raise AssertionError("invalid source must fail before R2")

    assert ps.publish_state_blob(source, store_factory=store_must_not_open) is False
