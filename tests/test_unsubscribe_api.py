"""tests/test_unsubscribe_api.py — app/unsubscribe.py (SEE W4, masterplan R5).

The compliance endpoint. Public, unauthenticated, token-authorised: the person clicking is
very often exactly the person who cannot sign in, so requiring a session would make the
unsubscribe a dark pattern — and RFC 8058 one-click has no session to present at all.

What is proven here:
  * the HMAC token is the ONLY authorisation, and a missing/tampered/unsigned one is
    refused with the same answer, so the route cannot be used to probe for accounts;
  * both gates are written for a known user (address-level suppression AND the per-user
    opt-out), and either alone is a complete stop;
  * it is idempotent — a second click reports "already", never an error;
  * one-click works: a form-encoded POST with the token in the query string, which is the
    only shape a mail client will ever send;
  * resubscribe is a separate action AND refuses to lift a bounce or a complaint;
  * a database failure answers 503, not 500.

Fully offline. Two seams: ``unsubscribe._pg`` (PostgREST) and ``unsubscribe._user_email``
(the GoTrue admin read). The route is called directly with a fake Request, the
``tests/test_support_api.py`` idiom — no TestClient, so the suite needs no httpx.
"""
from __future__ import annotations

import asyncio
import sys
import urllib.parse
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import mailer, unsubscribe as unsub  # noqa: E402

UID = "11111111-1111-4111-8111-111111111111"
ADDR = "ada@example.com"

_MAIL_ENV = ("MAIL_UNSUB_SECRET", "MAIL_SMTP_HOST", "MAIL_SMTP_USER", "MAIL_SMTP_PASS",
             "MAIL_FROM", "MAIL_SITE_BASE")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No operator-local relay values may change what these tests assert (#3553)."""
    for k in _MAIL_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "test-unsub-secret")
    monkeypatch.setattr(mailer, "SUPABASE_SERVICE_ROLE_KEY", "svc-key")
    monkeypatch.setattr(unsub, "SUPABASE_URL", "https://example.supabase.co")


class _FakeRequest:
    """Enough Request for this route: query params and a raw body."""

    def __init__(self, query: dict | None = None, body: bytes = b""):
        self.query_params = dict(query or {})
        self._body = body

    async def body(self) -> bytes:
        return self._body


class _Store:
    """In-memory email_suppression + email_prefs."""

    def __init__(self, suppression=None, prefs=None):
        self.suppression = dict(suppression or {})     # addr -> reason
        self.prefs = dict(prefs or {})                 # user_id -> opt_out bool
        self.calls: list[tuple[str, str, str | None]] = []
        self.fail = False

    def pg(self, method, path, body=None, prefer=None, timeout=6):
        path = urllib.parse.unquote(path)
        self.calls.append((method, path, prefer))
        if self.fail:
            raise RuntimeError("supabase unreachable")
        if path.startswith("email_suppression"):
            if method == "GET":
                addr = path.split("email=eq.", 1)[1].split("&", 1)[0]
                reason = self.suppression.get(addr)
                return [{"email": addr, "reason": reason}] if reason else []
            if method == "POST":
                row = (body or [{}])[0]
                self.suppression[row["email"]] = row["reason"]
                return None
            if method == "DELETE":
                addr = path.split("email=eq.", 1)[1].split("&", 1)[0]
                self.suppression.pop(addr, None)
                return None
        if path.startswith("email_prefs") and method == "POST":
            row = (body or [{}])[0]
            self.prefs[row["user_id"]] = row["marketing_opt_out"]
            return None
        raise AssertionError(f"unexpected call {method} {path}")


@pytest.fixture
def store(monkeypatch):
    s = _Store()
    monkeypatch.setattr(unsub, "_pg", s.pg)
    monkeypatch.setattr(unsub, "_user_email", lambda uid: ADDR if uid == UID else None)
    return s


def _call(query=None, body=b""):
    return asyncio.run(unsub.unsubscribe(_FakeRequest(query, body)))


def _token(identity=UID):
    return mailer.unsub_token(identity)


# ===========================================================================
# The token is the whole authorisation
# ===========================================================================
def test_a_valid_token_unsubscribes_and_writes_both_gates(store):
    out = _call({"t": _token()})
    assert out["ok"] is True and out["state"] == "unsubscribed"
    assert store.suppression == {ADDR: "unsubscribe"}
    assert store.prefs == {UID: True}


@pytest.mark.parametrize("query", [
    {},                                   # no token at all
    {"t": ""},                            # empty
    {"t": "not-a-token"},                 # unparseable
    {"t": "garbage.garbage"},             # right shape, wrong MAC
])
def test_a_missing_or_invalid_token_is_refused_identically(store, query):
    """Same 400 for every failure, so the route cannot be used to test whether an address
    or a user id exists."""
    with pytest.raises(HTTPException) as e:
        _call(query)
    assert e.value.status_code == 400
    assert store.suppression == {} and store.prefs == {}


def test_a_token_for_a_different_secret_does_not_verify(store, monkeypatch):
    stolen = _token()
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "a-different-secret")
    with pytest.raises(HTTPException) as e:
        _call({"t": stolen})
    assert e.value.status_code == 400
    assert store.suppression == {}


def test_a_tampered_identity_does_not_verify(store):
    """Flipping the payload half of `<b64 identity>.<b64 mac>` must not let someone
    unsubscribe an address they do not hold a token for."""
    good = _token()
    ident_b64, _, mac = good.partition(".")
    forged = mailer._b64e(b"22222222-2222-4222-8222-222222222222") + "." + mac
    assert forged != good
    with pytest.raises(HTTPException) as e:
        _call({"t": forged})
    assert e.value.status_code == 400
    assert store.suppression == {}


def test_no_secret_configured_means_no_token_verifies(store, monkeypatch):
    """Fail-closed: with MAIL_UNSUB_SECRET unset nothing can be minted and nothing is
    accepted, rather than everything being accepted."""
    tok = _token()
    monkeypatch.delenv("MAIL_UNSUB_SECRET", raising=False)
    with pytest.raises(HTTPException) as e:
        _call({"t": tok})
    assert e.value.status_code == 400


# ===========================================================================
# Idempotency
# ===========================================================================
def test_a_second_click_says_already_and_never_errors(store):
    first = _call({"t": _token()})
    second = _call({"t": _token()})
    assert first["already"] is False
    assert second["ok"] is True and second["already"] is True
    assert second["state"] == "unsubscribed"
    assert store.suppression == {ADDR: "unsubscribe"}


def test_the_suppression_write_is_an_upsert_not_an_insert(store):
    """A read-then-write would race two tabs into a duplicate-key 500 in front of somebody
    who only wants the mail to stop."""
    _call({"t": _token()})
    posts = [(p, pref) for m, p, pref in store.calls
             if m == "POST" and p.startswith("email_suppression")]
    assert posts, "the suppression write must happen"
    # the merge-duplicates Prefer header is what makes the second click a no-op UPDATE
    # inside PostgREST rather than a unique-violation the reader would see as a failure
    assert all("resolution=merge-duplicates" in (pref or "") for _p, pref in posts)


def test_the_preference_write_is_an_upsert_too(store):
    """Most users have no email_prefs row at all, so a bare UPDATE would silently write
    nothing and leave the per-user gate open."""
    _call({"t": _token()})
    posts = [(p, pref) for m, p, pref in store.calls
             if m == "POST" and p.startswith("email_prefs")]
    assert posts and all("resolution=merge-duplicates" in (pref or "") for _p, pref in posts)


# ===========================================================================
# One-click (RFC 8058)
# ===========================================================================
def test_one_click_form_post_with_the_token_in_the_query_string(store):
    """The only shape a mail client sends: our JSON is never involved, the token rides the
    URL, and the body is the client's own `List-Unsubscribe=One-Click`."""
    out = _call({"t": _token()}, body=b"List-Unsubscribe=One-Click")
    assert out["ok"] is True and out["state"] == "unsubscribed"
    assert store.suppression == {ADDR: "unsubscribe"}


def test_a_non_json_body_is_not_an_error(store):
    out = _call({"t": _token()}, body=b"\x00\xff not json at all")
    assert out["ok"] is True


def test_a_json_body_token_also_works(store):
    """The page itself posts JSON."""
    import json
    out = _call({}, body=json.dumps({"t": _token(), "action": "unsubscribe"}).encode())
    assert out["ok"] is True and store.suppression == {ADDR: "unsubscribe"}


def test_one_click_can_never_resubscribe(store):
    """A mail client's own body must not be able to select the action. `action` is read
    from OUR json, and a form body carrying action=resubscribe is not our json."""
    _call({"t": _token()})
    out = _call({"t": _token()}, body=b"action=resubscribe&List-Unsubscribe=One-Click")
    assert out["state"] == "unsubscribed"
    assert store.suppression == {ADDR: "unsubscribe"}


# ===========================================================================
# Resubscribe — a second action, never the default
# ===========================================================================
def test_resubscribe_lifts_an_unsubscribe_and_clears_the_opt_out(store):
    import json
    _call({"t": _token()})
    assert store.suppression == {ADDR: "unsubscribe"} and store.prefs == {UID: True}
    out = _call({}, body=json.dumps({"t": _token(), "action": "resubscribe"}).encode())
    assert out["state"] == "subscribed"
    assert store.suppression == {} and store.prefs == {UID: False}


@pytest.mark.parametrize("reason", ["bounce", "complaint"])
def test_resubscribe_refuses_to_lift_a_bounce_or_a_complaint(store, reason):
    """Those record what the ADDRESS did, not what its owner chose. Re-arming the exact
    send that damaged our sending reputation because a link was clicked is how a domain
    gets blocklisted — and the reader is told plainly rather than silently ignored."""
    import json
    store.suppression = {ADDR: reason}
    out = _call({}, body=json.dumps({"t": _token(), "action": "resubscribe"}).encode())
    assert out["refused"] == reason
    assert out["state"] == "unsubscribed"
    assert store.suppression == {ADDR: reason}, "the row must survive"
    assert store.prefs == {}, "and the opt-out must not be cleared either"


def test_an_unknown_action_falls_back_to_unsubscribing(store):
    """The stricter direction. A typo or a hand-rolled request can never turn an
    unsubscribe link into a re-subscribe."""
    import json
    out = _call({}, body=json.dumps({"t": _token(), "action": "surprise"}).encode())
    assert out["state"] == "unsubscribed"
    assert store.suppression == {ADDR: "unsubscribe"}


def test_manual_suppressions_are_liftable_by_their_owner(store):
    import json
    store.suppression = {ADDR: "manual"}
    out = _call({}, body=json.dumps({"t": _token(), "action": "resubscribe"}).encode())
    assert "refused" not in out and store.suppression == {}


# ===========================================================================
# Identity shapes
# ===========================================================================
def test_a_bare_address_token_suppresses_without_touching_prefs(store):
    """Tokens are minted for people who never registered too — a bare address is a
    complete stop on its own, because mailer checks the address first."""
    out = _call({"t": _token("stranger@example.com")})
    assert out["ok"] is True
    assert store.suppression == {"stranger@example.com": "unsubscribe"}
    assert store.prefs == {}


def test_an_address_is_lowercased_before_it_is_stored(store):
    """`Ada@Example.com` unsubscribing has to suppress `ada@example.com`, or the very next
    send finds no row."""
    _call({"t": _token("Ada@Example.COM")})
    assert store.suppression == {"ada@example.com": "unsubscribe"}


def test_a_token_that_is_neither_a_uuid_nor_an_address_is_refused(store):
    with pytest.raises(HTTPException) as e:
        _call({"t": _token("not-an-identity")})
    assert e.value.status_code == 400


def test_the_opt_out_still_lands_when_the_address_cannot_be_resolved(store, monkeypatch):
    """Either gate alone is a complete stop, so losing one must not lose both."""
    monkeypatch.setattr(unsub, "_user_email", lambda uid: None)
    out = _call({"t": _token()})
    assert out["ok"] is True
    assert store.prefs == {UID: True}
    assert store.suppression == {}


# ===========================================================================
# Masking + failure
# ===========================================================================
def test_the_reply_masks_the_address():
    """The page says which address it acted on — "we stopped the emails" is not an answer
    when someone holds three — but a token is a public bearer credential, so the full
    address is not echoed back to whoever presents one."""
    assert unsub.mask("ada.lovelace@example.com").endswith("@example.com")
    assert "ada.lovelace" not in unsub.mask("ada.lovelace@example.com")
    assert unsub.mask("ab@x.com").startswith("a")
    assert unsub.mask("") == "" and unsub.mask("no-at-sign") == ""


def test_the_masked_address_comes_back_on_success(store):
    out = _call({"t": _token()})
    assert out["email_masked"].endswith("@example.com")
    assert ADDR not in out["email_masked"]


def test_a_database_failure_answers_503_not_500(store):
    """A compliance surface: "we could not record that, try again" keeps a reader
    retrying; "something broke" gets us reported."""
    store.fail = True
    with pytest.raises(HTTPException) as e:
        _call({"t": _token()})
    assert e.value.status_code == 503


def test_the_route_is_post_only_so_a_link_scanner_cannot_unsubscribe_anyone():
    """Mail scanners and preview bots fetch every URL in an inbound message. A GET that
    mutated would opt out people who never clicked, silently."""
    methods = {m for r in unsub.router.routes for m in getattr(r, "methods", set())}
    assert methods == {"POST"}
    paths = {getattr(r, "path", "") for r in unsub.router.routes}
    assert paths == {"/api/email/unsubscribe"}
