"""Every /api/government-revenue/* route is a paid (site_full) surface.

This file exists because the desk shipped 24 routes with zero ``Depends`` from
its first commit (``316385cdfb1``, 2026-08-01) until the 2026-08-11 serving
boundary census caught it live: ``/api/government-revenue/candidates?limit=2``
answered **200** anonymously while the sibling desk's
``/api/capital-structure/v1/coverage`` answered **401**.

Nothing caught it because nothing could:

* every other ``tests/test_government_revenue_*.py`` calls the endpoint
  functions directly as plain Python (``api.latest(...)``), which bypasses
  FastAPI's dependency stack entirely, so an ungated router is invisible to
  them -- and, symmetrically, adding the gate broke none of them; and
* ``tests/test_site_access_boundary.py`` deliberately scopes itself to static
  Caddy serving and excludes ``/api/*`` on the stated assumption that
  "app/main.py ... enforces its own auth" -- an assumption that was never
  checked for this router.

So the gate has to be proven over real HTTP, and proven for *every* route
rather than a hand-picked sample: the defect being fenced is a route that ships
without the dependency someone forgot to repeat.
"""
from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import government_revenue as api


# Placeholders chosen to satisfy each validator in app/government_revenue.py, so
# a route that reaches its body would fail on data rather than on a 422. The
# point is that it must never reach its body while anonymous.
_PATH_PARAMS = {
    "ticker": "RTX",                                   # _TICKER
    "candidate_id": "grc1-" + "a" * 24,                # _CANDIDATE_ID
    "award_key": "generated:CONT_AWD_1",               # _AWARD_KEY
    "subaward_key": "generated:SUB_AWD_1",             # _SUBAWARD_KEY
    "line_key": "dod:p1:department-of-army:2031a",     # _BUDGET_LINE_KEY
    "program_key": "dod-program:department-of-army",   # _BUDGET_PROGRAM_KEY
    "notice_id": "notice-1",                           # _NOTICE_ID
    "event_id": "event-1",
    "case_key": "fms:transmittal:26-13",               # _FMS_CASE_KEY
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def _routes() -> list[str]:
    return sorted(
        route.path for route in api.router.routes if getattr(route, "path", "").startswith("/api/")
    )


def _concrete(path: str) -> str:
    """Substitute every {param} with a validator-satisfying placeholder."""
    for name in re.findall(r"\{([^}]+)\}", path):
        # A new path param must be added to _PATH_PARAMS deliberately; failing
        # loudly here beats silently probing a malformed URL and "passing".
        assert name in _PATH_PARAMS, f"unmapped path param {{{name}}} in {path}"
        path = path.replace("{" + name + "}", _PATH_PARAMS[name])
    return path


def test_the_router_actually_has_routes() -> None:
    """Guard the guard: an empty enumeration would make every test below vacuous."""
    assert len(_routes()) >= 24


@pytest.mark.parametrize("path", _routes())
def test_every_route_refuses_an_anonymous_reader(path: str) -> None:
    """No route may answer 200 without a bearer token -- the census defect.

    ``q`` is supplied unconditionally: /search requires it, and FastAPI ignores
    unknown query params elsewhere, so one URL shape covers every route. Without
    it /search would 422 on the missing param and never exercise the gate.
    """
    response = _client().get(_concrete(path), params={"q": "RTX"})
    assert response.status_code == 401, (
        f"{path} answered {response.status_code} anonymously; "
        "every government-revenue route is site_full-gated"
    )


@pytest.mark.parametrize("path", _routes())
def test_every_route_refuses_a_malformed_bearer_token(path: str) -> None:
    """A cookie-only or garbage Authorization header must not pass either."""
    response = _client().get(
        _concrete(path), params={"q": "RTX"}, headers={"Authorization": "NotBearer x"}
    )
    assert response.status_code == 401, f"{path} answered {response.status_code} to a bad token"


def test_the_gate_runs_before_the_artifact_is_read(monkeypatch) -> None:
    """Anonymous 401 must not depend on the artifact being present or valid.

    Fails closed in both directions: a reader with no token is refused before
    any projection load, so a missing/corrupt artifact can never turn the gate
    into a 503-shaped information leak about serving state.
    """
    def _boom() -> dict:
        raise AssertionError("artifact was read before authentication")

    monkeypatch.setattr(api, "_load", _boom)
    monkeypatch.setattr(api, "_load_candidate_projection", _boom)
    monkeypatch.setattr(api, "_load_dossiers", _boom)

    for path in _routes():
        response = _client().get(_concrete(path), params={"q": "RTX"})
        assert response.status_code == 401, f"{path} answered {response.status_code}"


def test_router_declares_the_dependency_once_for_every_route() -> None:
    """Router-level, not per-route: a newly added @router.get inherits the gate.

    Pins the mechanism as well as the behaviour -- the 24 routes above were
    written over ten months by several sessions, and per-route ``Depends`` is
    exactly the shape that lets number 25 ship open.
    """
    dependencies = [dependency.dependency for dependency in api.router.dependencies]
    assert api.require_site_full_user in dependencies
