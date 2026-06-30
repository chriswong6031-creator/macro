"""admin.auth + deployed-mode auth gate — session signing, CSRF, login throttle,
and a live round-trip proving protected routes require a session."""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin import auth, settings  # noqa: E402
from admin.server import Handler  # noqa: E402


def _set_env(**kw):
    old = {k: os.environ.get(k) for k in kw}
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return old


def _restore(old):
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _reset_throttle():
    auth._attempts.clear()


# ---- unit: session signing ---------------------------------------------------
def test_session_roundtrip_and_tamper():
    old = _set_env(ADMIN_SESSION_SECRET="unit-test-secret")
    try:
        tok = auth.mint_session()
        assert auth.valid_session(tok)
        # tampered body / signature must fail
        body, _, sig = tok.partition(".")
        assert not auth.valid_session(body + ".deadbeef")
        assert not auth.valid_session("x" * 10 + "." + sig)
        assert not auth.valid_session(None) and not auth.valid_session("no-dot")
        # a session signed with a different secret must not validate
        _set_env(ADMIN_SESSION_SECRET="other-secret")
        assert not auth.valid_session(tok)
    finally:
        _restore(old)


def test_session_expiry():
    old = _set_env(ADMIN_SESSION_SECRET="unit-test-secret", ADMIN_SESSION_TTL_HOURS="1")
    try:
        import base64
        # hand-mint an already-expired payload with a valid signature
        payload = base64.urlsafe_b64encode(
            json.dumps({"iat": 0, "exp": int(time.time()) - 5}).encode()).decode().rstrip("=")
        tok = f"{payload}.{auth._sign(payload.encode())}"
        assert not auth.valid_session(tok)
    finally:
        _restore(old)


def test_password_and_lockout():
    old = _set_env(ADMIN_PASSWORD="hunter2")
    _reset_throttle()
    try:
        assert auth.password_ok("hunter2")[0] is True
        _reset_throttle()
        assert auth.password_ok("wrong")[0] is False
        # five failures → locked
        for _ in range(5):
            auth.password_ok("nope")
        ok, err = auth.password_ok("hunter2")   # correct, but locked out
        assert ok is False and "locked" in (err or "")
    finally:
        _reset_throttle()
        _restore(old)


def test_lockout_is_per_client_not_global():
    """An attacker hammering from one IP must NOT lock out the operator's IP."""
    old = _set_env(ADMIN_PASSWORD="hunter2")
    _reset_throttle()
    try:
        for _ in range(8):                       # attacker IP trips its own lockout
            auth.password_ok("nope", client_id="9.9.9.9")
        assert auth.password_ok("hunter2", client_id="9.9.9.9")[0] is False  # attacker locked
        # the operator, on a different IP, is unaffected and logs in fine
        assert auth.password_ok("hunter2", client_id="1.2.3.4")[0] is True
    finally:
        _reset_throttle()
        _restore(old)


def test_csrf_double_submit():
    assert auth.csrf_ok("abc", "abc") is True
    assert auth.csrf_ok("abc", "xyz") is False
    assert auth.csrf_ok(None, "abc") is False
    assert auth.csrf_ok("abc", None) is False


def test_startup_check_requires_password_when_deployed():
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_PASSWORD=None)
    try:
        raised = False
        try:
            settings.startup_check()
        except SystemExit:
            raised = True
        assert raised, "deployed mode with no password must refuse to start"
    finally:
        _restore(old)


# ---- integration: live deployed-mode gate ------------------------------------
def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _req(port, path, method="GET", body=None, cookies=None, headers=None):
    h = dict(headers or {})
    if body is not None:
        h["Content-Type"] = "application/json"
    if cookies:
        h["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h, method=method)
    return urllib.request.urlopen(req, timeout=10)


def test_deployed_mode_requires_session():
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_PASSWORD="s3cret",
                   ADMIN_SESSION_SECRET="it-secret")
    _reset_throttle()
    httpd, port = _server()
    try:
        # /api/session is public and reports the locked state
        r = _req(port, "/api/session")
        sess = json.loads(r.read())
        assert sess["auth_enabled"] is True and sess["authenticated"] is False
        assert sess["deployed"] is True

        # a protected route is 401 without a session
        try:
            _req(port, "/api/health")
            raise AssertionError("expected 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401

        # wrong password → 401
        try:
            _req(port, "/api/login", "POST", {"password": "nope"})
            raise AssertionError("expected 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401

        # correct password → 200 + Set-Cookie (session + csrf)
        r = _req(port, "/api/login", "POST", {"password": "s3cret"})
        setc = r.headers.get_all("Set-Cookie") or []
        jar = {}
        for c in setc:
            k, _, rest = c.partition("=")
            jar[k] = rest.split(";")[0]
        assert auth.SESSION_COOKIE in jar and auth.CSRF_COOKIE in jar
        assert "Secure" in " ".join(setc) and "HttpOnly" in " ".join(setc)

        # with the session cookie, the protected route works
        r = _req(port, "/api/health", cookies={auth.SESSION_COOKIE: jar[auth.SESSION_COOKIE]})
        assert r.status == 200

        # a write WITHOUT the CSRF header is rejected (403) even with a valid session
        try:
            _req(port, "/api/flags/toggle", "POST", {"path": "x", "value": True},
                 cookies={auth.SESSION_COOKIE: jar[auth.SESSION_COOKIE],
                          auth.CSRF_COOKIE: jar[auth.CSRF_COOKIE]})
            raise AssertionError("expected 403 (missing CSRF header)")
        except urllib.error.HTTPError as e:
            assert e.code == 403 and "CSRF" in json.loads(e.read())["error"]

        # write WITH a matching CSRF header passes auth+csrf (then 400 on unmanaged path)
        try:
            _req(port, "/api/flags/toggle", "POST", {"path": "not.real", "value": True},
                 cookies={auth.SESSION_COOKIE: jar[auth.SESSION_COOKIE],
                          auth.CSRF_COOKIE: jar[auth.CSRF_COOKIE]},
                 headers={auth.CSRF_HEADER: jar[auth.CSRF_COOKIE]})
            raise AssertionError("expected 400 (unmanaged flag, past auth)")
        except urllib.error.HTTPError as e:
            assert e.code == 400 and "unmanaged" in json.loads(e.read())["error"]
    finally:
        httpd.shutdown(); httpd.server_close()
        _reset_throttle(); _restore(old)
