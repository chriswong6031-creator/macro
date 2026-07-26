"""Regression test — every /api/* response must forbid shared caching.

WHY THIS EXISTS (2026-07-25 Stripe go-live audit, found live in the sandbox):
macro-api sent NO Cache-Control header on /api/* at all. The EdgeOne edge therefore
applied its own default heuristic and cached **404** responses — with a cache key that
IGNORES the Authorization header. `GET /api/billing/portal` returns 404 for any user
without a Stripe customer (every free user), so that 404 got parked at the edge and
replayed to PAYING subscribers: they saw "no billing account yet" and could not open the
billing portal at all — the only self-serve path to update a card, cancel, or downgrade.
Reproduced twice against production with `eo-cache-status: HIT`.

The fix is app.main._api_no_store. These tests pin the three properties that matter, so
the bug cannot come back silently if the middleware is reordered or dropped:

  1. a 404 on /api/* carries no-store          <- the exact response that was cached
  2. a 401 on /api/* carries no-store          <- the other auth-shaped failure
  3. a 200 on /api/* carries no-store          <- per-user payloads (/api/me et al)
  4. a route that sets its own Cache-Control keeps it (setdefault, not clobber)
  5. non-/api paths are left alone (the static site WANTS to be edge-cached)

Offline: no network, no Stripe, no Supabase — TestClient against the mounted app.

Run:
    python -m pytest tests/test_api_no_store.py -v
"""
from __future__ import annotations

import pytest

NO_STORE = "private, no-store"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def test_404_on_api_is_not_cacheable(client):
    """THE regression: the 404 EdgeOne was caching and replaying to paying subscribers."""
    r = client.get("/api/definitely-not-a-real-route-xyz")
    assert r.status_code == 404
    assert r.headers.get("cache-control") == NO_STORE, (
        "a 404 under /api/ must be uncacheable — an edge that caches it will replay one "
        "user's 404 to everyone else (see module docstring)"
    )


def test_401_on_api_is_not_cacheable(client):
    """An authed billing route with no bearer: 401 must not be parked at the edge either."""
    r = client.get("/api/billing/portal")
    assert r.status_code == 401
    assert r.headers.get("cache-control") == NO_STORE


def test_200_on_api_is_not_cacheable(client):
    """/api/health is unauthenticated but still origin-specific (it reports the build)."""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == NO_STORE


def test_billing_config_200_is_not_cacheable(client):
    """/api/billing/config is public (publishable key) — 200 or 503, never edge-cached."""
    r = client.get("/api/billing/config")
    assert r.status_code in (200, 503)
    assert r.headers.get("cache-control") == NO_STORE


def test_middleware_does_not_clobber_an_explicit_header(client, monkeypatch):
    """setdefault semantics: a route that states its own policy keeps it.

    The SSE brain streams ship `no-cache` and the regwall/paywall gates ship a bare
    `no-store`; the middleware must not overwrite a deliberate choice.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    @app.get("/api/_test_explicit_cache_header")
    def _explicit():
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True}, headers={"Cache-Control": "no-cache"})

    r = TestClient(app).get("/api/_test_explicit_cache_header")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-cache", "middleware must not clobber"


def test_non_api_paths_are_untouched(client):
    """The static site is SUPPOSED to be edge-cached — the middleware must not reach it."""
    r = client.get("/definitely-not-an-api-path")
    assert r.headers.get("cache-control") != NO_STORE
