"""admin.server — live localhost round-trip over the read-only routes (no external network)."""
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin import analytics_first_party as fp
from admin.server import (Handler, _api_cache_ttl, _cacheable_api_get,
                          _clear_response_cache, _host_only, _int_param)


def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
        return r.status, r.read()


def _get_with_headers(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
        return r.status, r.read(), dict(r.headers)


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


def test_static_bundle_is_content_versioned_and_immutable():
    httpd, port = _server()
    try:
        _, index, index_headers = _get_with_headers(port, "/")
        app_match = re.search(rb'app\.js\?v=([0-9a-f]{12})', index)
        css_match = re.search(rb'styles\.css\?v=([0-9a-f]{12})', index)
        assert app_match and css_match
        assert index_headers["Cache-Control"] == "no-store"

        _, _, app_headers = _get_with_headers(
            port, f"/app.js?v={app_match.group(1).decode()}"
        )
        assert app_headers["Cache-Control"] == "public, max-age=31536000, immutable"
        assert app_headers["ETag"] == f'"{app_match.group(1).decode()}"'
    finally:
        httpd.shutdown(); httpd.server_close()


def test_read_only_api_response_is_reused_briefly(monkeypatch):
    from admin import server

    calls = 0

    def fake_health():
        nonlocal calls
        calls += 1
        return {"healthy": True, "call": calls}

    monkeypatch.setattr(server.health, "summary", fake_health)
    _clear_response_cache()
    httpd, port = _server()
    try:
        _, first, first_headers = _get_with_headers(port, "/api/health?cache_test=1")
        _, second, second_headers = _get_with_headers(port, "/api/health?cache_test=1")
        assert json.loads(first)["call"] == 1
        assert json.loads(second)["call"] == 1
        assert calls == 1
        assert first_headers["X-Admin-Cache"] == "MISS"
        assert second_headers["X-Admin-Cache"] == "HIT"
        # Private API data is still forbidden from browser/edge caches.
        assert second_headers["Cache-Control"] == "no-store"
    finally:
        _clear_response_cache()
        httpd.shutdown(); httpd.server_close()


def test_runtime_state_is_on_demand_no_store_and_below_auth_gate(monkeypatch):
    from admin import server

    calls = 0

    def fake_snapshot():
        nonlocal calls
        calls += 1
        return ({"schema": "mastermind.runtime_state.v1", "call": calls}, 200)

    monkeypatch.setattr(server.runtime_state, "snapshot", fake_snapshot)
    _clear_response_cache()
    httpd, port = _server()
    try:
        _, first, first_headers = _get_with_headers(port, "/api/runtime-state")
        _, second, second_headers = _get_with_headers(port, "/api/runtime-state")
        assert json.loads(first)["call"] == 1
        assert json.loads(second)["call"] == 2
        assert calls == 2
        assert first_headers["Cache-Control"] == "no-store"
        assert second_headers["Cache-Control"] == "no-store"
        assert "X-Admin-Cache" not in second_headers
    finally:
        _clear_response_cache()
        httpd.shutdown(); httpd.server_close()

    source = (Path(__file__).resolve().parent.parent / "admin" / "server.py").read_text()
    body = source.split("def do_GET", 1)[1]
    assert body.index('"authentication required"') < body.index('"/api/runtime-state"')
    assert "/api/runtime-state" not in Handler._PUBLIC_GET


def test_runtime_state_refuses_an_unauthenticated_read(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "test-password")
    httpd, port = _server()
    try:
        try:
            _get(port, "/api/runtime-state")
            raise AssertionError("expected 401")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
            assert json.loads(exc.read())["error"] == "authentication required"
    finally:
        httpd.shutdown(); httpd.server_close()


def test_summary_parses_large_config_once(monkeypatch):
    from admin import server

    shared = {"notify": {"site_url": "https://example.test"}}
    reads = 0
    consumers = []

    def read_config():
        nonlocal reads
        reads += 1
        return shared

    def uses_config(cfg=None):
        consumers.append(cfg)
        return {}

    monkeypatch.setattr(server.config_store, "read_config", read_config)
    monkeypatch.setattr(server, "_repo_summary", uses_config)
    monkeypatch.setattr(server.flags, "snapshot", uses_config)
    monkeypatch.setattr(server.brief, "panel", uses_config)
    monkeypatch.setattr(server.ai_cost, "estimate", uses_config)
    monkeypatch.setattr(server.health, "summary", lambda: {})
    monkeypatch.setattr(server.gitops, "status", lambda: {})
    monkeypatch.setattr(server.system, "snapshot", lambda: {})
    monkeypatch.setattr(server.services, "status", lambda: {})
    monkeypatch.setattr(server.experiments, "alert_summary", lambda: {})
    # key_alerts.panel() and program_watch.panel() take no cfg — they compose the
    # landing rails from committed artifacts, so they are NOT among the shared-config
    # consumers asserted below.
    monkeypatch.setattr(server.key_alerts, "panel", lambda: {})
    monkeypatch.setattr(server.program_watch, "panel", lambda: {})

    result = server._summary_payload()

    assert reads == 1
    assert consumers == [shared, shared, shared, shared]
    # Every panel the landing renders. "key_alerts" joined the payload in #4612 and
    # app.js reads it (renderKeyAlerts(s.key_alerts)); this suite was enumerated by no
    # CI job until 2026-08-06, so the stale set sat red on main instead of failing #4612.
    # "program_watch" joined it the same way (renderProgramWatch(s.program_watch)) —
    # this assertion is the enumerated contract, so a new rail must be added here too.
    assert set(result) == {
        "meta", "flags", "brief", "health", "cost", "git", "system",
        "services", "experiments", "key_alerts", "program_watch",
    }


def test_spa_reuses_recent_reads_and_prefetches_nav_targets():
    source = (Path(__file__).resolve().parent.parent
              / "admin" / "static" / "app.js").read_text()
    assert "const API_CACHE_TTL_MS = 15000" in source
    assert "function clearApiCache()" in source
    assert "generation === API_CACHE_GENERATION" in source
    assert 'it.addEventListener("pointerenter", () => scheduleTabPrefetch(id)' in source
    assert 'it.addEventListener("pointerleave", cancelTabPrefetch' in source
    assert 'neural_web: ["/api/neural_web/lobes"]' in source


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


# ---- persistent-connection framing (2026-08-19) -----------------------------
# The console now speaks HTTP/1.1, so every API call reuses one connection instead
# of paying a fresh handshake and worker thread. That makes response FRAMING
# load-bearing in a way it was not while every connection closed after its body.

def test_admin_speaks_http_11():
    assert Handler.protocol_version == "HTTP/1.1"


def test_idle_connections_cannot_pin_a_thread_forever():
    assert Handler.timeout, (
        "a keep-alive handler with no socket timeout leaks a ThreadingHTTPServer "
        "worker per idle connection"
    )


class _RecordingHandler(Handler):
    """Capture what _json_body puts on the wire without opening a socket."""

    def __init__(self):                       # bypass BaseHTTPRequestHandler setup
        self.sent_headers = []
        self.written = b""
        self.code = None
        self._response_cache_key = None

    def send_response(self, code, *a):
        self.code = code

    def send_header(self, key, value):
        self.sent_headers.append((key, value))

    def end_headers(self):
        pass

    @property
    def wfile(self):
        outer = self

        class _W:
            def write(self, b):
                outer.written += b
        return _W()


def test_no_content_responses_carry_no_body():
    """204/304 must send neither a body nor a Content-Length.

    /favicon.ico answers 204. On the old close-after-body connection a stray body
    was invisible; on a persistent one the client reads it as the head of the NEXT
    response — which is how a perfectly healthy endpoint starts returning
    unparseable JSON to the panel that asked for it.
    """
    for code in (204, 304):
        h = _RecordingHandler()
        h._json_body(b'{"ignored": true}', code=code)
        assert h.written == b"", f"{code} wrote a body"
        assert not any(k.lower() == "content-length" for k, _ in h.sent_headers), \
            f"{code} sent a Content-Length"


def test_ordinary_responses_still_carry_body_and_length():
    h = _RecordingHandler()
    h._json_body(b'{"a": 1}', code=200)
    assert h.written == b'{"a": 1}'
    assert ("Content-Length", "8") in h.sent_headers


# ---- analytics fan-out (2026-08-19) -----------------------------------------
# Each analytics surface used to issue its statements in SEQUENCE — the default tab
# fired six — so a panel paid the SUM of its round trips. They now go out as one
# wave under a whole-surface deadline, which is what keeps a slow panel returning a
# JSON error instead of the CDN edge's HTML error page.

def _analytics_configured():
    """_guard short-circuits on an unconfigured reader, before the machinery under
    test runs. Returns a restore callable (no fixture — this file's __main__ runner
    calls tests with no arguments)."""
    original = fp.status
    fp.status = lambda: {"configured": True, "project_ref": "test",
                         "reason": None, "setup_steps": []}
    return lambda: setattr(fp, "status", original)


def test_analytics_parallel_runs_thunks_concurrently():
    barrier = threading.Barrier(3, timeout=5)

    def wait():
        barrier.wait()          # only returns if all three are in flight at once
        return "done"

    assert fp._parallel(a=wait, b=wait, c=wait) == {
        "a": "done", "b": "done", "c": "done"}


def test_analytics_deadline_reaches_the_worker_threads():
    """ThreadPoolExecutor does not propagate contextvars on its own.

    Without the per-thunk context copy every fan-out query would silently fall back
    to its own full timeout and the whole-surface budget would bound nothing.
    """
    restore = _analytics_configured()
    try:
        seen = []

        def probe():
            seen.append(fp._remaining_budget())
            return 1

        fp._guard(lambda: (fp._parallel(a=probe, b=probe), {})[1])
        assert len(seen) == 2
        assert all(v is not None and v > 0 for v in seen), \
            f"deadline did not reach the worker threads: {seen}"
    finally:
        restore()


def test_analytics_query_refuses_once_the_budget_is_spent():
    """An exhausted budget raises — so _guard renders JSON — rather than dialing out."""
    original_pat = fp.settings.supabase_pat
    fp.settings.supabase_pat = lambda: "sbp_test"
    token = fp._DEADLINE.set(time.monotonic() - 1.0)     # already past
    try:
        fp._query("select 1")
    except TimeoutError as exc:
        assert "budget" in str(exc)
    else:
        raise AssertionError("expected TimeoutError on an exhausted budget")
    finally:
        fp._DEADLINE.reset(token)
        fp.settings.supabase_pat = original_pat


def test_analytics_guard_still_returns_json_shaped_errors():
    """Whatever fails underneath, the SPA envelope stays {ok: False, error: ...}."""
    restore = _analytics_configured()
    try:
        def boom():
            raise RuntimeError("upstream exploded")

        out = fp._guard(boom)
        assert out["ok"] is False
        assert "upstream exploded" in out["error"]
    finally:
        restore()


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn(); print("PASS", fn.__name__)


def test_analytics_panels_get_a_longer_response_cache_than_other_apis():
    """The fp panels are window snapshots, not live readings — 15s was shorter than
    the time it takes to read one, so every trip back to a tab re-folded the panel."""
    assert _api_cache_ttl("/api/analytics/fp/visitors") == 60.0
    assert _api_cache_ttl("/api/analytics/fp/overview") == 60.0
    assert _api_cache_ttl("/api/health") == 15.0
    assert _api_cache_ttl("/api/users") == 15.0


def test_the_one_live_analytics_reading_is_still_never_cached():
    """The "N active" pill polls /fp/realtime. It is the only number on that screen
    the operator watches for freshness, so the longer TTL above must not reach it."""
    assert not _cacheable_api_get("/api/analytics/fp/realtime", {})
    assert _cacheable_api_get("/api/analytics/fp/visitors", {})
