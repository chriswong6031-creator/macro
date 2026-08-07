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
        assert forensics_api._build_store() is None
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
    seed_fundamental_forensics_attested_history.py:680/:821.  This test fails
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
    clock = _Clock(1_000_000)
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
    assert store.child_expires_at == 1_001_800
    assert store.refresh_count == 0
    assert len(minter.calls) == 1
    assert len(factory.clients) == 1

    # One tick before (expiry - margin): the same child and the same client.
    clock.value = 1_001_499.0
    assert store.get_bytes_strict_bounded("k", 64) == RECEIPT_BYTES
    assert len(minter.calls) == 1
    assert len(factory.clients) == 1
    assert store.refresh_count == 0

    # At (expiry - margin): a new child and a NEW client.
    clock.value = 1_001_500.0
    assert store.get_bytes_strict_bounded("k", 64) == RECEIPT_BYTES
    assert len(minter.calls) == 2
    assert len(factory.clients) == 2
    assert store.refresh_count == 1
    assert store.child_expires_at == 1_003_300
    assert factory.clients[1].calls, "the read must use the renewed client"

    # Still inside the NEW window: the crossing is not re-counted per read.
    for _ in range(5):
        assert store.get_bytes_strict_bounded("k", 64) == RECEIPT_BYTES
    assert len(minter.calls) == 2
    assert store.refresh_count == 1


def test_many_reads_inside_the_validity_window_mint_exactly_once() -> None:
    clock = _Clock(1_000_000)
    minter = _RecordingMinter(clock)
    factory = _RecordingClientFactory()
    store = _store(clock=clock, minter=minter, client_factory=factory)
    for offset in range(0, 1_200, 100):
        clock.value = 1_000_000 + offset
        assert store.get_bytes_strict_bounded("k", 64) == RECEIPT_BYTES
    assert len(minter.calls) == 1
    assert len(factory.clients) == 1
    assert store.refresh_count == 0


# ---------------------------------------------------------------------------
# (h) concurrent cold start mints once
# ---------------------------------------------------------------------------

def test_concurrent_cold_reads_mint_exactly_one_child() -> None:
    clock = _Clock(1_000_000)
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


# ---------------------------------------------------------------------------
# (i)/(j) protocol admission and verbatim bounded-read forwarding
# ---------------------------------------------------------------------------

def test_store_satisfies_the_strict_bounded_read_protocol() -> None:
    assert isinstance(_store(), StrictBoundedReadStore)


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

def test_unmintable_credential_becomes_a_bounded_private_503(monkeypatch) -> None:
    for name, value in FAKE_ENV.items():
        monkeypatch.setenv(name, value)
    # A parent that cannot sign a scoped child is a configuration failure; the
    # route contract is still one bounded 503 with the private headers.
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
    steps = workflow["jobs"]["deploy"]["steps"]
    assert len(steps) == 2
    api_env = steps[0]["env"]
    admin_step = steps[1]
    assert [name for name in api_env if "ATTESTED" in name]
    assert not [name for name in admin_step.get("env", {}) if "ATTESTED" in name]
    assert "ATTESTED" not in admin_step["run"]
