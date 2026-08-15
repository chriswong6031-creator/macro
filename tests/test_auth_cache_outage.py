"""WS-3 / GATE-3: require_user reuses paywall._AUTH_CACHE; vendor outage is bounded.

Acceptance (research/MASTERMIND_RED_TEAM_REMEDIATION_PLAN.md WS-3):
- require_user consolidates onto paywall._fresh_identity / _AUTH_CACHE
- concurrent upstream auth calls are semaphore-bounded (shed, do not stall)
- /api/health answers while Supabase is unreachable
- a cached valid identity survives a vendor outage for the lawful TTL only
- invalid/expired tokens stay rejected; the cache is not a bypass
- no cross-user leakage
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import paywall
from app.main import app, require_user

UID = "11111111-1111-1111-1111-111111111111"
ALICE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BOB = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

client = TestClient(app)


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _reset_auth_cache():
    paywall._AUTH_CACHE.clear()
    original_sem = paywall._AUTH_UPSTREAM_SEM
    paywall._AUTH_UPSTREAM_SEM = threading.BoundedSemaphore(paywall._AUTH_UPSTREAM_LIMIT)
    yield
    paywall._AUTH_CACHE.clear()
    paywall._AUTH_UPSTREAM_SEM = original_sem


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x/auth/v1/user", code, "no", {}, None)


def _auth(token: str) -> dict:
    return require_user(authorization=f"Bearer {token}")


def _cache_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def test_require_user_and_paywall_share_one_hashed_cache_entry(monkeypatch):
    """One upstream call, one cache map — require_user must not mint a second."""
    calls: list[str] = []

    def urlopen(req, timeout=None):
        calls.append(getattr(req, "full_url", "") or "")
        return _Resp({"id": UID, "email": "Ops@Example.com", "role": "authenticated"})

    monkeypatch.setattr(paywall.urllib.request, "urlopen", urlopen)
    user = _auth("tok-shared")
    assert user["id"] == UID
    assert user["email"] == "Ops@Example.com"
    assert paywall._fresh_identity("tok-shared") == (UID, "ops@example.com")
    assert len(calls) == 1
    assert _cache_key("tok-shared") in paywall._AUTH_CACHE
    assert len(paywall._AUTH_CACHE) == 1


def test_cached_valid_identity_survives_vendor_outage_for_ttl_only(monkeypatch):
    monkeypatch.setattr(
        paywall.urllib.request,
        "urlopen",
        lambda *a, **k: _Resp(
            {"id": UID, "email": "a@b.com", "user_metadata": {"lang": "en"}}
        ),
    )
    user = _auth("tok-live")
    assert user["id"] == UID
    assert user["user_metadata"]["lang"] == "en"

    def boom(*a, **k):
        raise urllib.error.URLError("supabase down")

    monkeypatch.setattr(paywall.urllib.request, "urlopen", boom)
    still = _auth("tok-live")
    assert still["id"] == UID
    assert still["email"] == "a@b.com"
    assert paywall._fresh_identity("tok-live") == (UID, "a@b.com")

    key = _cache_key("tok-live")
    with paywall._AUTH_LOCK:
        uid, email, _exp, rec = paywall._AUTH_CACHE[key]
        paywall._AUTH_CACHE[key] = (uid, email, time.monotonic() - 1, rec)
    with pytest.raises(HTTPException) as ei:
        _auth("tok-live")
    assert ei.value.status_code == 502


def test_health_stays_up_while_supabase_is_unavailable(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.URLError("supabase down")

    monkeypatch.setattr(paywall.urllib.request, "urlopen", boom)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    with pytest.raises(HTTPException) as ei:
        _auth("tok-uncached")
    assert ei.value.status_code == 502


def test_invalid_and_expired_tokens_are_rejected_and_cached(monkeypatch):
    calls: list[int] = []

    def reject(req, timeout=None):
        calls.append(401)
        raise _http_error(401)

    monkeypatch.setattr(paywall.urllib.request, "urlopen", reject)
    with pytest.raises(HTTPException) as ei:
        _auth("tok-expired")
    assert ei.value.status_code == 401
    assert calls == [401]
    assert paywall._fresh_identity("tok-expired") == (None, "")
    assert calls == [401], "rejection must be served from _AUTH_CACHE"

    def ok(req, timeout=None):
        calls.append(200)
        return _Resp({"id": UID, "email": "x@y.z"})

    monkeypatch.setattr(paywall.urllib.request, "urlopen", ok)
    with pytest.raises(HTTPException) as ei:
        _auth("tok-expired")
    assert ei.value.status_code == 401
    assert 200 not in calls, "a cached reject must not become a bypass"

    other = _auth("tok-other")
    assert other["id"] == UID
    assert calls.count(200) == 1


def test_token_cache_does_not_leak_across_users(monkeypatch):
    def urlopen(req, timeout=None):
        tok = req.headers.get("Authorization", "")
        if tok.endswith("alice"):
            return _Resp({"id": ALICE, "email": "alice@x.com"})
        if tok.endswith("bob"):
            return _Resp({"id": BOB, "email": "bob@x.com"})
        raise _http_error(401)

    monkeypatch.setattr(paywall.urllib.request, "urlopen", urlopen)
    assert _auth("alice")["id"] == ALICE
    assert _auth("bob")["id"] == BOB
    with pytest.raises(HTTPException) as ei:
        _auth("eve")
    assert ei.value.status_code == 401

    def swapped(req, timeout=None):
        tok = req.headers.get("Authorization", "")
        if tok.endswith("alice"):
            return _Resp({"id": BOB, "email": "bob@x.com"})
        return _Resp({"id": ALICE, "email": "alice@x.com"})

    monkeypatch.setattr(paywall.urllib.request, "urlopen", swapped)
    assert _auth("alice")["id"] == ALICE
    assert _auth("bob")["id"] == BOB
    with pytest.raises(HTTPException) as ei:
        _auth("eve")
    assert ei.value.status_code == 401


def test_outage_is_not_cached_as_invalid(monkeypatch):
    """A transport failure teaches us nothing about the token — do not remember it."""
    monkeypatch.setattr(
        paywall.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("timed out")),
    )
    with pytest.raises(HTTPException) as ei:
        _auth("tok-blip")
    assert ei.value.status_code == 502
    assert _cache_key("tok-blip") not in paywall._AUTH_CACHE
    assert paywall._fresh_identity("tok-blip") == (None, "")
    assert _cache_key("tok-blip") not in paywall._AUTH_CACHE

    monkeypatch.setattr(
        paywall.urllib.request,
        "urlopen",
        lambda *a, **k: _Resp({"id": UID, "email": "back@x.com"}),
    )
    assert _auth("tok-blip")["id"] == UID


def test_concurrent_slow_auth_is_semaphore_bounded(monkeypatch):
    limit = 2
    paywall._AUTH_UPSTREAM_SEM = threading.BoundedSemaphore(limit)
    release = threading.Event()
    entered = threading.Event()
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()

    def urlopen(req, timeout=None):
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            if in_flight >= limit:
                entered.set()
        assert release.wait(timeout=2.0)
        with lock:
            in_flight -= 1
        return _Resp({"id": UID, "email": "slow@x.com"})

    monkeypatch.setattr(paywall.urllib.request, "urlopen", urlopen)

    n = 12
    results: list[object | None] = [None] * n

    def worker(i: int) -> None:
        try:
            results[i] = _auth(f"tok-{i}")
        except HTTPException as exc:
            results[i] = exc.status_code

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for thread in threads:
        thread.start()
    assert entered.wait(timeout=2.0)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if sum(1 for item in results if item == 502) == n - limit:
            break
        time.sleep(0.01)
    else:
        raise AssertionError(f"slow-auth shed stuck: {results!r}")

    assert max_in_flight <= limit
    release.set()
    for thread in threads:
        thread.join(timeout=2.0)
    assert all(not thread.is_alive() for thread in threads)
    ok = [item for item in results if isinstance(item, dict)]
    assert len(ok) == limit
    assert all(item["id"] == UID for item in ok)
    assert sum(1 for item in results if item == 502) == n - limit


def test_missing_bearer_is_rejected_without_touching_the_cache():
    with pytest.raises(HTTPException) as ei:
        require_user(authorization=None)
    assert ei.value.status_code == 401
    assert ei.value.detail == "missing bearer token"
    assert paywall._AUTH_CACHE == {}
