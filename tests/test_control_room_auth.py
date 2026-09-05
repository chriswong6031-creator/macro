"""CCR-R0 Task 6: exact-operator auth gate over the existing identity owner."""
from __future__ import annotations

import base64
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import main, paywall


OPERATOR_UUID = "11111111-1111-4111-8111-111111111111"
OTHER_UUID = "22222222-2222-4222-8222-222222222222"
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _clean_auth(monkeypatch):
    monkeypatch.delenv("SUPABASE_OPERATOR_USER_ID", raising=False)
    paywall._AUTH_CACHE.clear()
    yield
    paywall._AUTH_CACHE.clear()


@pytest.mark.parametrize(
    ("config", "token", "identity", "expected"),
    [
        (None, None, None, 503),
        ("not-a-uuid", None, None, 503),
        ("11111111-1111-4111-8111-11111111111A", None, None, 503),
        (OPERATOR_UUID, None, None, 401),
        (OPERATOR_UUID, "bad", paywall._Identity(None, "", None, "invalid"), 401),
        (
            OPERATOR_UUID,
            "ordinary",
            paywall._Identity(OTHER_UUID, "ordinary@example.test", {"id": OTHER_UUID}, "ok"),
            403,
        ),
        (OPERATOR_UUID, "down", paywall._Identity(None, "", None, "outage"), 502),
        (OPERATOR_UUID, "busy", paywall._Identity(None, "", None, "busy"), 502),
        (
            OPERATOR_UUID,
            "operator",
            paywall._Identity(OPERATOR_UUID, "operator@example.test", {"id": OPERATOR_UUID}, "ok"),
            204,
        ),
    ],
)
@pytest.mark.parametrize("method", ["get", "head"])
def test_control_room_auth_matrix_is_bodyless_and_credential_safe(
    monkeypatch, config, token, identity, expected, method
):
    """A wrong branch, noncanonical UUID, or leaked identity must fail this matrix."""
    if config is None:
        monkeypatch.delenv("SUPABASE_OPERATOR_USER_ID", raising=False)
    else:
        monkeypatch.setenv("SUPABASE_OPERATOR_USER_ID", config)
    monkeypatch.setattr(main, "_mm_supabase_access_token", lambda request: token)
    if identity is not None:
        monkeypatch.setattr(paywall, "_resolve_identity", lambda supplied: identity)

    response = getattr(client, method)("/api/control-room/auth-check")

    assert response.status_code == expected
    assert response.content == b""
    visible = (str(response.headers) + response.text).lower()
    for forbidden in (
        OPERATOR_UUID,
        OTHER_UUID,
        "operator@example.test",
        "ordinary@example.test",
        "authorization",
        "cookie",
        "supabase",
        "/users/",
    ):
        assert forbidden.lower() not in visible


def test_control_room_auth_checks_configuration_before_identity(monkeypatch):
    """Malformed authority configuration must not touch browser or provider identity."""
    monkeypatch.setenv("SUPABASE_OPERATOR_USER_ID", "not-a-uuid")
    monkeypatch.setattr(
        main,
        "_mm_supabase_access_token",
        lambda request: pytest.fail("cookie extraction must not run"),
    )
    monkeypatch.setattr(
        paywall,
        "_resolve_identity",
        lambda token: pytest.fail("identity resolution must not run"),
    )

    response = client.get("/api/control-room/auth-check")

    assert response.status_code == 503
    assert response.content == b""


@pytest.mark.parametrize(
    "cookie_header",
    [
        lambda key: f"{key}=not-base64",
        lambda key: f"{key}=base64-not-json",
        lambda key: f"{key}.0=base64-bm90; {key}.2=LWpzb24=",
    ],
)
def test_control_room_auth_rejects_malformed_and_gapped_chunk_cookies(
    monkeypatch, cookie_header
):
    """Malformed cookie encodings must never reach the identity owner."""
    monkeypatch.setenv("SUPABASE_OPERATOR_USER_ID", OPERATOR_UUID)
    monkeypatch.setattr(
        paywall,
        "_resolve_identity",
        lambda token: pytest.fail("malformed cookie must not resolve"),
    )

    response = client.get(
        "/api/control-room/auth-check",
        headers={"cookie": cookie_header(main._SB_STORAGE_KEY)},
    )

    assert response.status_code == 401
    assert response.content == b""


def _jwt_with_exp(exp: float) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode("utf-8")).decode("ascii")
    return f"header.{payload.rstrip('=')}.signature"


def test_positive_identity_cache_is_clamped_to_verified_jwt_exp(monkeypatch):
    """A positive cache entry must not outlive a token expiring in five seconds."""
    token = _jwt_with_exp(1005.0)
    monotonic_now = 200.0
    monkeypatch.setenv("PAYWALL_AUTH_CACHE_SECONDS", "45")
    monkeypatch.setattr(paywall.time, "time", lambda: 1000.0)
    monkeypatch.setattr(paywall.time, "monotonic", lambda: monotonic_now)
    monkeypatch.setattr(
        paywall,
        "_fetch_supabase_user",
        lambda supplied: paywall._Identity(OPERATOR_UUID, "operator@example.test", {"id": OPERATOR_UUID}, "ok"),
    )

    identity = paywall._resolve_identity(token)

    assert identity.uid == OPERATOR_UUID
    key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert paywall._AUTH_CACHE[key][2] == pytest.approx(205.0)


@pytest.mark.parametrize("token", [_jwt_with_exp(999.0), "not-a-jwt"])
def test_expired_or_unparseable_positive_token_is_not_cached(monkeypatch, token):
    """No parseable future expiry means no reusable positive identity."""
    monkeypatch.setattr(paywall.time, "time", lambda: 1000.0)
    monkeypatch.setattr(paywall.time, "monotonic", lambda: 200.0)
    monkeypatch.setattr(
        paywall,
        "_fetch_supabase_user",
        lambda supplied: paywall._Identity(OPERATOR_UUID, "operator@example.test", {"id": OPERATOR_UUID}, "ok"),
    )

    identity = paywall._resolve_identity(token)

    assert identity.uid == OPERATOR_UUID
    assert hashlib.sha256(token.encode("utf-8")).hexdigest() not in paywall._AUTH_CACHE


def test_invalid_identity_keeps_existing_bounded_cache_contract(monkeypatch):
    """Clamping positives must not remove the existing short invalid-verdict cache."""
    token = "invalid-token-without-jwt-exp"
    monkeypatch.setattr(paywall.time, "monotonic", lambda: 300.0)
    monkeypatch.setattr(
        paywall,
        "_fetch_supabase_user",
        lambda supplied: paywall._Identity(None, "", None, "invalid"),
    )

    identity = paywall._resolve_identity(token)

    assert identity.status == "invalid"
    key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert paywall._AUTH_CACHE[key][2] == pytest.approx(345.0)


def test_control_room_auth_reuses_only_the_existing_hashed_cache(monkeypatch):
    """Two gate calls for one token use one existing cache entry and one upstream call."""
    token = _jwt_with_exp(2000.0)
    calls: list[str] = []
    monkeypatch.setenv("SUPABASE_OPERATOR_USER_ID", OPERATOR_UUID)
    monkeypatch.setattr(main, "_mm_supabase_access_token", lambda request: token)
    monkeypatch.setattr(paywall.time, "time", lambda: 1000.0)

    def fetch(supplied: str) -> paywall._Identity:
        calls.append(supplied)
        return paywall._Identity(OPERATOR_UUID, "operator@example.test", {"id": OPERATOR_UUID}, "ok")

    monkeypatch.setattr(paywall, "_fetch_supabase_user", fetch)

    first = client.get("/api/control-room/auth-check")
    second = client.head("/api/control-room/auth-check")

    assert first.status_code == second.status_code == 204
    assert calls == [token]
    assert set(paywall._AUTH_CACHE) == {hashlib.sha256(token.encode("utf-8")).hexdigest()}
    assert not any(name.startswith("_CONTROL_ROOM_") and "CACHE" in name for name in vars(paywall))
