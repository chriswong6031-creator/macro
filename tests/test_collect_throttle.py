"""Per-IP throttle on the anonymous /api/collect analytics beacon (pre-launch
hardening). Unit-tests the hand-rolled sliding-window helper directly, plus an
end-to-end 429 through the mounted route via TestClient. No new dependency — the
throttle mirrors the existing _brain_throttle_check deque-window pattern.
"""
from __future__ import annotations

import time

import app.main as m


def test_collect_throttle_allows_up_to_max_then_429s(monkeypatch):
    # Isolate the module-global window so the test is order-independent.
    monkeypatch.setattr(m, "_collect_throttle", {})
    ip = "203.0.113.55"
    assert all(m._collect_throttle_ok(ip) for _ in range(m._COLLECT_THROTTLE_MAX))
    assert m._collect_throttle_ok(ip) is False              # one past the budget
    assert m._collect_throttle_ok("198.51.100.7") is True   # a different IP is independent


def test_collect_throttle_window_refills(monkeypatch):
    """Once the sliding window rolls past, the per-IP budget refills."""
    monkeypatch.setattr(m, "_collect_throttle", {})
    monkeypatch.setattr(m, "_COLLECT_THROTTLE_WINDOW", 0.05)   # tiny window; no real 60s wait
    ip = "203.0.113.56"
    assert all(m._collect_throttle_ok(ip) for _ in range(m._COLLECT_THROTTLE_MAX))
    assert m._collect_throttle_ok(ip) is False
    time.sleep(0.06)                                          # window elapses
    assert m._collect_throttle_ok(ip) is True                # budget refilled


def test_collect_throttle_dict_is_capped(monkeypatch):
    """The throttle map can never grow unbounded — it evicts oldest at the cap."""
    monkeypatch.setattr(m, "_collect_throttle", {})
    monkeypatch.setattr(m, "_COLLECT_THROTTLE_CAP", 10)
    for i in range(50):
        m._collect_throttle_ok(f"10.0.0.{i}")
    assert len(m._collect_throttle) <= 10


def test_collect_endpoint_returns_429_on_breach(monkeypatch):
    """End-to-end: the mounted /api/collect route returns 429 once the per-IP
    budget is exhausted, while staying 204 within budget. Size/batch caps are
    untouched. TestClient is used WITHOUT a lifespan context so no startup hooks
    (tape hub, etc.) fire."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(m, "_collect_throttle", {})
    monkeypatch.setattr(m, "_COLLECT_THROTTLE_MAX", 3)
    # Belt-and-suspenders: never attempt the Supabase insert from a test.
    monkeypatch.setattr(m, "_mm_analytics_insert", lambda *a, **k: None)

    client = TestClient(m.app)
    body = {"events": [{"type": "pageview", "path": "/"}]}
    headers = {"eo-client-ip": "203.0.113.99"}   # stable client IP the app trusts
    codes = [
        client.post("/api/collect", json=body, headers=headers).status_code
        for _ in range(4)
    ]
    assert codes[:3] == [204, 204, 204]          # within budget
    assert codes[3] == 429                        # 4th request breaches -> 429


def test_collect_oversize_body_still_413_before_throttle(monkeypatch):
    """The existing 16KB size cap is preserved and independent of the throttle."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(m, "_collect_throttle", {})
    client = TestClient(m.app)
    # content-length over 16384 -> 413 regardless of throttle state.
    big = {"events": [{"type": "pageview", "path": "x" * 20000}]}
    r = client.post("/api/collect", json=big, headers={"eo-client-ip": "203.0.113.98"})
    assert r.status_code == 413
