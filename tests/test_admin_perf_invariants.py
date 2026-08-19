"""Invariants behind the 2026-08-19 admin-console latency work.

Each test here pins a property that a plausible future edit would silently break,
and whose breakage is expensive rather than obvious:

  * the config parse cache must still reflect on-disk state (a stale admin shows
    the operator flags that are not real);
  * the analytics fan-out must actually run concurrently AND carry its deadline
    into the worker threads (that deadline is what keeps a slow panel returning a
    JSON error instead of the CDN's HTML error page — the "bad json" symptom);
  * a 204/304 must not carry a body now that connections are persistent (a stray
    body desynchronises the next response on the same connection).
"""
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin import analytics_first_party as fp
from admin import config_store as cs
from admin import server as admin_server


# ---- config parse cache -----------------------------------------------------

def _temp_config(monkeypatch, content):
    d = tempfile.mkdtemp(prefix="cfgperf_")
    p = Path(d) / "config.yml"
    p.write_text(content)
    monkeypatch.setattr(cs, "CONFIG", p)
    monkeypatch.setattr(cs, "_PARSE_CACHE", None)
    return p


def test_read_config_caches_the_parse(monkeypatch):
    """A repeat read of an UNCHANGED file must not re-parse it."""
    _temp_config(monkeypatch, "top:\n  enabled: true\n")
    calls = []
    real_load = cs.yaml.load
    monkeypatch.setattr(cs.yaml, "load",
                        lambda *a, **k: (calls.append(1), real_load(*a, **k))[1])
    assert cs.read_config() == {"top": {"enabled": True}}
    assert cs.read_config() == {"top": {"enabled": True}}
    assert cs.read_config() == {"top": {"enabled": True}}
    assert len(calls) == 1, "config.yml was re-parsed despite being unchanged"


def test_read_config_sees_an_edit_made_behind_its_back(monkeypatch):
    """The cache is a speedup, NOT a snapshot: an out-of-process edit must win.

    This is the property the old 'never cached' docstring was protecting, and it
    is the one that matters — a git pull or a hand edit on the VPS changes the
    file without this process knowing.
    """
    p = _temp_config(monkeypatch, "top:\n  enabled: true\n")
    assert cs.read_config()["top"]["enabled"] is True
    # Rewrite with a DIFFERENT size so the check does not lean on mtime alone,
    # then again at the SAME size to prove mtime is doing its half of the job.
    p.write_text("top:\n  enabled: false\n  extra: 1\n")
    assert cs.read_config()["top"]["enabled"] is False
    time.sleep(0.01)
    p.write_text("top:\n  enabled: true\n  extra: 2\n")
    assert cs.read_config()["top"]["extra"] == 2


def test_write_path_invalidates_the_cache(monkeypatch):
    """set_bool edits the file; the very next read must show the new value."""
    _temp_config(monkeypatch, "top:\n  enabled: true   # keep me\n")
    assert cs.read_config()["top"]["enabled"] is True
    assert cs.set_bool("top.enabled", False)["ok"] is True
    assert cs.read_config()["top"]["enabled"] is False


# ---- analytics fan-out ------------------------------------------------------

def test_parallel_runs_thunks_concurrently():
    """_parallel must overlap its thunks, not merely sequence them."""
    barrier = threading.Barrier(3, timeout=5)

    def wait():
        barrier.wait()          # only returns if all three run at once
        return "done"

    out = fp._parallel(a=wait, b=wait, c=wait)
    assert out == {"a": "done", "b": "done", "c": "done"}


def _configured(monkeypatch):
    """_guard short-circuits on an unconfigured reader, before any of the machinery
    under test runs — so these cases have to look connected."""
    monkeypatch.setattr(fp, "status", lambda: {
        "configured": True, "project_ref": "test", "reason": None, "setup_steps": []})


def test_parallel_carries_the_deadline_into_worker_threads(monkeypatch):
    """The budget _guard opens must be visible inside the pool.

    ThreadPoolExecutor does not propagate contextvars on its own, so this is a
    real hazard: without the per-thunk context copy every fan-out query would
    silently fall back to its own full timeout and the whole-surface budget
    would stop bounding anything.
    """
    _configured(monkeypatch)
    seen = []

    def probe():
        seen.append(fp._remaining_budget())
        return 1

    def run():
        fp._parallel(a=probe, b=probe)
        return {}

    fp._guard(run)
    assert len(seen) == 2
    assert all(v is not None and v > 0 for v in seen), \
        f"deadline did not reach the worker threads: {seen}"


def test_query_refuses_once_the_budget_is_spent(monkeypatch):
    """An exhausted budget raises (so _guard renders JSON) rather than dialing out."""
    monkeypatch.setattr(fp.settings, "supabase_pat", lambda: "sbp_test")
    monkeypatch.setattr(fp, "requests", object())   # any call would AttributeError
    token = fp._DEADLINE.set(time.monotonic() - 1.0)   # already past
    try:
        try:
            fp._query("select 1")
        except TimeoutError as exc:
            assert "budget" in str(exc)
        else:
            raise AssertionError("expected TimeoutError on an exhausted budget")
    finally:
        fp._DEADLINE.reset(token)


def test_guard_still_returns_json_shaped_errors(monkeypatch):
    """Whatever fails underneath, the SPA envelope stays {ok: False, error: ...}."""
    _configured(monkeypatch)

    def boom():
        raise RuntimeError("upstream exploded")

    out = fp._guard(boom)
    assert out["ok"] is False
    assert "upstream exploded" in out["error"]


# ---- persistent-connection framing -----------------------------------------

def test_admin_speaks_http_11():
    assert admin_server.Handler.protocol_version == "HTTP/1.1"


def test_idle_connections_cannot_pin_a_thread_forever():
    assert admin_server.Handler.timeout, \
        "a keep-alive handler with no socket timeout leaks a thread per idle connection"


def test_no_content_responses_carry_no_body():
    """204/304 must send neither a body nor a Content-Length.

    /favicon.ico answers 204. On the old close-after-body connection a stray body
    was invisible; on a persistent one the client reads it as the head of the next
    response, which is exactly how a healthy endpoint starts returning unparseable
    JSON to the panel that asked for it.
    """
    class Rec(admin_server.Handler):
        def __init__(self):            # bypass BaseHTTPRequestHandler's socket setup
            self.headers_sent = []
            self.written = b""
            self._response_cache_key = None

        def send_response(self, code, *a):
            self.code = code

        def send_header(self, k, v):
            self.headers_sent.append((k, v))

        def end_headers(self):
            pass

        @property
        def wfile(self):
            outer = self

            class W:
                def write(self, b):
                    outer.written += b
            return W()

    for code in (204, 304):
        h = Rec()
        h._json_body(b'{"ignored": true}', code=code)
        assert h.written == b"", f"{code} wrote a body"
        assert not any(k.lower() == "content-length" for k, _ in h.headers_sent), \
            f"{code} sent a Content-Length"

    ok = Rec()
    ok._json_body(b'{"a": 1}', code=200)
    assert ok.written == b'{"a": 1}'
    assert ("Content-Length", "8") in ok.headers_sent
