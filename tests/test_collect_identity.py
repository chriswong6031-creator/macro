"""Tests for app/main.py registered-visitor identity capture (the pure, no-network parts).

Covers the Supabase session-cookie parsing (single + chunked), the storage-key derivation,
and the EO-Client-IP real-IP precedence. The network verification (_mm_verify_uid_cached) is
the same secretless idiom as require_user and is exercised only via a monkeypatched urlopen.
"""
import base64
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import app.main as m


class _FakeReq:
    def __init__(self, cookies=None, headers=None):
        self.cookies = cookies or {}
        self.headers = headers or {}


def _cookie_for(session: dict) -> str:
    """Mirror templates/theme.js COOKIE_STORAGE: 'base64-' + unpadded base64url(JSON)."""
    raw = json.dumps(session)
    b = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    return "base64-" + b


def test_storage_key_shape():
    assert m._SB_STORAGE_KEY.startswith("sb-")
    assert m._SB_STORAGE_KEY.endswith("-auth-token")


def test_extract_token_single_cookie():
    tok = "eyJhbGciOi.header.payload.sig"
    ck = {m._SB_STORAGE_KEY: _cookie_for({"access_token": tok, "user": {"id": "u1"}})}
    assert m._mm_supabase_access_token(_FakeReq(cookies=ck)) == tok


def test_extract_token_chunked():
    tok = "chunked.access.token.value"
    full = _cookie_for({"access_token": tok, "user": {"id": "u2"}})
    mid = len(full) // 2
    ck = {f"{m._SB_STORAGE_KEY}.0": full[:mid], f"{m._SB_STORAGE_KEY}.1": full[mid:]}
    assert m._mm_supabase_access_token(_FakeReq(cookies=ck)) == tok


def test_extract_token_absent():
    assert m._mm_supabase_access_token(_FakeReq(cookies={})) is None


def test_extract_token_not_base64_prefixed():
    ck = {m._SB_STORAGE_KEY: "raw-non-base64-value"}
    assert m._mm_supabase_access_token(_FakeReq(cookies=ck)) is None


def test_extract_token_corrupt_base64_returns_none():
    ck = {m._SB_STORAGE_KEY: "base64-!!!not valid!!!"}
    assert m._mm_supabase_access_token(_FakeReq(cookies=ck)) is None


def test_extract_token_no_access_token_key():
    ck = {m._SB_STORAGE_KEY: _cookie_for({"user": {"id": "u3"}})}  # session without access_token
    assert m._mm_supabase_access_token(_FakeReq(cookies=ck)) is None


def test_client_ip_prefers_eo_client_ip():
    h = {"eo-client-ip": "1.2.3.4", "eo-connecting-ip": "5.6.7.8", "x-forwarded-for": "9.9.9.9"}
    assert m._mm_client_ip(_FakeReq(headers=h)) == "1.2.3.4"


def test_client_ip_falls_back_to_xff_first_hop():
    h = {"x-forwarded-for": "9.9.9.9, 1.1.1.1"}
    assert m._mm_client_ip(_FakeReq(headers=h)) == "9.9.9.9"


def test_client_ip_unknown_when_no_headers():
    assert m._mm_client_ip(_FakeReq(headers={})) == "unknown"


def test_verify_uid_cached(monkeypatch):
    """Verified token returns the user's uuid; invalid token returns None (both cached)."""
    import io

    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        tok = req.headers.get("Authorization", "")
        if "good-token" in tok:
            return io.BytesIO(json.dumps({"id": "11111111-2222-3333-4444-555555555555",
                                          "email": "a@b.com"}).encode())
        raise RuntimeError("401")

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    m._MM_UID_CACHE.clear()
    uid = m._mm_verify_uid_cached("good-token")
    assert uid == "11111111-2222-3333-4444-555555555555"
    # cached — no second network call
    m._mm_verify_uid_cached("good-token")
    assert calls["n"] == 1
    # invalid token caches as None
    assert m._mm_verify_uid_cached("bad-token") is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
