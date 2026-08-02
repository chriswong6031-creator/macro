"""Hermetic boundary tests for the dedicated BioCatalyst R2 adapter."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.biocatalyst.storage import (
    DedicatedR2Config,
    DedicatedR2Store,
    StorageError,
    mirror_bytes_verified,
)


class ProviderFailure(RuntimeError):
    """Minimal botocore-like failure with only the public response shape."""

    def __init__(self, *, code: str = "", status: int | str | None = None) -> None:
        self.response: dict[str, object] = {}
        if code:
            self.response["Error"] = {"Code": code}
        if status is not None:
            self.response["ResponseMetadata"] = {"HTTPStatusCode": status}
        super().__init__("provider detail must never escape")


class FakeBody:
    def __init__(self, value: object) -> None:
        self.value = value

    def read(self) -> object:
        return self.value


class FakeR2Client:
    def __init__(self, *, put_members: object = None) -> None:
        members = {"IfNoneMatch": object()} if put_members is None else put_members
        self.meta = SimpleNamespace(
            service_model=SimpleNamespace(
                operation_model=lambda name: SimpleNamespace(
                    input_shape=SimpleNamespace(members=members)
                )
            )
        )
        self.get_result: object = {"Body": FakeBody(b"payload")}
        self.put_result: object = None
        self.get_calls: list[dict[str, object]] = []
        self.put_calls: list[dict[str, object]] = []

    def get_object(self, **kwargs: object) -> object:
        self.get_calls.append(kwargs)
        if isinstance(self.get_result, BaseException):
            raise self.get_result
        return self.get_result

    def put_object(self, **kwargs: object) -> None:
        self.put_calls.append(kwargs)
        if isinstance(self.put_result, BaseException):
            raise self.put_result


def _config(endpoint: str = "https://r2.example.test") -> DedicatedR2Config:
    return DedicatedR2Config(
        endpoint=endpoint,
        bucket="biocatalyst-private",
        access_key_id="test-access",
        secret_access_key="test-secret",
    )


def _store(client: FakeR2Client | None = None) -> tuple[DedicatedR2Store, FakeR2Client]:
    fake = client or FakeR2Client()
    return DedicatedR2Store(_config(), client=fake), fake


@pytest.mark.parametrize(
    "endpoint",
    (
        "https://r2.example.test",
        "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com/",
    ),
)
def test_dedicated_r2_endpoint_accepts_only_a_root_https_authority(endpoint: str):
    _config(endpoint).validate()


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://r2.example.test",
        "https://operator:secret@r2.example.test",
        "https://r2.example.test/private-bucket",
        "https://r2.example.test/?redirect=elsewhere",
        "https://r2.example.test/#elsewhere",
        "https://r2.example.test:443",
        "https://r2.example.test:invalid",
        "https://r2.example.test\\unexpected",
    ),
)
def test_dedicated_r2_endpoint_rejects_ambiguous_or_non_r2_transport(endpoint: str):
    with pytest.raises(StorageError) as raised:
        _config(endpoint).validate()
    assert raised.value.code == "BIOCATALYST_R2_ENDPOINT_INVALID"


@pytest.mark.parametrize(
    "client",
    (
        FakeR2Client(put_members={}),
        object(),
    ),
)
def test_adapter_rejects_sdk_models_without_conditional_create_capability(client: object):
    with pytest.raises(StorageError) as raised:
        DedicatedR2Store(_config(), client=client)
    assert raised.value.code == "BIOCATALYST_R2_CONDITIONAL_CREATE_UNAVAILABLE"


def test_get_object_missing_key_or_404_is_a_clean_absence():
    store, client = _store()
    client.get_result = ProviderFailure(code="NoSuchKey")
    assert store.get_bytes("biocatalyst/raw/one.json") is None

    client.get_result = ProviderFailure(status="404")
    assert store.get_bytes("biocatalyst/raw/two.json") is None
    assert [call["Key"] for call in client.get_calls] == [
        "biocatalyst/raw/one.json",
        "biocatalyst/raw/two.json",
    ]


def test_get_object_transient_or_malformed_response_is_a_bounded_failure():
    store, client = _store()
    client.get_result = RuntimeError("https://sensitive-r2-endpoint.example internal detail")
    with pytest.raises(StorageError) as raised:
        store.get_bytes("biocatalyst/raw/one.json")
    assert raised.value.code == "BIOCATALYST_R2_READ_FAILED"
    assert "sensitive" not in str(raised.value)
    assert raised.value.__cause__ is None

    client.get_result = {"Body": FakeBody("not bytes")}
    with pytest.raises(StorageError) as malformed:
        store.get_bytes("biocatalyst/raw/two.json")
    assert malformed.value.code == "BIOCATALYST_R2_READ_FAILED"


@pytest.mark.parametrize(
    "failure",
    (
        ProviderFailure(code="ConditionalRequestConflict"),
        ProviderFailure(code="PreconditionFailed"),
        ProviderFailure(status=409),
        ProviderFailure(status="412"),
    ),
)
def test_conditional_create_maps_only_competing_immutable_writes_to_false(failure: ProviderFailure):
    store, client = _store()
    client.put_result = failure
    assert store.put_if_absent("biocatalyst/raw/one.json", b"evidence") is False
    assert client.put_calls == [{
        "Bucket": "biocatalyst-private",
        "Key": "biocatalyst/raw/one.json",
        "Body": b"evidence",
        "ContentType": "application/octet-stream",
        "IfNoneMatch": "*",
    }]


def test_conditional_create_transient_failure_is_bounded_and_non_secret():
    store, client = _store()
    client.put_result = RuntimeError("test-secret must not escape")
    with pytest.raises(StorageError) as raised:
        store.put_if_absent("biocatalyst/raw/one.json", b"evidence")
    assert raised.value.code == "BIOCATALYST_R2_CONDITIONAL_CREATE_FAILED"
    assert "test-secret" not in str(raised.value)
    assert raised.value.__cause__ is None


class SequencedObjectStore:
    def __init__(self, reads: list[bytes | None], *, create_result: bool) -> None:
        self._reads = reads
        self._create_result = create_result
        self.put_calls: list[tuple[str, bytes, str]] = []

    def get_bytes(self, key: str) -> bytes | None:
        return self._reads.pop(0)

    def put_if_absent(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> bool:
        self.put_calls.append((key, data, content_type))
        return self._create_result


def test_verified_mirror_reads_back_the_winner_after_a_conditional_race():
    fake = SequencedObjectStore([None, b"evidence"], create_result=False)
    receipt = mirror_bytes_verified(
        fake,
        object_key="biocatalyst/raw/one.json",
        payload=b"evidence",
        content_type="application/json",
    )
    assert receipt.object_key == "biocatalyst/raw/one.json"
    assert receipt.byte_count == len(b"evidence")
    assert fake.put_calls == [("biocatalyst/raw/one.json", b"evidence", "application/json")]


def test_verified_mirror_rejects_a_successful_put_without_exact_readback():
    fake = SequencedObjectStore([None, b"different writer"], create_result=True)
    with pytest.raises(StorageError) as raised:
        mirror_bytes_verified(
            fake,
            object_key="biocatalyst/raw/one.json",
            payload=b"evidence",
        )
    assert raised.value.code == "BIOCATALYST_R2_READBACK_MISMATCH"
