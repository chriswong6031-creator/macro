"""admin.server — live localhost round-trip over the read-only routes (no external network)."""
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin.server import Handler, _host_only, _int_param


def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
        return r.status, r.read()


def test_static_and_local_api_routes():
    httpd, port = _server()
    try:
        # SPA shell
        code, body = _get(port, "/")
        assert code == 200 and b"Mastermind Admin" in body

        # static asset
        code, _ = _get(port, "/app.js")
        assert code == 200

        # local JSON routes (no external network: health/cost/flags/brief/git/summary)
        for path, key in [("/api/health", "healthy"), ("/api/cost", "monthly_usd"),
                          ("/api/flags", "groups"), ("/api/brief", "master_brain"),
                          ("/api/git", "branch"), ("/api/summary", "flags")]:
            code, body = _get(port, path)
            assert code == 200, f"{path} → {code}"
            assert key in json.loads(body), f"{path} missing {key}"

        # unknown route → 404 JSON
        try:
            _get(port, "/api/nope")
            raise AssertionError("expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        httpd.shutdown(); httpd.server_close()


def _post(port, path, body, headers=None, host=None):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                data=json.dumps(body).encode(), headers=h, method="POST")
    if host:
        req.add_header("Host", host)
    return urllib.request.urlopen(req, timeout=10)


def test_post_requires_json_content_type():
    """CSRF guard: a cross-site 'simple request' (text/plain) is rejected (415)."""
    httpd, port = _server()
    try:
        try:
            _post(port, "/api/flags/toggle", {"path": "x", "value": True},
                  headers={"Content-Type": "text/plain"})
            raise AssertionError("expected 415")
        except urllib.error.HTTPError as e:
            assert e.code == 415 and "application/json" in json.loads(e.read())["error"]
    finally:
        httpd.shutdown(); httpd.server_close()


def test_forged_host_rejected():
    """DNS-rebinding guard: a non-loopback Host header is rejected."""
    httpd, port = _server()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/health")
        req.add_header("Host", "evil.example.com")
        try:
            urllib.request.urlopen(req, timeout=10)
            raise AssertionError("expected 403")
        except urllib.error.HTTPError as e:
            assert e.code == 403
    finally:
        httpd.shutdown(); httpd.server_close()


def test_dispatch_ref_must_be_main():
    httpd, port = _server()
    try:
        try:
            _post(port, "/api/deploy/dispatch",
                  {"confirm": True, "workflow": "pages.yml", "ref": "feature-branch"})
            raise AssertionError("expected 400")
        except urllib.error.HTTPError as e:
            assert e.code == 400 and "ref must be main" in json.loads(e.read())["error"]
    finally:
        httpd.shutdown(); httpd.server_close()


def test_toggle_rejects_unmanaged_path():
    httpd, port = _server()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/flags/toggle",
            data=json.dumps({"path": "not.a.real.flag", "value": True}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            raise AssertionError("expected 400")
        except urllib.error.HTTPError as e:
            assert e.code == 400
            assert "unmanaged" in json.loads(e.read())["error"]
    finally:
        httpd.shutdown(); httpd.server_close()


def test_int_param_happy_and_clamp():
    """_int_param returns default on missing/bad values and clamps to [lo, hi]."""
    # normal parse
    assert _int_param({"days": ["14"]}, "days", 7, 1, 365) == 14
    # missing key → default
    assert _int_param({}, "days", 7, 1, 365) == 7
    # non-numeric → default
    assert _int_param({"days": ["abc"]}, "days", 7, 1, 365) == 7
    # below lo → clamped to lo
    assert _int_param({"limit": ["0"]}, "limit", 30, 1, 1000) == 1
    # above hi → clamped to hi
    assert _int_param({"limit": ["99999"]}, "limit", 30, 1, 1000) == 1000
    # exactly at bounds
    assert _int_param({"days": ["1"]}, "days", 7, 1, 365) == 1
    assert _int_param({"days": ["365"]}, "days", 7, 1, 365) == 365


def test_host_only_bare_ipv6():
    """_host_only must return bare IPv6 addresses unchanged (no port stripping)."""
    assert _host_only("::1") == "::1"
    assert _host_only("2001:db8::1") == "2001:db8::1"
    # bracketed form with port is still stripped correctly
    assert _host_only("[::1]:8080") == "::1"
    # plain host:port
    assert _host_only("localhost:8080") == "localhost"
    # plain host, no port
    assert _host_only("localhost") == "localhost"


def test_body_size_cap():
    """_body() returns {} without reading when Content-Length > 1_000_000."""
    import io
    import unittest.mock as mock

    # Build a minimal fake handler to exercise _body() directly.
    h = object.__new__(Handler)
    # Simulate a large Content-Length header.
    h.headers = {"Content-Length": "1100000"}
    # rfile should never be read when the cap fires; wrap a sentinel to assert that.
    h.rfile = mock.MagicMock()
    result = h._body()
    assert result == {}, f"expected empty dict, got {result!r}"
    h.rfile.read.assert_not_called()

    # A normal-sized body is still parsed.
    payload = b'{"key": "value"}'
    h2 = object.__new__(Handler)
    h2.headers = {"Content-Length": str(len(payload))}
    h2.rfile = io.BytesIO(payload)
    result2 = h2._body()
    assert result2 == {"key": "value"}


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn(); print("PASS", fn.__name__)
