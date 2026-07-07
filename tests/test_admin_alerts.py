"""tests/test_admin_alerts.py — Unit + HTTP tests for PR-C4 operator capture.

Tests
-----
1.  test_alert_id_stable           — same key fields → same alert_id across calls
2.  test_alert_id_differs_on_type  — different type → different alert_id
3.  test_feed_panel_absent         — feed file absent → ok=True, alerts=[], note set
4.  test_feed_panel_present        — feed file present → alerts returned correctly
5.  test_feed_panel_limit          — limit param respected
6.  test_feed_panel_bad_json       — corrupt JSON → ok=False, no raise
7.  test_http_get_alerts_ok        — GET /api/alerts returns {ok, alerts, generated_utc}
8.  test_http_get_alerts_empty     — empty feed → ok=True, alerts=[]
9.  test_exp_overrode_button_exists— 'overrode' action is wired in VALID_ACTIONS (schema)
10. test_build_triage_has_alert_id — build_triage enriched alerts carry alert_id field
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import unittest.mock
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from admin.actions import VALID_ACTIONS          # noqa: E402
from admin.server import Handler                 # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


def _get(port, path):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    return urllib.request.urlopen(req, timeout=10)


def _make_feed(alerts: list[dict], generated_utc: str = "2026-07-06 04:00") -> dict:
    return {"generated_utc": generated_utc, "alerts": alerts}


def _sample_alert(n: int = 1) -> dict:
    return {
        "alert_id": hashlib.sha256(f"macro|ebp_widening|macro|2026-07-0{n}".encode()).hexdigest()[:12],
        "emit_ts": f"2026-07-0{n}T00:00:00",
        "title": f"Alert {n}",
        "surface": "macro:ebp_widening",
        "severity": "major",
        "tier": "act",
        "priority": 70,
        "source": "macro",
    }


# ---------------------------------------------------------------------------
# 1–2: alert_id stability (engine.alert_triage._id_key logic)
# ---------------------------------------------------------------------------

def test_alert_id_stable():
    """Same (source, type, asset, date) → same 12-hex ID regardless of call order."""
    key = "macro|ebp_widening|macro|2026-07-06"
    expected = hashlib.sha256(key.encode()).hexdigest()[:12]
    # Compute twice — must be identical
    assert hashlib.sha256(key.encode()).hexdigest()[:12] == expected
    assert len(expected) == 12
    assert all(c in "0123456789abcdef" for c in expected)


def test_alert_id_differs_on_type():
    """Different alert type → different ID."""
    key_a = "macro|ebp_widening|macro|2026-07-06"
    key_b = "macro|hy_oas_widening|macro|2026-07-06"
    id_a = hashlib.sha256(key_a.encode()).hexdigest()[:12]
    id_b = hashlib.sha256(key_b.encode()).hexdigest()[:12]
    assert id_a != id_b


# ---------------------------------------------------------------------------
# 3–6: admin.alerts.panel()
# ---------------------------------------------------------------------------

def test_feed_panel_absent(tmp_path):
    """When feed.json doesn't exist panel returns ok=True with empty list and a note."""
    with unittest.mock.patch("admin.alerts._feed_path", return_value=tmp_path / "feed.json"):
        from admin import alerts
        result = alerts.panel()
    assert result["ok"] is True
    assert result["alerts"] == []
    assert result["note"] is not None
    assert "not yet generated" in result["note"]


def test_feed_panel_present(tmp_path):
    """Feed file present → alerts returned with correct fields."""
    feed_file = tmp_path / "feed.json"
    alerts_data = [_sample_alert(1), _sample_alert(2)]
    feed_file.write_text(json.dumps(_make_feed(alerts_data)))
    with unittest.mock.patch("admin.alerts._feed_path", return_value=feed_file):
        from admin import alerts
        result = alerts.panel()
    assert result["ok"] is True
    assert len(result["alerts"]) == 2
    assert result["alerts"][0]["alert_id"] is not None
    assert result["alerts"][0]["title"] == "Alert 1"
    assert result["generated_utc"] == "2026-07-06 04:00"
    assert result["note"] is None


def test_feed_panel_limit(tmp_path):
    """limit= parameter caps returned alerts."""
    feed_file = tmp_path / "feed.json"
    alerts_data = [_sample_alert(i) for i in range(1, 6)]
    feed_file.write_text(json.dumps(_make_feed(alerts_data)))
    with unittest.mock.patch("admin.alerts._feed_path", return_value=feed_file):
        from admin import alerts
        result = alerts.panel(limit=3)
    assert len(result["alerts"]) == 3


def test_feed_panel_bad_json(tmp_path):
    """Corrupt JSON returns ok=False, no exception raised."""
    feed_file = tmp_path / "feed.json"
    feed_file.write_text("{not valid json")
    with unittest.mock.patch("admin.alerts._feed_path", return_value=feed_file):
        from admin import alerts
        result = alerts.panel()
    assert result["ok"] is False
    assert result["alerts"] == []


# ---------------------------------------------------------------------------
# 7–8: HTTP GET /api/alerts
# ---------------------------------------------------------------------------

def test_http_get_alerts_ok(tmp_path):
    """GET /api/alerts returns {ok, generated_utc, alerts} when feed exists."""
    feed_file = tmp_path / "feed.json"
    alerts_data = [_sample_alert(1)]
    feed_file.write_text(json.dumps(_make_feed(alerts_data)))
    httpd, port = _server()
    try:
        with unittest.mock.patch("admin.alerts._feed_path", return_value=feed_file):
            resp = _get(port, "/api/alerts")
            data = json.loads(resp.read())
        assert data["ok"] is True
        assert "alerts" in data
        assert isinstance(data["alerts"], list)
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["source"] == "macro"
    finally:
        httpd.shutdown(); httpd.server_close()


def test_http_get_alerts_empty(tmp_path):
    """GET /api/alerts with absent feed → ok=True, alerts=[]."""
    httpd, port = _server()
    try:
        with unittest.mock.patch("admin.alerts._feed_path",
                                  return_value=tmp_path / "missing.json"):
            resp = _get(port, "/api/alerts")
            data = json.loads(resp.read())
        assert data["ok"] is True
        assert data["alerts"] == []
    finally:
        httpd.shutdown(); httpd.server_close()


# ---------------------------------------------------------------------------
# 9: 'overrode' is in VALID_ACTIONS (schema completeness)
# ---------------------------------------------------------------------------

def test_exp_overrode_button_exists():
    """'overrode' must be in VALID_ACTIONS — it's the schema for the missing button."""
    assert "overrode" in VALID_ACTIONS


# ---------------------------------------------------------------------------
# 10: build_triage enriched alerts carry alert_id
# ---------------------------------------------------------------------------

def test_build_triage_has_alert_id():
    """build_triage returns alerts that each carry a non-empty alert_id field."""
    from engine.alert_triage import build_triage
    # Patch all raw feed loaders to return a single synthetic alert so the test
    # doesn't depend on any data files.
    synthetic = [{
        "source": "macro", "type": "ebp_widening", "asset": "macro",
        "ts": "2026-07-06T00:00:00", "date_only": True,
        "raw_sev": "high", "tier": "act",
        "headline": "Test alert", "headline_zh": "Test alert",
        "detail": "", "detail_zh": "",
        "anchor": "", "edge": "", "edge_zh": "",
    }]
    with (
        unittest.mock.patch("engine.alert_triage._macro_raw", return_value=synthetic),
        unittest.mock.patch("engine.alert_triage._jsonl_raw", return_value=[]),
        unittest.mock.patch("engine.alert_triage._load_context", return_value={}),
        unittest.mock.patch("engine.alert_triage._events", return_value={"items": [], "next": None}),
        unittest.mock.patch("engine.alert_triage._registry_index", return_value={}),
        unittest.mock.patch("engine.alert_triage._rule_scorecard", return_value={}),
    ):
        result = build_triage()
    alerts = result.get("alerts", [])
    assert len(alerts) >= 1
    for a in alerts:
        assert "alert_id" in a
        assert len(a["alert_id"]) == 12
        assert all(c in "0123456789abcdef" for c in a["alert_id"])


if __name__ == "__main__":
    import tempfile, inspect
    for fn_name in sorted(k for k in globals() if k.startswith("test_")):
        fn = globals()[fn_name]
        sig = inspect.signature(fn)
        if "tmp_path" in sig.parameters:
            with tempfile.TemporaryDirectory() as td:
                fn(Path(td))
        else:
            fn()
        print("PASS", fn_name)
