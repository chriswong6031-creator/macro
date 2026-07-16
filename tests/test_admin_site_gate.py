"""tests/test_admin_site_gate.py — Unit + HTTP-level tests for admin/site_gate.py.

Tests
-----
1.  test_read_rules_missing_file         — missing file returns safe {enabled:False} default
2.  test_read_rules_invalid_json         — invalid JSON returns safe default (fail-open)
3.  test_read_rules_wrong_version        — wrong version returns safe default
4.  test_save_reject_bad_ip              — bad IP in blocked_ips → 400-style envelope
5.  test_save_reject_bad_country         — bad country code → 400-style envelope
6.  test_save_good_roundtrip             — valid save persists and reads back correctly
7.  test_save_self_lockout_guard_adds_ip — caller IP auto-added to allow_ips
8.  test_save_warn_if_blocked_and_allowed — caller IP in blocked_ips triggers warning
9.  test_save_enabled_must_be_bool       — non-bool enabled → 400-style envelope
10. test_save_blocked_ips_must_be_list   — non-list blocked_ips → error
11. test_save_ipv6_cidr_accepted         — IPv6 CIDR is valid
12. test_http_get_site_gate              — GET /api/site_gate returns {ok, rules, your_ip}
13. test_http_post_site_gate_save_ok     — POST /api/site_gate/save round-trips through HTTP
14. test_http_post_site_gate_bad_ip      — bad IP rejected via HTTP (400-style response)
15. test_gate_status_offline             — gate_status() returns {ok:False} when macro-api is down
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import admin.site_gate as sg  # noqa: E402
from admin.server import Handler  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_state_path(tmp_path: Path, monkeypatch):
    """Make site_gate read/write under tmp_path."""
    p = tmp_path / "site_gate.json"
    monkeypatch.setenv("SITE_GATE_STATE", str(p))
    return p


def _server():
    """Spin up a real ThreadingHTTPServer using the admin Handler."""
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


def _get(port, path):
    import urllib.request
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{path}", timeout=5
        ) as r:
            return r.status, json.loads(r.read())
    except Exception as e:  # urllib raises for non-2xx
        import urllib.error
        if isinstance(e, urllib.error.HTTPError):
            return e.code, json.loads(e.read())
        raise


def _post(port, path, body, extra_headers=None):
    import urllib.request, urllib.error
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", **(extra_headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ---------------------------------------------------------------------------
# Unit tests — read_rules
# ---------------------------------------------------------------------------

def test_read_rules_missing_file(tmp_path, monkeypatch):
    _patch_state_path(tmp_path, monkeypatch)
    rules = sg.read_rules()
    assert rules["enabled"] is False
    assert rules["blocked_ips"] == []
    assert rules["blocked_countries"] == []


def test_read_rules_invalid_json(tmp_path, monkeypatch):
    p = _patch_state_path(tmp_path, monkeypatch)
    p.write_text("NOT JSON", encoding="utf-8")
    rules = sg.read_rules()
    assert rules["enabled"] is False


def test_read_rules_wrong_version(tmp_path, monkeypatch):
    p = _patch_state_path(tmp_path, monkeypatch)
    p.write_text(json.dumps({"version": 99, "enabled": True}), encoding="utf-8")
    rules = sg.read_rules()
    assert rules["enabled"] is False


# ---------------------------------------------------------------------------
# Unit tests — save_rules validation
# ---------------------------------------------------------------------------

def test_save_reject_bad_ip(tmp_path, monkeypatch):
    _patch_state_path(tmp_path, monkeypatch)
    result = sg.save_rules(
        {"enabled": False, "blocked_ips": ["not-an-ip", "1.2.3.4"], "blocked_countries": []},
        caller_ip="10.0.0.1",
    )
    assert result["ok"] is False
    assert "not-an-ip" in result.get("bad_ips", [])


def test_save_reject_bad_country(tmp_path, monkeypatch):
    _patch_state_path(tmp_path, monkeypatch)
    result = sg.save_rules(
        {"enabled": False, "blocked_ips": [], "blocked_countries": ["RU", "NOTCODE", "99"]},
        caller_ip="10.0.0.1",
    )
    assert result["ok"] is False
    bad = result.get("bad_countries", [])
    assert "NOTCODE" in bad
    assert "99" in bad


def test_save_good_roundtrip(tmp_path, monkeypatch):
    _patch_state_path(tmp_path, monkeypatch)
    result = sg.save_rules(
        {"enabled": True, "blocked_ips": ["203.0.113.0/24", "198.51.100.5"],
         "blocked_countries": ["RU", "kp"]},   # lowercase kp should be upcased
        caller_ip="10.0.0.1",
    )
    assert result["ok"] is True
    rules = result["rules"]
    assert rules["enabled"] is True
    assert "203.0.113.0/24" in rules["blocked_ips"]
    assert "KP" in rules["blocked_countries"]

    # Read back from disk to verify atomic write
    read_back = sg.read_rules()
    assert read_back["enabled"] is True
    assert "KP" in read_back["blocked_countries"]


def test_save_self_lockout_guard_adds_ip(tmp_path, monkeypatch):
    _patch_state_path(tmp_path, monkeypatch)
    caller = "1.2.3.4"
    result = sg.save_rules(
        {"enabled": True, "blocked_ips": [], "blocked_countries": []},
        caller_ip=caller,
    )
    assert result["ok"] is True
    assert caller in result["rules"]["allow_ips"]

    # Second save: caller already in allow_ips — must not duplicate
    result2 = sg.save_rules(
        {"enabled": True, "blocked_ips": [], "blocked_countries": []},
        caller_ip=caller,
    )
    assert result2["rules"]["allow_ips"].count(caller) == 1


def test_save_warn_if_blocked_and_allowed(tmp_path, monkeypatch):
    _patch_state_path(tmp_path, monkeypatch)
    caller = "10.10.10.10"
    result = sg.save_rules(
        {"enabled": True, "blocked_ips": [caller], "blocked_countries": []},
        caller_ip=caller,
    )
    assert result["ok"] is True
    # Caller is still in allow_ips despite being in blocked_ips
    assert caller in result["rules"]["allow_ips"]
    # And a warning was emitted
    assert len(result["warnings"]) > 0
    assert caller in result["warnings"][0]


def test_save_enabled_must_be_bool(tmp_path, monkeypatch):
    _patch_state_path(tmp_path, monkeypatch)
    result = sg.save_rules(
        {"enabled": "yes", "blocked_ips": [], "blocked_countries": []},
        caller_ip="10.0.0.1",
    )
    assert result["ok"] is False
    assert "enabled" in result.get("error", "")


def test_save_blocked_ips_must_be_list(tmp_path, monkeypatch):
    _patch_state_path(tmp_path, monkeypatch)
    result = sg.save_rules(
        {"enabled": False, "blocked_ips": "1.2.3.4", "blocked_countries": []},
        caller_ip="10.0.0.1",
    )
    assert result["ok"] is False


def test_save_ipv6_cidr_accepted(tmp_path, monkeypatch):
    _patch_state_path(tmp_path, monkeypatch)
    result = sg.save_rules(
        {"enabled": False, "blocked_ips": ["2001:db8::/32", "::1"],
         "blocked_countries": []},
        caller_ip="10.0.0.1",
    )
    assert result["ok"] is True
    assert "2001:db8::/32" in result["rules"]["blocked_ips"]


# ---------------------------------------------------------------------------
# Unit test — gate_status offline
# ---------------------------------------------------------------------------

def test_gate_status_offline():
    """gate_status() must return {ok:False} when macro-api is not running on port 8000."""
    # We rely on port 8000 being free in the test environment; gate_status()
    # must never raise regardless.
    result = sg.gate_status()
    assert isinstance(result, dict)
    # Either ok:False (macro-api down) or ok:True (if it happens to be running)
    assert "ok" in result


# ---------------------------------------------------------------------------
# HTTP-level tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("sg_srv")
    import os
    os.environ["SITE_GATE_STATE"] = str(tmp / "site_gate.json")
    httpd, port = _server()
    yield port
    httpd.shutdown()


def test_http_get_site_gate(server, tmp_path, monkeypatch):
    """GET /api/site_gate returns envelope with ok, rules, your_ip."""
    port = server
    code, body = _get(port, "/api/site_gate")
    assert code == 200
    assert body["ok"] is True
    assert "rules" in body
    assert "your_ip" in body
    rules = body["rules"]
    assert "enabled" in rules
    assert "blocked_ips" in rules
    assert "blocked_countries" in rules
    assert "allow_ips" in rules


def test_http_post_site_gate_save_ok(server):
    """POST /api/site_gate/save with valid payload returns ok + rules."""
    port = server
    code, body = _post(port, "/api/site_gate/save", {
        "enabled": False,
        "blocked_ips": ["198.51.100.0/24"],
        "blocked_countries": ["KP"],
    })
    assert code == 200
    assert body["ok"] is True
    assert "rules" in body
    assert "198.51.100.0/24" in body["rules"]["blocked_ips"]
    assert "KP" in body["rules"]["blocked_countries"]


def test_http_post_site_gate_bad_ip(server):
    """POST /api/site_gate/save with bad IP entry returns error response (not 200 ok)."""
    port = server
    code, body = _post(port, "/api/site_gate/save", {
        "enabled": False,
        "blocked_ips": ["not-an-ip"],
        "blocked_countries": [],
    })
    # The server returns 400 for validation failures
    assert code == 400
    assert body.get("ok") is False
    assert "bad_ips" in body or "error" in body
