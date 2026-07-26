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
import json
import sys
import urllib.error
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
    """In-memory email_suppression + email_prefs.

    The POST branch models PostgREST FAITHFULLY, and that is load-bearing rather than
    pedantic: ``email_suppression.email`` is UNIQUE, so a plain insert on an address
    already on file answers 409 (SQLSTATE 23505) and writes nothing, while an insert
    carrying ``Prefer: resolution=merge-duplicates`` becomes ``do update set …`` and
    OVERWRITES the reason. A fake that upserted either way could not tell the two apart,
    and telling them apart is the whole of the downgrade fix.
    """

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
                merge = "resolution=merge-duplicates" in (prefer or "")
                if row["email"] in self.suppression and not merge:
                    raise urllib.error.HTTPError(
                        "https://example.supabase.co/rest/v1/email_suppression", 409,
                        "duplicate key value violates unique constraint", {}, None)
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


def _token(identity=UID, action="unsubscribe"):
    return mailer.unsub_token(identity, action)


def _undo(store, identity=UID):
    """Unsubscribe once and hand back the resubscribe capability the server minted.

    The ONLY way the page ever obtains one: the footer token authorises `unsubscribe`,
    and the undo token is issued to the request that actually recorded the opt-out.
    """
    out = _call({"t": _token(identity)})
    return out.get("resubscribe_token", "")


def _resub(store, tok):
    return _call({}, body=json.dumps({"t": tok, "action": "resubscribe"}).encode())


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


def test_the_suppression_write_can_never_overwrite_an_existing_reason(store):
    """It must NOT be a merge-duplicates upsert.

    ``resolution=merge-duplicates`` is ``on conflict do update set reason =
    excluded.reason`` with no guard, so a reader already suppressed as `complaint` who
    clicked an old footer link rewrote their own row to `unsubscribe` — which
    RESUBSCRIBABLE then let them delete from the page. The unique constraint is still what
    arbitrates the two-tabs race; a 409 is simply read as "already there" instead of being
    papered over with a write that can only weaken the row.
    """
    _call({"t": _token()})
    posts = [(p, pref) for m, p, pref in store.calls
             if m == "POST" and p.startswith("email_suppression")]
    assert posts, "the suppression write must happen"
    assert all("resolution=merge-duplicates" not in (pref or "") for _p, pref in posts)


@pytest.mark.parametrize("reason", ["bounce", "complaint"])
def test_an_unsubscribe_click_cannot_downgrade_a_bounce_or_a_complaint(store, reason):
    """THE ESCALATION, end to end. Someone suppressed as `complaint` clicks an old
    unsubscribe link; if that click rewrote the reason to `unsubscribe`, the very next
    press of "turn them back on" would delete the row and marketing would resume to an
    address that had reported us as spam. The reason must survive the click, and the
    refusal must survive it too."""
    store.suppression = {ADDR: reason}
    out = _call({"t": _token()})

    assert out["ok"] is True and out["already"] is True
    assert store.suppression == {ADDR: reason}, "the reason may not be weakened"
    assert "resubscribe_token" not in out, (
        "an already-suppressed address must not hand out an undo capability — that is the "
        "second half of the same escalation")


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


def test_a_one_click_body_can_never_select_the_action(store):
    """A mail client's own body must not be able to select the action. `action` is read
    from OUR json, and a form body carrying action=resubscribe is not our json."""
    _call({"t": _token()})
    out = _call({"t": _token()}, body=b"action=resubscribe&List-Unsubscribe=One-Click")
    assert out["state"] == "unsubscribed"
    assert store.suppression == {ADDR: "unsubscribe"}


def test_the_query_string_door_is_shut_too(store):
    """THE ONE THAT ACTUALLY WORKED, and which the test named for it never touched.

    The body check above closed a door mail clients cannot open anyway; the action was
    read from the QUERY STRING first, so ``POST /api/email/unsubscribe?t=<any footer
    token>&action=resubscribe`` with a one-click body returned 200 and DELETED the
    suppression. Anyone who could read one of the target's emails could silently reverse
    their opt-out.

    Two independent things now stop it, and both are asserted: the action is not read from
    the query string at all, and the token is scoped to `unsubscribe` so it could not
    authorise a resubscribe even if it were.
    """
    _call({"t": _token()})
    assert store.suppression == {ADDR: "unsubscribe"}

    out = _call({"t": _token(), "action": "resubscribe"},
                body=b"List-Unsubscribe=One-Click")
    assert out["state"] == "unsubscribed", "the query string must not select the action"
    assert store.suppression == {ADDR: "unsubscribe"}, "nothing may have been lifted"


def test_an_unsubscribe_token_does_not_verify_for_a_resubscribe(store):
    """The signature covers the ACTION. Belt and braces behind the parameter removal: even
    a caller who gets `action=resubscribe` past the reader is presenting a token minted for
    a different action, and gets the same 400 a forged one does."""
    tok = _token()
    assert mailer.verify_unsub_token(tok, "unsubscribe") == UID
    assert mailer.verify_unsub_token(tok, "resubscribe") is None

    _call({"t": tok})
    with pytest.raises(HTTPException) as e:
        _resub(store, tok)
    assert e.value.status_code == 400
    assert store.suppression == {ADDR: "unsubscribe"}


# ===========================================================================
# Resubscribe — a second action, its own capability, never the default
# ===========================================================================
def test_resubscribe_lifts_an_unsubscribe_and_clears_the_opt_out(store):
    tok = _undo(store)
    assert tok, "a newly recorded opt-out hands back the undo capability"
    assert store.suppression == {ADDR: "unsubscribe"} and store.prefs == {UID: True}
    out = _resub(store, tok)
    assert out["state"] == "subscribed"
    assert store.suppression == {} and store.prefs == {UID: False}


def test_the_undo_capability_is_only_minted_for_a_NEW_opt_out(store):
    """The reason the undo is not simply "a resubscribe token in every reply".

    A token that came back for an ALREADY-suppressed address would rebuild the exact
    escalation the action scope closes: read one of the target's emails, POST the footer
    token, collect an undo capability for a choice somebody else made, put them back on
    the list. Undoing something you did a second ago is a courtesy; undoing a standing
    choice is the vulnerability.
    """
    first = _call({"t": _token()})
    second = _call({"t": _token()})
    assert first.get("resubscribe_token"), "the request that recorded it may undo it"
    assert second["already"] is True
    assert "resubscribe_token" not in second, "a replay must not mint a capability"


@pytest.mark.parametrize("reason", ["bounce", "complaint"])
def test_resubscribe_refuses_to_lift_a_bounce_or_a_complaint(store, reason):
    """Those record what the ADDRESS did, not what its owner chose. Re-arming the exact
    send that damaged our sending reputation because a link was clicked is how a domain
    gets blocklisted — and the reader is told plainly rather than silently ignored."""
    store.suppression = {ADDR: reason}
    out = _resub(store, _token(action="resubscribe"))
    assert out["refused"] == reason
    assert out["state"] == "unsubscribed"
    assert store.suppression == {ADDR: reason}, "the row must survive"
    assert store.prefs == {}, "and the opt-out must not be cleared either"


def test_an_unknown_action_falls_back_to_unsubscribing(store):
    """The stricter direction. A typo or a hand-rolled request can never turn an
    unsubscribe link into a re-subscribe."""
    out = _call({}, body=json.dumps({"t": _token(), "action": "surprise"}).encode())
    assert out["state"] == "unsubscribed"
    assert store.suppression == {ADDR: "unsubscribe"}


def test_manual_suppressions_are_liftable_by_their_owner(store):
    store.suppression = {ADDR: "manual"}
    out = _resub(store, _token(action="resubscribe"))
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


def test_the_mask_is_a_fixed_width_and_does_not_leak_the_length():
    """A bullet run sized to the local part printed the ONE fact a mask exists to hide.
    `a@x.com` and `alexandra.hamilton@x.com` must be indistinguishable after the head."""
    short = unsub.mask("ab.cd@example.com")
    long = unsub.mask("alexandra.hamilton.jones@example.com")
    assert short.count("•") == long.count("•")
    assert len(short) == len(long)


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
