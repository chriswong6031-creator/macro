"""tests/test_ontology_explorer_transport.py — F04-X1 private transport (RED first).

`/ontology.html` is public and carries no current value. Every current value
reaches the researcher through `GET /api/ontology/explorer/v1` behind the
existing `require_user -> enforce_site_full(always=True)` authority.

The hard part is not the happy path — it is the outcomes where a header is
easiest to forget. A 401 raised inside a dependency never reaches the endpoint
body, so a router that only stamps its headers on success will serve its
rejections cacheable and indexable. These tests therefore assert the private
header set on EVERY outcome: success, 401, 403, typed 503 and 422.

They also pin the two refusals that make the paywall meaningful at all: there is
no static fallback to serve when the source is unavailable, and no error body
ever carries a current owner reading.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="ontology explorer transport tests need fastapi")
pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ontology_explorer_fixtures as fx  # noqa: E402

ROUTE = "/api/ontology/explorer/v1"

REQUIRED_PRIVATE_HEADERS = {
    "cache-control": "private, no-store",
    "vary": "Authorization",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, noarchive",
}


def _api():
    from app import ontology_explorer as api
    return api


def _client(monkeypatch, tmp_path, *, entitled: bool = True, authed: bool = True,
            root: Path | None = None, chain: str = fx.SLUG) -> TestClient:
    api = _api()
    root = fx.build_root(tmp_path) if root is None else root
    monkeypatch.setattr(api, "_repo_root", lambda: root)
    monkeypatch.setattr(api, "DEFAULT_CHAIN", chain)
    app = FastAPI()
    app.include_router(api.router)

    def _dep():
        if not authed:
            raise HTTPException(401, "missing bearer token")
        if not entitled:
            raise HTTPException(403, detail={"locked": True, "tier": "essential",
                                             "required_feature": "site_full",
                                             "upgrade_url": "/plans.html?upgrade=1"})
        return {"id": "paid-user"}

    app.dependency_overrides[api.require_site_full_user] = _dep
    return TestClient(app, raise_server_exceptions=False)


def _assert_private(response) -> None:
    for name, value in REQUIRED_PRIVATE_HEADERS.items():
        assert response.headers.get(name) == value, (
            f"{name} missing or wrong on a {response.status_code} response")


# --------------------------------------------------------------------------
# the authenticated happy path
# --------------------------------------------------------------------------
def test_entitled_read_returns_the_snapshot_privately(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.get(ROUTE)
    assert response.status_code == 200
    assert response.json()["schema"] == "ontology_explorer_snapshot.v1"
    _assert_private(response)


def test_the_route_is_registered_under_the_frozen_namespace(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        assert ROUTE in client.app.openapi()["paths"]


# --------------------------------------------------------------------------
# rejection outcomes still carry the private header set
# --------------------------------------------------------------------------
def test_anonymous_read_is_401_and_still_private(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path, authed=False) as client:
        response = client.get(ROUTE)
    assert response.status_code == 401
    _assert_private(response)


def test_authenticated_without_site_full_is_403_and_still_private(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path, entitled=False) as client:
        response = client.get(ROUTE)
    assert response.status_code == 403
    _assert_private(response)
    assert response.json()["detail"]["required_feature"] == "site_full"


def test_a_missing_source_is_a_typed_503_and_still_private(monkeypatch, tmp_path):
    root = fx.build_root(tmp_path)
    (root / "data" / "transmission" / "chain_state.json").unlink()
    with _client(monkeypatch, tmp_path, root=root) as client:
        response = client.get(ROUTE)
    assert response.status_code == 503
    _assert_private(response)
    detail = response.json()["detail"]
    assert detail["code"] == "source_unavailable"
    assert detail["schema"] == "ontology_explorer_error.v1"


def test_an_incoherent_source_is_a_typed_503_and_still_private(monkeypatch, tmp_path):
    root = fx.build_root(tmp_path, yaml_doc=fx.chain_yaml(rev=3),
                         state_doc=fx.chain_state(rev=2))
    with _client(monkeypatch, tmp_path, root=root) as client:
        response = client.get(ROUTE)
    assert response.status_code == 503
    _assert_private(response)
    assert response.json()["detail"]["code"] == "source_incoherent"


def test_an_unknown_chain_parameter_is_rejected_privately(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.get(ROUTE, params={"chain": "../../etc/passwd"})
    assert response.status_code in {400, 422}
    _assert_private(response)


# --------------------------------------------------------------------------
# no fallback, no leak
# --------------------------------------------------------------------------
def test_source_failure_never_falls_back_to_a_stale_snapshot(monkeypatch, tmp_path):
    """A cached last-good answer served on failure is exactly the "old static
    fallback" the operation forbids: the researcher would read a stale state as
    the current one."""
    root = fx.build_root(tmp_path)
    with _client(monkeypatch, tmp_path, root=root) as client:
        assert client.get(ROUTE).status_code == 200
        (root / "data" / "transmission" / "chain_state.json").unlink()
        failed = client.get(ROUTE)
    assert failed.status_code == 503
    assert "path" not in failed.json().get("detail", {})


def test_error_bodies_carry_no_owner_reading(monkeypatch, tmp_path):
    root = fx.build_root(tmp_path, yaml_doc=fx.chain_yaml(rev=3),
                         state_doc=fx.chain_state(rev=2))
    with _client(monkeypatch, tmp_path, root=root) as client:
        body = client.get(ROUTE).text
    for leaked in ("receipts", "value_receipt", "confirmed", "threshold"):
        assert leaked not in body


def test_the_router_serves_no_write_verbs(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        paths = client.app.openapi()["paths"]
    for methods in paths.values():
        assert set(methods) <= {"get"}, "the explorer is read-only"


def test_a_get_does_not_mutate_the_owner_artifacts(monkeypatch, tmp_path):
    root = fx.build_root(tmp_path)
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size)
              for p in sorted(root.rglob("*")) if p.is_file()}
    with _client(monkeypatch, tmp_path, root=root) as client:
        assert client.get(ROUTE).status_code == 200
    after = {p: (p.stat().st_mtime_ns, p.stat().st_size)
             for p in sorted(root.rglob("*")) if p.is_file()}
    assert before == after


def test_the_router_reuses_the_shared_entitlement_authority(monkeypatch, tmp_path):
    """A second identity path is how a paywall quietly stops being one. The
    dependency must resolve through app.main.require_user and
    app.paywall.enforce_site_full(always=True), not a local re-implementation."""
    import inspect
    source = inspect.getsource(_api().require_site_full_user)
    assert "require_user" in source
    assert "enforce_site_full" in source
    assert "always=True" in source


# --------------------------------------------------------------------------
# outcomes that never reach the endpoint at all
#
# The route class stamps headers by wrapping the endpoint. Three outcomes do not
# go through it: an exception it does not catch escapes to Starlette's outermost
# error middleware, and a method mismatch is raised by Starlette's router BEFORE
# the wrapper is entered. An independent review measured all three arriving with
# none of the private header set.
# --------------------------------------------------------------------------
def _boom_client(monkeypatch, tmp_path) -> TestClient:
    api = _api()
    root = fx.build_root(tmp_path)
    monkeypatch.setattr(api, "_repo_root", lambda: root)
    monkeypatch.setattr(api, "DEFAULT_CHAIN", fx.SLUG)

    def explode(*a, **k):
        raise ValueError("boom /Users/someone/private/path.json")

    monkeypatch.setattr(api, "compose_snapshot", explode)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_site_full_user] = lambda: {"id": "paid-user"}
    return TestClient(app, raise_server_exceptions=False)


def test_an_unexpected_exception_is_still_a_private_response(monkeypatch, tmp_path):
    with _boom_client(monkeypatch, tmp_path) as client:
        response = client.get(ROUTE)
    assert response.status_code >= 500
    _assert_private(response)


def test_an_unexpected_exception_does_not_leak_its_message(monkeypatch, tmp_path):
    """A stray exception string is where internal paths escape."""
    with _boom_client(monkeypatch, tmp_path) as client:
        body = client.get(ROUTE).text
    assert "boom" not in body
    assert "/Users/" not in body


def test_a_disallowed_method_is_still_a_private_response(monkeypatch, tmp_path):
    for method in ("post", "put", "patch", "delete"):
        with _client(monkeypatch, tmp_path) as client:
            response = getattr(client, method)(ROUTE)
        assert response.status_code == 405, method
        _assert_private(response)


def test_head_is_answered_and_is_private(monkeypatch, tmp_path):
    """A cache or crawler that probes with HEAD must not get an un-noindexed,
    un-nosniffed response."""
    with _client(monkeypatch, tmp_path) as client:
        response = client.head(ROUTE)
    assert response.status_code == 200
    _assert_private(response)
    assert response.content == b""


# --------------------------------------------------------------------------
# the chain parameter
# --------------------------------------------------------------------------
def test_a_trailing_newline_cannot_smuggle_a_slug_past_the_guard(monkeypatch, tmp_path):
    """Python's `$` matches before a trailing newline, so `^...$` accepted a slug
    with a line break appended — which then reached the composer and split one
    log call across two lines."""
    with _client(monkeypatch, tmp_path) as client:
        response = client.get(ROUTE, params={"chain": f"{fx.SLUG}\n"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unknown_chain"
    _assert_private(response)


def test_an_explicitly_empty_chain_is_rejected_not_silently_defaulted(monkeypatch, tmp_path):
    """Every other malformed value is refused; an empty one asked for something
    specific and got the default instead."""
    with _client(monkeypatch, tmp_path) as client:
        response = client.get(ROUTE, params={"chain": ""})
    assert response.status_code == 400
    _assert_private(response)


def test_the_composer_also_refuses_a_trailing_newline_slug():
    from engine.ontology_explorer import SourceUnavailable, compose_snapshot
    with pytest.raises(SourceUnavailable):
        compose_snapshot(Path("/nonexistent"), chain="oil_inflation_duration_derate\n")


# --------------------------------------------------------------------------
# the builder
# --------------------------------------------------------------------------
def test_the_builder_fails_loudly_when_a_paired_asset_is_missing(tmp_path, monkeypatch):
    """`return 0` from main() is SystemExit(0): a missing asset made the build a
    silent success that also skipped every later asset."""
    import scripts.build_ontology_explorer as builder
    monkeypatch.setattr(builder, "PAIRED_ASSETS", ("ontology.css", "definitely_absent.js"))
    assert builder.main() == 1
