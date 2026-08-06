"""admin/users.py — operator password reset (GoTrue admin API, service-role).

Two planes, mocked separately, mirroring test_admin_entitlements:

  * LOOKUP (read) → monkeypatch ``admin.users._query`` + ``admin.users.status``
    (the Management-API PAT SELECT).
  * SET (write)   → monkeypatch ``app.billing.SUPABASE_SERVICE_ROLE_KEY`` and
    ``admin.users.requests`` so the GoTrue PUT is captured, never sent.

What these pin, beyond "it returns ok":

  * the WRITE degrades to 503 with setup steps when the service-role key is unset
    (the module must not raise, and must not pretend it reset anything);
  * validation happens BEFORE the network call, so a rejected password can never
    reach GoTrue as a half-applied write;
  * a generated password is returned exactly once and never lands in the operator
    ledger note (the ledger records THAT a reset happened, not the secret);
  * a non-2xx from GoTrue surfaces GoTrue's own body — a weak-password policy
    rejection and a dead service-role key are indistinguishable otherwise.
"""
from __future__ import annotations

import pytest

from admin import users


class _Resp:
    def __init__(self, status_code=200, text='{"id":"u-1"}'):
        self.status_code = status_code
        self.text = text


class _FakeRequests:
    """Captures the GoTrue call instead of making it."""

    def __init__(self, resp=None):
        self.calls = []
        self._resp = resp or _Resp()

    def put(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        return self._resp


USER_ROW = {
    "user_id": "11111111-2222-3333-4444-555555555555",
    "email": "customer@example.com",
    "name": "A Customer",
    "provider": "email",
    "confirmed": True,
    "last_sign_in_at": "2026-08-01 10:00",
}


@pytest.fixture
def wired(monkeypatch):
    """Read plane configured + one matching user; write plane armed with a fake key."""
    from app import billing

    monkeypatch.setattr(users, "status", lambda: {
        "configured": True, "project_ref": "ref", "reason": None, "setup_steps": []})
    monkeypatch.setattr(users, "_query", lambda sql: [dict(USER_ROW)])
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_ROLE_KEY", "svc-role-test")
    monkeypatch.setattr(billing, "SUPABASE_URL", "https://proj.supabase.co")

    ledger = []
    monkeypatch.setattr(users.actions, "append_action",
                        lambda **kw: ledger.append(kw) or kw)
    fake = _FakeRequests()
    monkeypatch.setattr(users, "requests", fake)
    return fake, ledger


# --------------------------------------------------------------------------- #
# degraded: no writer
# --------------------------------------------------------------------------- #
def test_no_service_role_key_is_503_with_setup_steps(monkeypatch):
    from app import billing
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_ROLE_KEY", "")
    payload, code = users.set_password("customer@example.com")
    assert code == 503
    assert payload["ok"] is False
    assert payload["code"] == "no_writer"
    assert payload["setup_steps"], "a 503 must tell the operator how to fix it"
    assert "password" not in payload


def test_no_writer_never_calls_gotrue(monkeypatch):
    from app import billing
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_ROLE_KEY", "")
    fake = _FakeRequests()
    monkeypatch.setattr(users, "requests", fake)
    users.set_password("customer@example.com")
    assert fake.calls == []


# --------------------------------------------------------------------------- #
# lookup
# --------------------------------------------------------------------------- #
def test_unknown_user_is_404_and_never_calls_gotrue(monkeypatch, wired):
    fake, _ledger = wired
    monkeypatch.setattr(users, "_query", lambda sql: [])
    payload, code = users.set_password("ghost@example.com")
    assert code == 404
    assert payload["code"] == "not_found"
    assert fake.calls == [], "a miss must not reach the write plane"


def test_duplicate_email_refuses_rather_than_guessing(monkeypatch, wired):
    fake, _ledger = wired
    monkeypatch.setattr(users, "_query", lambda sql: [dict(USER_ROW), dict(USER_ROW)])
    payload, code = users.set_password("customer@example.com")
    assert code == 400
    assert payload["code"] == "ambiguous"
    assert fake.calls == []


def test_lookup_by_uuid_uses_the_id_column(monkeypatch, wired):
    seen = {}

    def _q(sql):
        seen["sql"] = sql
        return [dict(USER_ROW)]

    monkeypatch.setattr(users, "_query", _q)
    users.set_password(USER_ROW["user_id"], "aValidPassword1")
    assert "u.id = " in seen["sql"] and "::uuid" in seen["sql"]


def test_lit_doubles_quotes_and_strips_nul():
    """Pin _lit directly. Asserting `"''" in sql` would be VACUOUS: display_name_sql
    already emits empty-string literals, so that substring is present no matter what
    _lit does (this test caught exactly that mistake)."""
    assert users._lit("o'brien", maxlen=99) == "'o''brien'"
    assert users._lit("a\x00b", maxlen=99) == "'ab'"
    assert users._lit("x" * 50, maxlen=10) == "'" + "x" * 10 + "'"


def test_email_lookup_escapes_quotes(monkeypatch, wired):
    seen = {}

    def _q(sql):
        seen["sql"] = sql
        return []

    monkeypatch.setattr(users, "_query", _q)
    users.set_password("bob'; drop table users; --@example.com")
    # the payload appears ONLY in its doubled-quote form …
    assert "'bob''; drop table users; --@example.com'" in seen["sql"]
    # … and never as a literal that would close the string early
    assert "lower('bob'; drop" not in seen["sql"]


# --------------------------------------------------------------------------- #
# validation happens before the network call
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pw", ["", "short", "1234567"])
def test_too_short_is_rejected_before_gotrue(wired, pw):
    fake, _ledger = wired
    payload, code = users.set_password("customer@example.com", pw)
    assert code == 400
    assert "at least" in payload["error"]
    assert fake.calls == [], "validation must precede the write"


def test_over_bcrypt_limit_is_rejected_before_gotrue(wired):
    fake, _ledger = wired
    payload, code = users.set_password("customer@example.com", "x" * 73)
    assert code == 400
    assert "72" in payload["error"]
    assert fake.calls == []


def test_multibyte_password_is_measured_in_bytes_not_characters(wired):
    """bcrypt truncates at 72 BYTES — 30 emoji are well past that but only 30 chars."""
    fake, _ledger = wired
    payload, code = users.set_password("customer@example.com", "🔒" * 30)
    assert code == 400
    assert fake.calls == []


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #
def test_generated_password_is_returned_once_and_meets_the_floor(wired):
    fake, _ledger = wired
    payload, code = users.set_password("customer@example.com")
    assert code == 200 and payload["ok"] is True
    assert payload["generated"] is True
    pw = payload["password"]
    assert pw and len(pw) >= users.MIN_PASSWORD_LEN
    assert not (set(pw) & set("O0lI1")), "ambiguous glyphs must be excluded"
    # what actually went to GoTrue
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == f"https://proj.supabase.co/auth/v1/admin/users/{USER_ROW['user_id']}"
    assert call["json"] == {"password": pw}
    assert call["headers"]["apikey"] == "svc-role-test"
    assert call["headers"]["Authorization"] == "Bearer svc-role-test"


def test_operator_supplied_password_is_used_verbatim_and_not_echoed(wired):
    fake, _ledger = wired
    payload, code = users.set_password("customer@example.com", "correcthorsebattery")
    assert code == 200
    assert fake.calls[0]["json"] == {"password": "correcthorsebattery"}
    assert payload["generated"] is False
    assert payload["password"] is None, "only a GENERATED password is handed back"


def test_ledger_records_the_reset_but_never_the_secret(wired):
    fake, ledger = wired
    payload, _ = users.set_password("customer@example.com")
    assert len(ledger) == 1
    row = ledger[0]
    assert USER_ROW["email"] in row["surface"]
    blob = " ".join(str(v) for v in row.values())
    assert payload["password"] not in blob, "the ledger must not carry the password"
    # the honest caveat travels with the action
    assert "sessions" in row["direction_note"].lower()


def test_response_does_not_leak_the_service_role_key(wired):
    payload, _ = users.set_password("customer@example.com")
    assert "svc-role-test" not in str(payload)


# --------------------------------------------------------------------------- #
# failure surfaces
# --------------------------------------------------------------------------- #
def test_gotrue_rejection_surfaces_its_own_body(monkeypatch, wired):
    _fake, ledger = wired
    monkeypatch.setattr(users, "requests",
                        _FakeRequests(_Resp(422, '{"msg":"Password is known to be weak"}')))
    payload, code = users.set_password("customer@example.com", "aValidPassword1")
    assert code == 502
    assert "known to be weak" in payload["error"], "GoTrue's reason must reach the operator"
    assert ledger == [], "a failed write must not be logged as a reset"


def test_route_reaches_set_password_and_accepts_either_identifier(monkeypatch):
    """Pin the wiring, not just the module: a typo'd path would 404 silently."""
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    from admin import server as admin_server

    seen = []
    monkeypatch.setattr(
        users, "set_password",
        lambda ident, pw=None, operator="operator": (
            seen.append({"ident": ident, "pw": pw, "operator": operator})
            or ({"ok": True, "user": {"email": ident}, "password": "generated-x",
                 "generated": pw is None, "note": "n"}, 200)))

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), admin_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        def _post(body):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/users/reset_password",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())

        code, payload = _post({"email": "customer@example.com"})
        assert code == 200 and payload["ok"] is True
        assert seen[-1]["ident"] == "customer@example.com"
        assert seen[-1]["pw"] is None, "no password in the body means GENERATE one"

        _post({"user_id": USER_ROW["user_id"], "password": "operatorChosen1"})
        assert seen[-1]["ident"] == USER_ROW["user_id"], "user_id is accepted too"
        assert seen[-1]["pw"] == "operatorChosen1"

        # An empty-string password must mean "generate", not "set the empty string"
        _post({"email": "customer@example.com", "password": ""})
        assert seen[-1]["pw"] is None
    finally:
        httpd.shutdown()


def test_transport_failure_is_502_not_a_traceback(monkeypatch, wired):
    _fake, ledger = wired

    class _Boom:
        def put(self, *a, **k):
            raise OSError("connection reset")

    monkeypatch.setattr(users, "requests", _Boom())
    payload, code = users.set_password("customer@example.com", "aValidPassword1")
    assert code == 502
    assert payload["ok"] is False
    assert "connection reset" in payload["error"]
    assert ledger == []
