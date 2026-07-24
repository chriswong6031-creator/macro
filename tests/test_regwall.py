"""tests/test_regwall.py — the registration wall's fail-closed contract.

Offline: the Supabase verifier + cookie parser (app.main) are monkeypatched.
NOTE (repo memory fastapi-includedrouter-route-verify): endpoints are verified
via TestClient RESPONSES, never by scanning app.routes.

The one law under test: gated paths NEVER serve without a verified session —
missing cookie, bad token, verifier outage, and module exceptions all DENY
(302 to the landing with the sheet param), and nothing this endpoint returns
is cacheable.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import regwall
from app.main import app

client = TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def _wall_on(monkeypatch):
    monkeypatch.delenv("REGWALL_ENABLED", raising=False)


def _check(cookies=None, orig="/macro.html"):
    return client.get("/api/regwall/check", cookies=cookies or {},
                      headers={"X-Original-Uri": orig})


def test_no_cookie_denies_with_ret():
    r = _check()
    assert r.status_code == 302
    assert r.headers["location"] == "/?signin=1&ret=/macro.html"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-regwall"] == "deny"


def test_valid_session_allows(monkeypatch):
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda req: "tok_good")
    monkeypatch.setattr("app.main._mm_verify_uid_cached", lambda tok: "11111111-1111-1111-1111-111111111111")
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-regwall"] == "allow"
    assert r.headers["cache-control"] == "no-store"


def test_invalid_token_denies(monkeypatch):
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda req: "tok_bad")
    monkeypatch.setattr("app.main._mm_verify_uid_cached", lambda tok: None)
    assert _check().status_code == 302


def test_verifier_exception_fails_closed(monkeypatch):
    def boom(tok):
        raise RuntimeError("supabase down")
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda req: "tok")
    monkeypatch.setattr("app.main._mm_verify_uid_cached", boom)
    r = _check()
    assert r.status_code == 302, "an erroring verifier must DENY, never allow"


def test_ret_sanitization():
    # off-origin and garbage rets are dropped, never echoed
    r = _check(orig="//evil.example/steal")
    assert r.status_code == 302
    assert r.headers["location"] == "/?signin=1"
    r = _check(orig="https://evil.example/x")
    assert r.headers["location"] == "/?signin=1"


def test_public_ret_not_echoed():
    # redirecting back to a public page is pointless; keep the location minimal
    r = _check(orig="/index.html")
    assert r.headers["location"] == "/?signin=1"


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("REGWALL_ENABLED", "0")
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-regwall"] == "off"


def test_deny_helper_percent_encodes():
    assert regwall._deny("/a b.html").headers["Location"] == "/?signin=1&ret=/a%20b.html"
