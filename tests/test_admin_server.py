"""admin.server — live localhost round-trip over the read-only routes (no external network)."""
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin.server import Handler


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
        assert code == 200 and b"Macro Admin" in body

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
    """CSRF guard: a cross-site 'simple request' (text/plain) is rejected with 403."""
    httpd, port = _server()
    try:
        try:
            _post(port, "/api/flags/toggle", {"path": "x", "value": True},
                  headers={"Content-Type": "text/plain"})
            raise AssertionError("expected 403")
        except urllib.error.HTTPError as e:
            assert e.code == 403 and "application/json" in json.loads(e.read())["error"]
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


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn(); print("PASS", fn.__name__)
