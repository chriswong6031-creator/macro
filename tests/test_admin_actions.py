"""tests/test_admin_actions.py — Unit + HTTP-level tests for admin.actions (NW Rails PR-8).

Tests
-----
1. test_append_basic         — happy-path row written with correct fields
2. test_note_capped          — direction_note silently capped at 280 chars
3. test_latency_computed     — latency_s computed from alert_emit_ts
4. test_latency_none_on_bad_ts — bad emit ts → latency_s is None (no raise)
5. test_latency_none_when_absent — no emit ts → latency_s is None
6. test_invalid_action_recorded — action value is stored verbatim (validation is server's job)
7. test_io_error_swallowed   — IO error does NOT raise to caller
8. test_multiple_appends     — multiple calls append multiple lines
9. test_http_post_actions_ok — HTTP POST /api/actions returns {ok, row} (HTTP-level)
10. test_http_post_actions_bad_action — unknown action → 400
11. test_http_post_actions_missing_surface → 400
"""
from __future__ import annotations

import json
import sys
import threading
import unittest.mock
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from admin.actions import VALID_ACTIONS, NOTE_MAX_CHARS, append_action  # noqa: E402
from admin.server import Handler  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


def _post(port, path, body, headers=None):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        headers=h,
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=10)


# ---------------------------------------------------------------------------
# Unit tests for admin.actions
# ---------------------------------------------------------------------------

def test_append_basic(tmp_path):
    """Happy-path: row written with correct required fields."""
    ledger = tmp_path / "action_ledger.jsonl"
    with unittest.mock.patch("admin.actions._ledger_path", return_value=ledger):
        row = append_action(surface="exp-abc", action="acted", direction_note="looked good")
    assert ledger.exists()
    written = json.loads(ledger.read_text().strip())
    assert written["actor"] == "operator"
    assert written["surface"] == "exp-abc"
    assert written["action"] == "acted"
    assert written["direction_note"] == "looked good"
    assert "ts" in written
    # Verify row returned matches what was written
    assert row["surface"] == "exp-abc"
    assert row["action"] == "acted"


def test_note_capped(tmp_path):
    """direction_note is silently capped at NOTE_MAX_CHARS."""
    ledger = tmp_path / "action_ledger.jsonl"
    long_note = "x" * 500
    with unittest.mock.patch("admin.actions._ledger_path", return_value=ledger):
        row = append_action(surface="exp-note", action="dismissed", direction_note=long_note)
    assert len(row["direction_note"]) == NOTE_MAX_CHARS
    written = json.loads(ledger.read_text().strip())
    assert len(written["direction_note"]) == NOTE_MAX_CHARS


def test_latency_computed(tmp_path):
    """latency_s is computed from a valid alert_emit_ts."""
    from datetime import datetime, timedelta, timezone
    ledger = tmp_path / "action_ledger.jsonl"
    # Emit ts 30 seconds ago
    emit = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    with unittest.mock.patch("admin.actions._ledger_path", return_value=ledger):
        row = append_action(surface="alert-001", action="acted", direction_note="", alert_emit_ts=emit)
    # latency_s should be ~30 (allow 10s window for test runner slowness)
    assert row["latency_s"] is not None
    assert 20 <= row["latency_s"] <= 60


def test_latency_none_on_bad_ts(tmp_path):
    """A malformed alert_emit_ts does not raise — latency_s is None."""
    ledger = tmp_path / "action_ledger.jsonl"
    with unittest.mock.patch("admin.actions._ledger_path", return_value=ledger):
        row = append_action(surface="exp-x", action="snoozed", direction_note="", alert_emit_ts="not-a-date")
    assert row["latency_s"] is None


def test_latency_none_when_absent(tmp_path):
    """When alert_emit_ts is omitted, latency_s is None."""
    ledger = tmp_path / "action_ledger.jsonl"
    with unittest.mock.patch("admin.actions._ledger_path", return_value=ledger):
        row = append_action(surface="exp-y", action="overrode", direction_note="manual")
    assert row["latency_s"] is None


def test_io_error_swallowed(tmp_path):
    """IO errors (e.g. unwritable path) must NOT raise to the caller."""
    import unittest.mock
    # Patch open to raise OSError
    with unittest.mock.patch("builtins.open", side_effect=OSError("disk full")):
        with unittest.mock.patch("admin.actions._ledger_path", return_value=tmp_path / "x.jsonl"):
            # Must not raise
            row = append_action(surface="exp-z", action="dismissed", direction_note="test")
    # Row is still returned
    assert row["surface"] == "exp-z"


def test_multiple_appends(tmp_path):
    """Multiple calls append multiple JSONL lines."""
    ledger = tmp_path / "action_ledger.jsonl"
    with unittest.mock.patch("admin.actions._ledger_path", return_value=ledger):
        append_action(surface="a", action="acted", direction_note="first")
        append_action(surface="b", action="dismissed", direction_note="second")
        append_action(surface="c", action="snoozed", direction_note="third")
    lines = ledger.read_text().strip().splitlines()
    assert len(lines) == 3
    surfaces = [json.loads(l)["surface"] for l in lines]
    assert surfaces == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# HTTP-level tests for POST /api/actions
# ---------------------------------------------------------------------------

def test_http_post_actions_ok(tmp_path):
    """POST /api/actions with valid payload returns {ok: true, row: {...}}."""
    ledger = tmp_path / "action_ledger.jsonl"
    httpd, port = _server()
    try:
        with unittest.mock.patch("admin.actions._ledger_path", return_value=ledger):
            resp = _post(port, "/api/actions", {
                "surface": "exp-http-1",
                "action": "acted",
                "direction_note": "http test",
            })
            data = json.loads(resp.read())
        assert data["ok"] is True
        assert data["row"]["surface"] == "exp-http-1"
        assert data["row"]["action"] == "acted"
        assert data["row"]["actor"] == "operator"
    finally:
        httpd.shutdown(); httpd.server_close()


def test_http_post_actions_bad_action():
    """POST /api/actions with an unknown action returns 400."""
    httpd, port = _server()
    try:
        try:
            _post(port, "/api/actions", {
                "surface": "exp-bad",
                "action": "not_a_valid_action",
                "direction_note": "",
            })
            raise AssertionError("expected 400")
        except urllib.error.HTTPError as e:
            assert e.code == 400
            body = json.loads(e.read())
            assert "action" in body["error"]
    finally:
        httpd.shutdown(); httpd.server_close()


def test_http_post_actions_missing_surface():
    """POST /api/actions without a surface field returns 400."""
    httpd, port = _server()
    try:
        try:
            _post(port, "/api/actions", {
                "action": "acted",
                "direction_note": "no surface",
            })
            raise AssertionError("expected 400")
        except urllib.error.HTTPError as e:
            assert e.code == 400
            body = json.loads(e.read())
            assert "surface" in body["error"]
    finally:
        httpd.shutdown(); httpd.server_close()


if __name__ == "__main__":
    import tempfile, os
    for fn_name in sorted(k for k in globals() if k.startswith("test_")):
        fn = globals()[fn_name]
        # inject tmp_path for functions that need it
        import inspect
        sig = inspect.signature(fn)
        if "tmp_path" in sig.parameters:
            with tempfile.TemporaryDirectory() as td:
                fn(Path(td))
        else:
            fn()
        print("PASS", fn_name)
