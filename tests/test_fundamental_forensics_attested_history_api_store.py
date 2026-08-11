"""Contracts for the dedicated, renewing, read-only attested-history reader.

The production receipt API used to build the generic Research Vault store, so
a successful seed into the DEDICATED attested-history bucket would have been
invisible to it.  These tests pin the replacement: only the four
``FF_ATTESTED_R2_READONLY_*`` values may address that bucket, the minted child
is always GET/HEAD-only under the single Fundamental Forensics prefix, the
child is renewed before it expires instead of being cached forever, and every
write or discovery call is a loud refusal rather than a possibility.

No real credential appears here.  Every value below is syntactically valid and
deliberately fake.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
import threading
import time

import pytest

pytest.importorskip("fastapi", reason="attested history store tests exercise the API route")
pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.forensics as forensics_api  # noqa: E402
from engine.fundamental_forensics.attested_history_credentials import (  # noqa: E402
    R2_ATTESTED_HISTORY_PREFIX,
    R2TemporaryCredentialError,
    R2TemporaryCredentials,
)
from engine.fundamental_forensics.attested_history_store import (  # noqa: E402
    ATTESTED_HISTORY_ENV_NAMES,
    AttestedHistoryStoreError,
    DedicatedAttestedHistoryStore,
    build_attested_history_store,
)
from engine.research_vault.r2_store import (  # noqa: E402
    StrictBoundedReadStore,
    StrictConditionalWriteStore,
)


ROOT = Path(__file__).resolve().parents[1]

# Fake but format-valid: the host matches the account-ID endpoint pattern, the
# access key matches ^[A-Za-z0-9]{16,128}$, and the bucket matches R2's name rule.
FAKE_ENDPOINT = "https://00112233445566778899aabbccddeeff.r2.cloudflarestorage.com"
FAKE_ACCESS_KEY_ID = "FAKEREADONLYACCESSKEY0123456789"
FAKE_SECRET_ACCESS_KEY = "fake-parent-secret-value-for-tests-only"
FAKE_BUCKET = "attested-history-test"
FAKE_ENV = {
    "FF_ATTESTED_R2_READONLY_ENDPOINT": FAKE_ENDPOINT,
    "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID": FAKE_ACCESS_KEY_ID,
    "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY": FAKE_SECRET_ACCESS_KEY,
    "FF_ATTESTED_R2_READONLY_BUCKET": FAKE_BUCKET,
}
RECEIPT_BYTES = b'{"receipt":"bytes"}'
PRIVATE_HEADERS = {
    "cache-control": "private, no-store",
    "vary": "Authorization",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, noarchive",
}


class _Clock:
    """An injectable monotonic-enough clock the test moves by hand."""

    def __init__(self, value: float) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value


class _FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._offset = 0
        self.closed = False

    def read(self, size: int | None = None) -> bytes:
        if size is None:
            chunk = self._payload[self._offset :]
        else:
            chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


class _FakeS3Client:
    """The narrowest S3 surface R2Store's bounded reads actually touch."""

    def __init__(self, payload: bytes = RECEIPT_BYTES) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict]] = []

    def get_object(self, **kwargs):
        self.calls.append(("get_object", dict(kwargs)))
        return {
            "ContentLength": len(self.payload),
            "ETag": '"fake-etag"',
            "Body": _FakeBody(self.payload),
        }

    def head_object(self, **kwargs):
        self.calls.append(("head_object", dict(kwargs)))
        return {"ContentLength": len(self.payload), "ETag": '"fake-etag"'}


class _RecordingClientFactory:
    def __init__(self, payload: bytes = RECEIPT_BYTES) -> None:
        self.payload = payload
        self.calls: list[dict] = []
        self.clients: list[_FakeS3Client] = []

    def __call__(self, **kwargs) -> _FakeS3Client:
        self.calls.append(dict(kwargs))
        client = _FakeS3Client(self.payload)
        self.clients.append(client)
        return client


class _RecordingMinter:
    """A minter whose expiry follows the injected clock, not wall time."""

    def __init__(self, clock: _Clock, *, delay: float = 0.0) -> None:
        self._clock = clock
        self._delay = delay
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def __call__(self, **kwargs) -> R2TemporaryCredentials:
        if self._delay:
            time.sleep(self._delay)
        with self._lock:
            self.calls.append(dict(kwargs))
            index = len(self.calls)
        return R2TemporaryCredentials(
            access_key_id=kwargs["parent_access_key_id"],
            secret_access_key=f"fake-child-secret-{index}",
            session_token=f"fake-child-token-{index}",
            expires_at=int(self._clock()) + int(kwargs["ttl_seconds"]),
        )


def _explode(*_args, **_kwargs):
    raise AssertionError("the dedicated attested-history reader must not reach storage here")


def _store(
    *,
    clock: _Clock | None = None,
    minter=None,
    client_factory=None,
    **overrides,
) -> DedicatedAttestedHistoryStore:
    the_clock = clock if clock is not None else _Clock(1_800_000_000)
    kwargs = {
        "endpoint": FAKE_ENDPOINT,
        "parent_access_key_id": FAKE_ACCESS_KEY_ID,
        "parent_secret_access_key": FAKE_SECRET_ACCESS_KEY,
        "bucket": FAKE_BUCKET,
        "clock": the_clock,
        "minter": minter if minter is not None else _RecordingMinter(the_clock),
        "client_factory": client_factory if client_factory is not None else _RecordingClientFactory(),
    }
    kwargs.update(overrides)
    return DedicatedAttestedHistoryStore(**kwargs)


def _entitled_client() -> TestClient:
    app = FastAPI()
    app.include_router(forensics_api.router)
    app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    return TestClient(app)


# ---------------------------------------------------------------------------
# (a) missing configuration is an absent store, never a partial one
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing", ATTESTED_HISTORY_ENV_NAMES)
def test_any_missing_dedicated_value_yields_no_store(missing) -> None:
    partial = dict(FAKE_ENV)
    partial.pop(missing)
    assert build_attested_history_store(env=partial) is None
    blank = dict(FAKE_ENV)
    blank[missing] = ""
    assert build_attested_history_store(env=blank) is None


def test_all_absent_dedicated_values_yield_no_store(monkeypatch) -> None:
    assert build_attested_history_store(env={}) is None
    for name in ATTESTED_HISTORY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    assert build_attested_history_store() is None


# ---------------------------------------------------------------------------
# (b) no fallback: the Research Vault store is never reachable from this lane
# ---------------------------------------------------------------------------

def test_dedicated_reader_never_falls_back_to_research_vault_credentials(
    monkeypatch, tmp_path
) -> None:
    from engine.research_vault import r2_store

    monkeypatch.setattr(r2_store, "build_store", _explode)
    for name in ATTESTED_HISTORY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    # Every generic credential a fallback could have latched onto is present
    # and valid-looking.  None of them addresses the attested-history bucket.
    monkeypatch.setenv("R2_RESEARCH_ENDPOINT", FAKE_ENDPOINT)
    monkeypatch.setenv("R2_RESEARCH_ACCESS_KEY_ID", FAKE_ACCESS_KEY_ID)
    monkeypatch.setenv("R2_RESEARCH_SECRET_ACCESS_KEY", FAKE_SECRET_ACCESS_KEY)
    monkeypatch.setenv("R2_RESEARCH_BUCKET", "research-vault-must-not-be-used")
    monkeypatch.setenv("R2_ENDPOINT", FAKE_ENDPOINT)
    monkeypatch.setenv("R2_ACCESS_KEY_ID", FAKE_ACCESS_KEY_ID)
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", FAKE_SECRET_ACCESS_KEY)
    monkeypatch.setenv("RESEARCH_LOCAL_STORE", str(tmp_path))

    assert build_attested_history_store() is None

    forensics_api._reset_store_cache()
    try:
        built = forensics_api._build_store()
        # Assert the TYPE, not merely falsiness.  app/forensics.py catches
        # Exception broadly, so the _explode tripwire above cannot by itself
        # fail this test: a fallback that RETURNS a store (LocalStore via
        # RESEARCH_LOCAL_STORE, or an R2Store on the Research Vault bucket)
        # would sail past `is None`.  Only this admits nothing but the
        # dedicated reader.
        assert built is None or isinstance(built, DedicatedAttestedHistoryStore), (
            f"the receipt API built a {type(built).__name__} — the only store it may "
            "ever construct is the dedicated attested-history reader"
        )
        assert built is None
        with _entitled_client() as client:
            response = client.get("/api/forensics/v1/attested-history/latest")
        assert response.status_code == 503
        assert response.json() == {"detail": "attested query history temporarily unavailable"}
        for name, expected in PRIVATE_HEADERS.items():
            assert response.headers[name] == expected
    finally:
        forensics_api._reset_store_cache()


def test_store_module_does_not_import_the_research_vault_factory() -> None:
    """Prose may NAME the refused fallback; executable code may not reach it."""
    import ast

    path = ROOT / "engine" / "fundamental_forensics" / "attested_history_store.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert "engine.research_vault.r2_store.build_store" not in imported
    assert {name for name in imported if name.startswith("engine.research_vault")} == {
        "engine.research_vault.r2_store.R2Store",
        "engine.research_vault.r2_store.StrictBoundedReadStore",
    }
    identifiers = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert "build_store" not in identifiers
    # Only the four dedicated names may appear as env-variable string literals;
    # prose in the docstring is not an executable lookup.
    env_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.isupper()
        and node.value.replace("_", "").isalnum()
    }
    assert env_literals == set(ATTESTED_HISTORY_ENV_NAMES), env_literals


def test_forensics_api_no_longer_references_the_research_vault_store() -> None:
    source = (ROOT / "app" / "forensics.py").read_text(encoding="utf-8")
    assert "engine.research_vault" not in source
    assert "r2_store" not in source
    assert "build_attested_history_store" in source


# ---------------------------------------------------------------------------
# (c) present-but-unusable configuration fails closed before any client exists
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("FF_ATTESTED_R2_READONLY_BUCKET", "Attested_History", "bucket"),
        ("FF_ATTESTED_R2_READONLY_BUCKET", "../escape", "bucket"),
        ("FF_ATTESTED_R2_READONLY_ENDPOINT", "https://example.com", "endpoint"),
        (
            "FF_ATTESTED_R2_READONLY_ENDPOINT",
            "http://00112233445566778899aabbccddeeff.r2.cloudflarestorage.com",
            "endpoint",
        ),
        ("FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID", "short", "access key"),
    ],
)
def test_invalid_dedicated_values_fail_closed_without_constructing_a_client(
    name, value, message
) -> None:
    env = dict(FAKE_ENV)
    env[name] = value
    with pytest.raises(AttestedHistoryStoreError, match=message):
        build_attested_history_store(env=env)


def test_invalid_bucket_never_reaches_the_minter_or_the_client_factory() -> None:
    with pytest.raises(AttestedHistoryStoreError, match="bucket"):
        _store(bucket="NOT A BUCKET", minter=_explode, client_factory=_explode)


def test_refresh_margin_must_stay_inside_the_child_lifetime() -> None:
    with pytest.raises(AttestedHistoryStoreError, match="refresh margin"):
        _store(ttl_seconds=600, refresh_margin_seconds=600)
    with pytest.raises(AttestedHistoryStoreError, match="TTL"):
        _store(ttl_seconds=30 * 60 + 1)


# ---------------------------------------------------------------------------
# (d) denied mutation and discovery
# ---------------------------------------------------------------------------

def test_every_write_and_discovery_method_is_refused_without_touching_storage() -> None:
    store = _store(minter=_explode, client_factory=_explode)
    for call in (
        lambda: store.get_bytes("k"),
        lambda: store.get_bytes_strict("k"),
        lambda: store.list_prefix("fundamental_forensics/"),
        lambda: store.exists("k"),
        lambda: store.upload_time("k"),
    ):
        with pytest.raises(AttestedHistoryStoreError):
            call()
    assert store.write_attempts == 0

    with pytest.raises(AttestedHistoryStoreError, match="storage write"):
        store.put_bytes("k", b"x")
    assert store.write_attempts == 1
    with pytest.raises(AttestedHistoryStoreError, match="storage delete"):
        store.delete("k")
    assert store.write_attempts == 2


def test_reader_is_structurally_excluded_from_the_conditional_write_protocol() -> None:
    """Absence — not a raise — is what keeps this store out of the write gates.

    ``StrictConditionalWriteStore`` is a runtime-checkable Protocol, so merely
    DEFINING its three members (even bodies that raise) would make
    ``isinstance`` return True.  Six production sites read that check as "may
    this store write?" — source_sync.py:1018/:1220, query_snapshots.py:1287,
    attested_query_snapshots.py:2516 (the Wave 1 publication path), and
    seed_fundamental_forensics_attested_history.py:682/:823.  This test fails
    the moment someone re-adds one of the three as a convenience stub.
    """
    store = _store(minter=_explode, client_factory=_explode)

    assert isinstance(store, StrictBoundedReadStore)
    assert not isinstance(store, StrictConditionalWriteStore)

    for absent in (
        "get_bytes_strict_bounded_versioned",
        "validate_strict_conditional_write_capability",
        "put_bytes_strict_conditional",
    ):
        assert not hasattr(store, absent), (
            f"{absent} must stay ABSENT: defining it, even to raise, re-admits "
            "this read-only store to every StrictConditionalWriteStore gate"
        )


def test_repr_and_str_cannot_leak_the_parent_credential() -> None:
    store = _store()
    for rendered in (repr(store), str(store), f"{store}"):
        assert FAKE_SECRET_ACCESS_KEY not in rendered
        assert FAKE_ACCESS_KEY_ID not in rendered
        assert FAKE_BUCKET in rendered


# ---------------------------------------------------------------------------
# (e) the minted child is always read-only on the one prefix
# ---------------------------------------------------------------------------

def test_minted_child_is_read_only_on_the_fundamental_forensics_prefix() -> None:
    clock = _Clock(1_800_000_000)
    minter = _RecordingMinter(clock)
    factory = _RecordingClientFactory()
    store = _store(clock=clock, minter=minter, client_factory=factory)
    assert store.get_bytes_strict_bounded("fundamental_forensics/latest.json", 64) == RECEIPT_BYTES
    assert len(minter.calls) == 1
    call = minter.calls[0]
    assert call["scope"] == "object-read-only"
    assert list(call["actions"]) == ["GetObject", "HeadObject"]
    assert "PutObject" not in list(call["actions"])
    assert call["prefix"] == R2_ATTESTED_HISTORY_PREFIX == "fundamental_forensics/"
    assert call["bucket"] == FAKE_BUCKET
    assert call["endpoint"] == FAKE_ENDPOINT
    assert call["ttl_seconds"] <= 30 * 60


def test_default_minter_signs_a_read_only_child_jwt() -> None:
    """End-to-end through the real signer: the token itself must be narrow."""
    factory = _RecordingClientFactory()
    # No ``minter=``: this exercises the module default, the real local signer.
    store = DedicatedAttestedHistoryStore(
        endpoint=FAKE_ENDPOINT,
        parent_access_key_id=FAKE_ACCESS_KEY_ID,
        parent_secret_access_key=FAKE_SECRET_ACCESS_KEY,
        bucket=FAKE_BUCKET,
        client_factory=factory,
    )
    assert store.get_bytes_strict_bounded("fundamental_forensics/latest.json", 64) == RECEIPT_BYTES
    token = factory.calls[0]["session_token"]
    signed = base64.b64decode(token).decode("ascii").removeprefix("jwt/")
    segment = signed.split(".")[1]
    payload = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
    assert payload["scope"] == "object-read-only"
    assert payload["actions"] == ["GetObject", "HeadObject"]
    assert payload["paths"] == {"objectPaths": [], "prefixPaths": ["fundamental_forensics/"]}
    assert payload["bucket"] == FAKE_BUCKET
    assert payload["exp"] - payload["iat"] <= 30 * 60


# ---------------------------------------------------------------------------
# (f)/(g) renewal: before expiry, exactly once per crossing
# ---------------------------------------------------------------------------

def test_child_is_renewed_exactly_once_per_expiry_crossing() -> None:
    clock = _Clock(1_700_000_000)
    minter = _RecordingMinter(clock)
    factory = _RecordingClientFactory()
    store = _store(
        clock=clock,
        minter=minter,
        client_factory=factory,
        ttl_seconds=1_800,
        refresh_margin_seconds=300,
    )

    assert store.get_bytes_strict_bounded("k", 64) == RECEIPT_BYTES
    assert store.child_expires_at == 1_700_001_800
    assert store.refresh_count == 0
    assert len(minter.calls) == 1
    assert len(factory.clients) == 1

    # One tick before (expiry - margin): the same child and the same client.
    clock.value = 1_700_001_499.0
    assert store.get_bytes_strict_bounded("k", 64) == RECEIPT_BYTES
    assert len(minter.calls) == 1
    assert len(factory.clients) == 1
    assert store.refresh_count == 0

    # At (expiry - margin): a new child and a NEW client.
    clock.value = 1_700_001_500.0
    assert store.get_bytes_strict_bounded("k", 64) == RECEIPT_BYTES
    assert len(minter.calls) == 2
    assert len(factory.clients) == 2
    assert store.refresh_count == 1
    assert store.child_expires_at == 1_700_003_300
    assert factory.clients[1].calls, "the read must use the renewed client"

    # Still inside the NEW window: the crossing is not re-counted per read.
    for _ in range(5):
        assert store.get_bytes_strict_bounded("k", 64) == RECEIPT_BYTES
    assert len(minter.calls) == 2
    assert store.refresh_count == 1


def test_many_reads_inside_the_validity_window_mint_exactly_once() -> None:
    clock = _Clock(1_700_000_000)
    minter = _RecordingMinter(clock)
    factory = _RecordingClientFactory()
    store = _store(clock=clock, minter=minter, client_factory=factory)
    for offset in range(0, 1_200, 100):
        clock.value = 1_700_000_000 + offset
        assert store.get_bytes_strict_bounded("k", 64) == RECEIPT_BYTES
    assert len(minter.calls) == 1
    assert len(factory.clients) == 1
    assert store.refresh_count == 0


# ---------------------------------------------------------------------------
# (h) concurrent cold start mints once
# ---------------------------------------------------------------------------

def test_concurrent_cold_reads_mint_exactly_one_child() -> None:
    clock = _Clock(1_700_000_000)
    minter = _RecordingMinter(clock, delay=0.02)
    factory = _RecordingClientFactory()
    store = _store(clock=clock, minter=minter, client_factory=factory)
    results: list[bytes | None] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def read() -> None:
        try:
            barrier.wait(timeout=5)
            results.append(store.get_bytes_strict_bounded("k", 64))
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=read) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert results == [RECEIPT_BYTES] * 8
    assert len(minter.calls) == 1
    assert len(factory.clients) == 1
    assert store.refresh_count == 0


def test_reads_run_concurrently_because_the_lock_is_not_held_across_the_get() -> None:
    """The renewal lock must cover the mint ONLY, never the network read.

    This is the load-bearing performance property of the whole adapter: this
    store sits on a request path, so holding ``self._lock`` across the boto3
    GET would serialize every receipt request in the process behind one mutex.
    Folding the call at the end of ``get_bytes_strict_bounded`` into
    ``_active_backing``'s ``with`` block looks like a harmless simplification
    and every other test in this file still passes when you make it — so
    without this test, nothing catches it.
    """
    entered = threading.Semaphore(0)
    release = threading.Event()
    peak = {"current": 0, "max": 0}
    guard = threading.Lock()

    class _BlockingClient(_FakeS3Client):
        def get_object(self, **kwargs):
            with guard:
                peak["current"] += 1
                peak["max"] = max(peak["max"], peak["current"])
            entered.release()
            release.wait(timeout=5)
            with guard:
                peak["current"] -= 1
            return super().get_object(**kwargs)

    class _BlockingFactory(_RecordingClientFactory):
        def __call__(self, **kwargs) -> _FakeS3Client:
            self.calls.append(dict(kwargs))
            client = _BlockingClient(self.payload)
            self.clients.append(client)
            return client

    store = _store(client_factory=_BlockingFactory())
    # Warm the credential so all three threads race on the READ, not the mint.
    store.get_bytes_strict_bounded("warm", 64)

    errors: list[BaseException] = []

    def read() -> None:
        try:
            store.get_bytes_strict_bounded("k", 64)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=read) for _ in range(3)]
    for thread in threads:
        thread.start()
    for _ in range(3):
        assert entered.acquire(timeout=5), (
            "readers did not all reach get_object: the renewal lock is being held "
            "across the network read, which serializes every receipt request"
        )
    release.set()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert peak["max"] == 3


def test_a_failed_refresh_keeps_the_previous_child_and_recovers() -> None:
    """A mint that raises mid-refresh must not strand the store."""
    clock = _Clock(1_700_000_000)
    working = _RecordingMinter(clock)
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise R2TemporaryCredentialError("transient signing failure")
        return working(**kwargs)

    factory = _RecordingClientFactory()
    store = _store(clock=clock, minter=flaky, client_factory=factory)
    assert store.get_bytes_strict_bounded("k", 64) == RECEIPT_BYTES
    first_expiry = store.child_expires_at

    clock.value = 1_700_000_000 + 1_800 - 300  # cross the refresh boundary
    with pytest.raises(AttestedHistoryStoreError):
        store.get_bytes_strict_bounded("k", 64)
    # The previous child survives the failure rather than being torn down.
    assert store.child_expires_at == first_expiry
    assert store.refresh_count == 0

    # And the very next call recovers instead of staying broken forever.
    assert store.get_bytes_strict_bounded("k", 64) == RECEIPT_BYTES
    assert store.refresh_count == 1


def test_a_child_expiry_from_a_foreign_clock_is_refused() -> None:
    """Expiry is range-checked, not merely type-checked.

    If the minter answers on a different clock than the store's, the freshness
    comparison degrades into either "re-mint every read" or "never re-mint
    again" — the latter serving an expired token silently.
    """
    clock = _Clock(1_700_000_000)

    def foreign(**kwargs):
        del kwargs
        return R2TemporaryCredentials(
            access_key_id=FAKE_ACCESS_KEY_ID,
            secret_access_key="fake-child-secret",
            session_token="fake-child-token",
            expires_at=1_900_000_000,  # wall-clock epoch, not this store's clock
        )

    store = _store(clock=clock, minter=foreign, client_factory=_explode)
    with pytest.raises(AttestedHistoryStoreError, match="child expiry is invalid"):
        store.get_bytes_strict_bounded("k", 64)


def test_a_non_epoch_clock_is_refused_before_a_child_is_minted() -> None:
    """The minted child is a JWT R2 validates against real wall-clock time.

    Swapping the default clock to ``time.monotonic`` keeps every renewal test
    green — the store and the minter would agree with each other — while
    minting an ``exp`` claim Cloudflare rejects, which presents as a total
    receipt-route outage misdiagnosed as bad credentials.  Fail loudly instead.
    """
    store = _store(clock=_Clock(12_345.0), minter=_explode, client_factory=_explode)
    with pytest.raises(AttestedHistoryStoreError, match="not epoch seconds"):
        store.get_bytes_strict_bounded("k", 64)


def test_a_zero_refresh_margin_is_refused() -> None:
    """A zero margin hands out a credential that expires during the request."""
    with pytest.raises(AttestedHistoryStoreError, match="refresh margin is invalid"):
        _store(refresh_margin_seconds=0)


def test_minted_credentials_never_render_their_secret_or_token() -> None:
    """A frozen dataclass renders every field by default.

    One `log.warning("%s", creds)`, one pytest assertion diff, or one traceback
    frame holding this object would otherwise print the derived child secret
    and the entire signed JWT. The access key ID and expiry stay visible
    because those are what a diagnosis needs.
    """
    creds = R2TemporaryCredentials(
        access_key_id=FAKE_ACCESS_KEY_ID,
        secret_access_key="child-secret-must-not-render",
        session_token="jwt/signed-token-must-not-render",
        expires_at=1_700_001_800,
    )
    for rendered in (repr(creds), str(creds), f"{creds}", "%s" % (creds,)):
        assert "child-secret-must-not-render" not in rendered
        assert "signed-token-must-not-render" not in rendered
    assert FAKE_ACCESS_KEY_ID in repr(creds)
    assert "1700001800" in repr(creds).replace("_", "")
    # Excluded from repr, never from the object.
    assert creds.secret_access_key == "child-secret-must-not-render"
    assert creds.session_token == "jwt/signed-token-must-not-render"


def test_a_none_client_from_the_factory_is_refused() -> None:
    """A factory returning None must fail closed, never inherit ambient creds.

    `R2Store.__init__` (r2_store.py:257) is
    `self._s3 = client if client is not None else _r2_client()`, and
    `_r2_client()` reads R2_RESEARCH_* / generic R2_*.  So handing R2Store a
    None client silently reopens the exact Research Vault fallback this whole
    module exists to make impossible.
    """
    store = _store(client_factory=lambda **_kwargs: None)
    with pytest.raises(AttestedHistoryStoreError, match="returned no client"):
        store.get_bytes_strict_bounded("k", 64)


def test_configuration_failures_are_distinguishable_in_the_log(monkeypatch, caplog) -> None:
    """Five different misconfigurations must not collapse into one line.

    The store is cached as absent, so the route 503s until the process
    restarts.  If every cause logs identically the operator cannot tell which
    of the four delivered values is wrong.
    """
    import logging

    seen = {}
    for name, bad in (
        ("FF_ATTESTED_R2_READONLY_ENDPOINT", "https://not-an-r2-host.example.com"),
        ("FF_ATTESTED_R2_READONLY_BUCKET", "Not_A_Valid_Bucket"),
        ("FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID", "!!invalid!!"),
    ):
        for env_name, value in FAKE_ENV.items():
            monkeypatch.setenv(env_name, value)
        monkeypatch.setenv(name, bad)
        forensics_api._reset_store_cache()
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="fundamental_forensics.api"):
            assert forensics_api._build_store() is None
        seen[name] = " ".join(r.getMessage() for r in caplog.records)
        forensics_api._reset_store_cache()

    assert len(set(seen.values())) == 3, f"causes are indistinguishable: {seen}"
    for name, message in seen.items():
        assert "unavailable:" in message, f"{name} logged no cause: {message}"
        # A cause may be named, but never a delivered VALUE.
        assert FAKE_SECRET_ACCESS_KEY not in message
        assert FAKE_ACCESS_KEY_ID not in message


def test_absent_configuration_logs_the_missing_names_and_never_a_value(
    monkeypatch, caplog
) -> None:
    """A half-delivered credential set must name what is missing.

    The deploy workflow strips all four FF_ATTESTED_R2_READONLY_* lines and
    re-adds only the non-empty ones, so one dispatch mid-rotation can leave a
    partial set behind and a permanently 503-ing route.
    """
    import logging

    for env_name, value in FAKE_ENV.items():
        monkeypatch.setenv(env_name, value)
    monkeypatch.delenv("FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY", raising=False)
    forensics_api._reset_store_cache()
    caplog.clear()
    try:
        with caplog.at_level(logging.WARNING, logger="fundamental_forensics.api"):
            assert forensics_api._build_store() is None
        message = " ".join(r.getMessage() for r in caplog.records)
        assert "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY" in message
        assert "not configured" in message
        # Names only. The three values that ARE present must not be echoed.
        assert FAKE_SECRET_ACCESS_KEY not in message
        assert FAKE_ACCESS_KEY_ID not in message
        assert FAKE_BUCKET not in message
        assert FAKE_ENDPOINT not in message
    finally:
        forensics_api._reset_store_cache()


def test_a_non_credential_mint_failure_still_raises_the_advertised_error() -> None:
    """The class advertises one error type; every mint path must honour it."""

    def broken(**kwargs):
        del kwargs
        raise RuntimeError("boto internals blew up")

    store = _store(minter=broken, client_factory=_explode)
    with pytest.raises(AttestedHistoryStoreError, match="could not be minted"):
        store.get_bytes_strict_bounded("k", 64)


# ---------------------------------------------------------------------------
# (i)/(j) protocol admission and verbatim bounded-read forwarding
# ---------------------------------------------------------------------------

def test_store_satisfies_the_strict_bounded_read_protocol() -> None:
    assert isinstance(_store(), StrictBoundedReadStore)


class _S3OverBackingStore:
    """Serve a populated store's objects through the S3 surface R2Store uses."""

    def __init__(self, backing) -> None:
        self.backing = backing
        self.keys_read: list[str] = []

    def _fetch(self, key: str) -> bytes | None:
        # Read generously here; R2Store and the reader enforce the real bounds
        # above this layer, and this fake must not become a second ceiling.
        return self.backing.get_bytes_strict_bounded(key, 64 * 1024 * 1024)

    def get_object(self, **kwargs):
        key = kwargs["Key"]
        self.keys_read.append(key)
        payload = self._fetch(key)
        if payload is None:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"ContentLength": len(payload), "ETag": '"e"', "Body": _FakeBody(payload)}

    def head_object(self, **kwargs):
        payload = self._fetch(kwargs["Key"])
        if payload is None:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(payload), "ETag": '"e"'}


def test_the_real_receipt_reader_resolves_a_snapshot_through_this_adapter(
    monkeypatch, tmp_path
) -> None:
    """End-to-end: the production read path, not just protocol admission.

    Every other test in this file drives the adapter directly, and the route
    tests exercise an ABSENT store. `isinstance(store, StrictBoundedReadStore)`
    passing is NOT the same as the reader working: a signature mismatch, a
    swapped bounded-read mode, or a None-vs-raise difference would satisfy the
    protocol and still break serving. This publishes a real `ffqsv2_` snapshot
    with the reader suite's own fixture and resolves it back through the
    adapter.
    """
    pytest.importorskip("botocore")
    import sys

    from engine.fundamental_forensics.attested_query_snapshots import (
        load_attested_query_receipt_index,
    )

    # Reuse the reader suite's publication fixture regardless of pytest's
    # import mode, matching tests/test_dashboard_news_i18n.py's idiom.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_fundamental_forensics_attested_history_reader import (  # noqa: E402
        _published,
    )

    backing, snapshot = _published(monkeypatch, tmp_path)
    s3 = _S3OverBackingStore(backing)
    clock = _Clock(1_700_000_000)
    store = _store(
        clock=clock,
        minter=_RecordingMinter(clock),
        client_factory=lambda **_kwargs: s3,
    )

    index = load_attested_query_receipt_index(store)

    assert index.snapshot_id == snapshot.snapshot_id
    assert s3.keys_read, "the reader never reached storage through the adapter"

    # R2Store's contract: None means ONLY an authoritative 404; anything else
    # raises. If the adapter converted a raise into a None, a tampered or
    # unreachable object would read as "receipt absent" — a silent failure of
    # exactly the kind this receipt chain exists to prevent.
    assert store.get_bytes_strict_bounded(f"{R2_ATTESTED_HISTORY_PREFIX}absent", 64) is None


def test_the_production_client_factory_builds_against_the_dedicated_endpoint() -> None:
    """Smoke-test the ONE code path every other test replaces with a fake.

    `_default_client_factory` is injected away everywhere else, so a typo in
    its `Config(...)` or `boto3.client(...)` keywords would surface only on the
    VPS, as an unbounded 503 nobody can attribute.
    """
    boto3 = pytest.importorskip("boto3")
    del boto3
    from engine.fundamental_forensics.attested_history_store import (
        _default_client_factory,
    )

    client = _default_client_factory(
        endpoint=FAKE_ENDPOINT,
        access_key_id=FAKE_ACCESS_KEY_ID,
        secret_access_key="fake-child-secret",
        session_token="fake-child-token",
    )
    assert client.meta.endpoint_url == FAKE_ENDPOINT
    # No network call is made here; only that the client was constructible and
    # exposes the two operations the child credential is scoped to.
    assert hasattr(client, "get_object")
    assert hasattr(client, "head_object")


def test_the_read_hop_actually_targets_the_dedicated_bucket_and_exact_key() -> None:
    """The defect this whole change exists to fix must be detectable.

    Every other test here proves the CREDENTIAL is scoped to the dedicated
    bucket.  None of them proved the actual S3 call goes there: build the
    wrapped R2Store against ``R2_RESEARCH_BUCKET`` and the credential
    assertions, the minter assertions, and the protocol assertions all still
    pass.  This asserts the one thing that was missing — the Bucket and Key
    that reach the client — so a wrong-bucket or key-mangling regression is
    caught here rather than in production silence.
    """
    factory = _RecordingClientFactory()
    store = _store(client_factory=factory)
    key = f"{R2_ATTESTED_HISTORY_PREFIX}latest.json"
    assert store.get_bytes_strict_bounded(key, 64) == RECEIPT_BYTES

    client = factory.clients[0]
    assert client.calls, "the bounded read never reached the S3 client"
    _op, kwargs = client.calls[0]
    assert kwargs["Bucket"] == FAKE_BUCKET
    assert kwargs["Key"] == key

    # And the exact-length mode takes the same hop, so a prefix rewrite cannot
    # hide in the second code path.
    factory2 = _RecordingClientFactory()
    store2 = _store(client_factory=factory2)
    store2.get_bytes_strict_bounded(key, expected_byte_length=len(RECEIPT_BYTES), max_byte_length=64)
    for _op, kwargs in factory2.clients[0].calls:
        assert kwargs["Bucket"] == FAKE_BUCKET
        assert kwargs["Key"] == key


def test_positional_cap_is_forwarded_unchanged_to_the_wrapped_store() -> None:
    factory = _RecordingClientFactory(payload=b"0123456789")
    store = _store(client_factory=factory)
    assert store.get_bytes_strict_bounded("k", 10) == b"0123456789"
    # A cap the object exceeds must be honoured by the WRAPPED store's logic;
    # a dropped or widened cap would silently return the body instead.
    with pytest.raises(ValueError, match="bounded read limit"):
        store.get_bytes_strict_bounded("k", 4)


def test_exact_length_keyword_mode_is_forwarded_unchanged() -> None:
    factory = _RecordingClientFactory(payload=b"0123456789")
    store = _store(client_factory=factory)
    assert (
        store.get_bytes_strict_bounded("k", expected_byte_length=10, max_byte_length=64)
        == b"0123456789"
    )
    client = factory.clients[0]
    assert [name for name, _ in client.calls] == ["head_object", "get_object"]
    assert client.calls[1][1]["IfMatch"] == '"fake-etag"'
    # A mismatched declared length must still fail closed inside R2Store.
    with pytest.raises(Exception, match="HEAD length mismatch"):
        store.get_bytes_strict_bounded("k", expected_byte_length=9, max_byte_length=64)


def test_bounded_read_modes_stay_mutually_exclusive() -> None:
    store = _store()
    with pytest.raises(ValueError, match="mutually exclusive"):
        store.get_bytes_strict_bounded("k", 10, expected_byte_length=10, max_byte_length=64)


# ---------------------------------------------------------------------------
# (m) store failure is a bounded, private 503 — never a 500 or a traceback
# ---------------------------------------------------------------------------

def test_unbuildable_store_becomes_a_bounded_private_503(monkeypatch) -> None:
    # Named for what it actually exercises: an invalid bucket is rejected by
    # DedicatedAttestedHistoryStore.__init__, so the store never builds and no
    # minter is ever reached.  Request-time mint failures are covered
    # separately by test_a_non_credential_mint_failure_still_raises_the_
    # advertised_error and test_a_failed_refresh_keeps_the_previous_child_and_
    # recovers.  Either way the route contract is one bounded 503 with the
    # private headers.
    for name, value in FAKE_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("FF_ATTESTED_R2_READONLY_BUCKET", "Not_A_Valid_Bucket")
    forensics_api._reset_store_cache()
    try:
        assert forensics_api._build_store() is None
        with _entitled_client() as client:
            response = client.get("/api/forensics/v1/attested-history/latest")
        assert response.status_code == 503
        assert response.json() == {"detail": "attested query history temporarily unavailable"}
        for name, expected in PRIVATE_HEADERS.items():
            assert response.headers[name] == expected
        assert FAKE_SECRET_ACCESS_KEY not in response.text
    finally:
        forensics_api._reset_store_cache()


# ---------------------------------------------------------------------------
# (n) writer-free VPS delivery of the read-only half only
# ---------------------------------------------------------------------------

def test_dedicated_readonly_credentials_are_delivered_to_macro_api_only() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-api-secrets.yml").read_text(
        encoding="utf-8"
    )
    for name in (
        "R2_ATTESTED_HISTORY_ENDPOINT",
        "R2_ATTESTED_HISTORY_BUCKET",
        "R2_ATTESTED_HISTORY_READONLY_ACCESS_KEY_ID",
        "R2_ATTESTED_HISTORY_READONLY_SECRET_ACCESS_KEY",
    ):
        assert f"secrets.{name}" in workflow, name
        # Exactly once: a second reference would mean the admin step gets it too.
        assert workflow.count(f"secrets.{name}") == 1, name
    for name in (
        "FF_ATTESTED_R2_READONLY_ENDPOINT",
        "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID",
        "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY",
        "FF_ATTESTED_R2_READONLY_BUCKET",
    ):
        assert f"_require {name} " in workflow, name
        assert f"_add {name} " in workflow, name
    assert (
        'grep -vE "^FF_ATTESTED_R2_READONLY_(ENDPOINT|ACCESS_KEY_ID|SECRET_ACCESS_KEY|BUCKET)="'
        in workflow
    )
    # Writer credentials never travel to the VPS, in any spelling.
    assert workflow.count("R2_ATTESTED_HISTORY_SEED") == 0
    assert workflow.count("FF_ATTESTED_R2_SEED") == 0
    # The existing fail-closed preflight coupling stays exactly as it was.
    assert (
        'echo "::error::All seven CLAUDE_CODE_OAUTH_TOKEN_N secrets are empty/absent"'
        in workflow
    )
    assert workflow.count('[ -n "$SSH_KEY" ] || { echo "::error::VPS_DEPLOY_KEY secret is empty/absent"; exit 1; }') == 2
    assert "SSH_KEY: ${{ secrets.VPS_DEPLOY_KEY }}" in workflow


def test_macro_admin_step_receives_no_attested_history_variable() -> None:
    import yaml

    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "deploy-api-secrets.yml").read_text(
            encoding="utf-8"
        )
    )
    job = workflow["jobs"]["deploy"]
    steps = job["steps"]
    assert len(steps) == 2
    api_env = steps[0]["env"]
    admin_step = steps[1]
    assert [name for name in api_env if "ATTESTED" in name]
    assert not [name for name in admin_step.get("env", {}) if "ATTESTED" in name]
    assert "ATTESTED" not in admin_step["run"]

    # A credential declared at JOB level is inherited by BOTH steps, so a
    # writer secret hidden there would reach macro-admin while every
    # step-scoped assertion above still passed.
    assert not [
        name
        for name, value in (job.get("env") or {}).items()
        if "ATTESTED" in name or "ATTESTED" in str(value)
    ], "attested-history credentials must be step-scoped, never job-scoped"
    assert not [
        name
        for name, value in (workflow.get("env") or {}).items()
        if "ATTESTED" in name or "ATTESTED" in str(value)
    ], "attested-history credentials must never be workflow-scoped"

    # Allow-list, not presence: asserting merely that SOME attested name exists
    # lets a NEW writer variable (say R2_ATTESTED_HISTORY_WRITE_ACCESS_KEY_ID)
    # be added to the macro-api step invisibly.  Exactly these four, no more.
    delivered = {
        name: str(value)
        for name, value in api_env.items()
        if "ATTESTED" in name or "ATTESTED" in str(value)
    }
    assert set(delivered) == {
        "FF_ATTESTED_EP",
        "FF_ATTESTED_BUCKET_NAME",
        "FF_ATTESTED_RO_AK",
        "FF_ATTESTED_RO_SK",
    }, f"unexpected attested-history variable in the VPS delivery step: {sorted(delivered)}"
    assert sorted(
        value.split("secrets.")[1].rstrip(" }") for value in delivered.values()
    ) == [
        "R2_ATTESTED_HISTORY_BUCKET",
        "R2_ATTESTED_HISTORY_ENDPOINT",
        "R2_ATTESTED_HISTORY_READONLY_ACCESS_KEY_ID",
        "R2_ATTESTED_HISTORY_READONLY_SECRET_ACCESS_KEY",
    ]
