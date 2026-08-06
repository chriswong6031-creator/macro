"""tests/test_uid_verify_cache.py — _mm_verify_uid_cached caches ANSWERS, not outages.

The 2026-08-03 "suddenly logged out" bug. app/regwall.py is fail-closed and verifies
the short-lived Supabase ACCESS token on every gated navigation. The verifier below
caught every failure into one `uid = None` and cached it for the full 10-minute TTL,
so a 4s timeout or a Supabase 5xx was recorded against the visitor's token as though
Supabase had said 401. The visitor was then 302'd to /?signin=1&ret=…, and the
landing's silent refresh could not rescue them: the poisoned entry outlived the
retry, onboard.js's 45s wall-hop loop guard gave up, and a signed-in account with a
renewable session got a credentials prompt.

The contract: a transport failure still DENIES (fail-closed is not relaxed) but must
not be remembered; only an HTTP verdict on the token is cacheable.
"""
from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from app import main as appmain

UID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _clear_cache():
    appmain._MM_UID_CACHE.clear()
    yield
    appmain._MM_UID_CACHE.clear()


class _Resp:
    """Minimal context-manager stand-in for urlopen's response."""

    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(monkeypatch, uid: str = UID):
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: _Resp(b'{"id":"' + uid.encode() + b'"}'))


def _raises(monkeypatch, exc: BaseException):
    def _boom(*a, **k):
        raise exc
    monkeypatch.setattr(urllib.request, "urlopen", _boom)


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x/auth/v1/user", code, "no", {}, None)


def _never_called(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("upstream re-queried — the verdict was not cached")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)


# ── the regression pin ──────────────────────────────────────────────────────────
# This is the test the old code fails: it cached the timeout, so the retry never
# reached Supabase and the user stayed "logged out" for the full 10-minute TTL.
def test_timeout_is_not_cached_so_the_next_request_recovers(monkeypatch):
    _raises(monkeypatch, urllib.error.URLError("timed out"))
    assert appmain._mm_verify_uid_cached("tok_live") is None      # denied, correctly
    assert "tok_live" not in appmain._MM_UID_CACHE                # but NOT remembered

    _ok(monkeypatch)                                              # upstream recovers
    assert appmain._mm_verify_uid_cached("tok_live") == UID       # same token, now allowed


def test_server_error_is_not_cached(monkeypatch):
    """A 5xx/429 is the service failing, not a ruling on the token."""
    for code in (429, 500, 502, 503):
        appmain._MM_UID_CACHE.clear()
        _raises(monkeypatch, _http_error(code))
        assert appmain._mm_verify_uid_cached("tok_5xx") is None
        assert "tok_5xx" not in appmain._MM_UID_CACHE, f"HTTP {code} must not be cached"

        _ok(monkeypatch)
        assert appmain._mm_verify_uid_cached("tok_5xx") == UID


def test_unparseable_body_is_not_cached(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp(b"<html>nope"))
    assert appmain._mm_verify_uid_cached("tok_junk") is None
    assert "tok_junk" not in appmain._MM_UID_CACHE


# ── the half that must NOT regress: real verdicts still cache ───────────────────
@pytest.mark.parametrize("code", [400, 401, 403])
def test_token_rejection_is_cached(monkeypatch, code):
    """Supabase answered and rejected the token — authoritative, don't re-ask."""
    _raises(monkeypatch, _http_error(code))
    assert appmain._mm_verify_uid_cached("tok_bad") is None
    assert appmain._MM_UID_CACHE["tok_bad"][0] is None

    _never_called(monkeypatch)
    assert appmain._mm_verify_uid_cached("tok_bad") is None


def test_valid_token_is_cached(monkeypatch):
    _ok(monkeypatch)
    assert appmain._mm_verify_uid_cached("tok_good") == UID

    _never_called(monkeypatch)
    assert appmain._mm_verify_uid_cached("tok_good") == UID


def test_non_uuid_id_is_rejected_and_cached(monkeypatch):
    """Supabase answered; the body just isn't a uuid FK. Still a verdict."""
    _ok(monkeypatch, uid="not-a-uuid")
    assert appmain._mm_verify_uid_cached("tok_weird") is None
    assert appmain._MM_UID_CACHE["tok_weird"][0] is None


def test_outage_never_serves_a_session(monkeypatch):
    """Fail-closed is unchanged: not-caching is not the same as allowing."""
    for exc in (urllib.error.URLError("dns"), TimeoutError(), OSError("reset"),
                _http_error(500)):
        appmain._MM_UID_CACHE.clear()
        _raises(monkeypatch, exc)
        assert appmain._mm_verify_uid_cached("tok_any") is None
