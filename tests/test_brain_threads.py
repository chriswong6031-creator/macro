"""Thread rename + delete: store functions (engine.neuralweb.brain_gateway) and the
owned, guest-locked routes (PATCH/DELETE /api/brain/threads/{thread_id}).

Routes are verified through the TestClient (status codes + JSON bodies), never by
scanning app.routes — this FastAPI wraps routes in _IncludedRouter so a route scan is
blind (repo memory: fastapi-includedrouter-route-verify). The Supabase _sb_* layer is
patched per the existing test idiom (patch.object(gw, "_sb_*", side_effect=...)), and
the captured PostgREST path is asserted to carry the user_id=eq ownership filter.
"""

from __future__ import annotations

import os
import sys

import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.neuralweb import brain_gateway as gw  # noqa: E402

# A canonical, valid (UUID-ish) thread id reused across tests.
TID = "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# Store layer: rename_thread
# ---------------------------------------------------------------------------

def test_rename_thread_success_carries_owner_filter():
    """A patched _sb_patch returning a row → True, and the PostgREST path filters on BOTH
    id and user_id (the user_id=eq clause IS the ownership check)."""
    seen = {}

    def fake_patch(path, payload):
        seen["path"] = path
        seen["payload"] = payload
        return [{"id": "t1", "title": payload["title"]}]

    with patch.object(gw, "_sb_patch", side_effect=fake_patch):
        ok = gw.rename_thread(TID, "userA", "My Thread")

    assert ok is True
    assert f"id=eq.{TID}" in seen["path"]
    assert "user_id=eq.userA" in seen["path"]
    assert seen["payload"] == {"title": "My Thread"}


def test_rename_thread_not_owner_returns_false():
    """0 rows patched (filter matched nothing — not yours or absent) → False."""
    with patch.object(gw, "_sb_patch", return_value=[]):
        assert gw.rename_thread(TID, "userA", "Hi") is False


def test_rename_thread_store_down_returns_false():
    """_sb_patch None (store unconfigured / errored) → False, never raises."""
    with patch.object(gw, "_sb_patch", return_value=None):
        assert gw.rename_thread(TID, "userA", "Hi") is False


def test_rename_thread_userA_cannot_touch_userB_thread():
    """Ownership is enforced by the filter: user A's rename only ever patches rows where
    user_id=eq.userA — user B's row (a different user_id) can never match."""
    captured = {}

    def fake_patch(path, payload):
        captured["path"] = path
        # PostgREST would match 0 rows because the row's user_id is userB, not userA.
        return []

    with patch.object(gw, "_sb_patch", side_effect=fake_patch):
        ok = gw.rename_thread(TID, "userA", "hijack")

    assert ok is False
    assert "user_id=eq.userA" in captured["path"]
    assert "userB" not in captured["path"]


def test_rename_thread_title_clamped_to_80():
    """Title clamped to 80 chars before hitting the store."""
    seen = {}
    with patch.object(gw, "_sb_patch", side_effect=lambda p, x: seen.setdefault("t", x["title"]) or [{"id": "t1"}]):
        gw.rename_thread(TID, "userA", "x" * 200)
    assert len(seen["t"]) == 80


def test_rename_thread_whitespace_collapsed():
    """Internal whitespace is collapsed and the title trimmed."""
    seen = {}
    with patch.object(gw, "_sb_patch", side_effect=lambda p, x: seen.setdefault("t", x["title"]) or [{"id": "t1"}]):
        gw.rename_thread(TID, "userA", "  New   \t Thread\n Name  ")
    assert seen["t"] == "New Thread Name"


def test_rename_thread_empty_title_rejected_without_store_call():
    """Empty-after-strip title → False and the store is never touched."""
    calls = []
    with patch.object(gw, "_sb_patch", side_effect=lambda p, x: calls.append(p)):
        assert gw.rename_thread(TID, "userA", "   \t \n ") is False
    assert calls == []


def test_rename_thread_no_user_id_returns_false():
    calls = []
    with patch.object(gw, "_sb_patch", side_effect=lambda p, x: calls.append(p)):
        assert gw.rename_thread(TID, "", "Hi") is False
    assert calls == []


# ---------------------------------------------------------------------------
# Store layer: delete_thread
# ---------------------------------------------------------------------------

def test_delete_thread_deletes_messages_before_thread():
    """Ownership verified, then messages deleted BEFORE the thread row (no orphans),
    and both DELETE paths carry the right filters."""
    order = []

    def fake_get(path):
        return [{"id": "t1"}]  # ownership check passes

    def fake_delete(path):
        order.append(path)
        return [{"id": "t1"}] if "brain_threads" in path else []

    with patch.object(gw, "_sb_get", side_effect=fake_get), \
         patch.object(gw, "_sb_delete", side_effect=fake_delete):
        ok = gw.delete_thread(TID, "userA")

    assert ok is True
    assert len(order) == 2
    assert order[0].startswith("brain_messages?thread_id=eq.")  # messages first
    assert order[1].startswith("brain_threads?id=eq.")          # thread second
    assert "user_id=eq.userA" in order[1]                       # owner filter on thread delete


def test_delete_thread_ownership_checked_before_any_delete():
    """Ownership GET carries id + user_id; a not-owned/absent thread (GET []) → False and
    NO delete is issued."""
    get_paths = []
    del_paths = []

    def fake_get(path):
        get_paths.append(path)
        return []  # not owner / absent

    with patch.object(gw, "_sb_get", side_effect=fake_get), \
         patch.object(gw, "_sb_delete", side_effect=lambda p: del_paths.append(p)):
        ok = gw.delete_thread(TID, "userA")

    assert ok is False
    assert del_paths == []                       # nothing deleted
    assert any("user_id=eq.userA" in p for p in get_paths)  # ownership filter present


def test_delete_thread_userA_cannot_delete_userB_thread():
    """User A deleting user B's thread: the ownership GET (filtered by user_id=eq.userA)
    returns nothing, so no delete fires."""
    del_paths = []
    with patch.object(gw, "_sb_get", return_value=[]), \
         patch.object(gw, "_sb_delete", side_effect=lambda p: del_paths.append(p)):
        assert gw.delete_thread(TID, "userA") is False
    assert del_paths == []


def test_delete_thread_returns_false_if_thread_row_not_deleted():
    """Ownership passes but the thread DELETE returns [] (raced away) → False, even though
    messages were removed."""
    def fake_delete(path):
        return []  # neither delete reports a row

    with patch.object(gw, "_sb_get", return_value=[{"id": "t1"}]), \
         patch.object(gw, "_sb_delete", side_effect=fake_delete):
        assert gw.delete_thread(TID, "userA") is False


def test_delete_thread_store_down_returns_false():
    """Ownership GET None (store down) → False, no delete attempted."""
    del_paths = []
    with patch.object(gw, "_sb_get", return_value=None), \
         patch.object(gw, "_sb_delete", side_effect=lambda p: del_paths.append(p)):
        assert gw.delete_thread(TID, "userA") is False
    assert del_paths == []


# ---------------------------------------------------------------------------
# thread_id validation (both store functions reject URL-metacharacter garbage)
# ---------------------------------------------------------------------------

_GARBAGE_IDS = [
    "t1,user_id.neq.x",          # PostgREST filter injection via comma
    "1;drop",                     # semicolon
    "id=eq.1&user_id=eq.2",       # embedded filter clauses
    "../../etc",                  # path traversal
    "a b",                        # whitespace
    "",                           # empty
    "x" * 100,                    # over-long
    "abc%20def",                  # percent-encoded space
]


@pytest.mark.parametrize("bad", _GARBAGE_IDS)
def test_rename_thread_rejects_garbage_id(bad):
    calls = []
    with patch.object(gw, "_sb_patch", side_effect=lambda p, x: calls.append(p)):
        assert gw.rename_thread(bad, "userA", "Hi") is False
    assert calls == [], f"store was touched for garbage id {bad!r}"


@pytest.mark.parametrize("bad", _GARBAGE_IDS)
def test_delete_thread_rejects_garbage_id(bad):
    calls = []
    with patch.object(gw, "_sb_get", side_effect=lambda p: calls.append(("get", p))), \
         patch.object(gw, "_sb_delete", side_effect=lambda p: calls.append(("del", p))):
        assert gw.delete_thread(bad, "userA") is False
    assert calls == [], f"store was touched for garbage id {bad!r}"


def test_valid_thread_id_accepts_uuid_rejects_garbage():
    assert gw._valid_thread_id(TID) is True
    assert gw._valid_thread_id("deadbeefdeadbeef") is True  # bare hex, no dashes
    for bad in _GARBAGE_IDS:
        assert gw._valid_thread_id(bad) is False
    assert gw._valid_thread_id(None) is False


# ---------------------------------------------------------------------------
# List ordering (widget assumes updated_at desc — regression guard on the query)
# ---------------------------------------------------------------------------

def test_list_threads_orders_by_updated_at_desc():
    """The threads-list store query must carry order=updated_at.desc (the widget shows
    most-recent-first)."""
    seen = {}
    with patch.object(gw, "_sb_get", side_effect=lambda p: seen.setdefault("p", p) or []):
        gw.list_threads("userA")
    assert "order=updated_at.desc" in seen["p"]


# ---------------------------------------------------------------------------
# Route layer: PATCH/DELETE /api/brain/threads/{thread_id}
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app), app


def _auth_as(app, user_id="userA", email="a@x.com"):
    """Override require_user → a verified user (mirrors the sibling brain route auth)."""
    from app.main import require_user
    app.dependency_overrides[require_user] = lambda: {"id": user_id, "email": email}


def _clear_auth(app):
    app.dependency_overrides.clear()


def test_route_patch_requires_auth_401(client):
    """No bearer → 401 on PATCH (require_user, not the guest-tolerant dep)."""
    c, app = client
    r = c.patch(f"/api/brain/threads/{TID}", json={"title": "Hi"})
    assert r.status_code == 401


def test_route_delete_requires_auth_401(client):
    """No bearer → 401 on DELETE."""
    c, app = client
    r = c.delete(f"/api/brain/threads/{TID}")
    assert r.status_code == 401


def test_route_patch_guest_enabled_still_401(client):
    """Even with guest access ENABLED, these routes use require_user → guests (who own no
    threads) get 401, never a guest identity."""
    c, app = client
    with patch("app.main._guest_access_enabled", return_value=True):
        r = c.patch(f"/api/brain/threads/{TID}", json={"title": "Hi"})
        rd = c.delete(f"/api/brain/threads/{TID}")
    assert r.status_code == 401
    assert rd.status_code == 401


def test_route_patch_success_200(client):
    c, app = client
    _auth_as(app)
    try:
        with patch.object(gw, "_sb_patch", return_value=[{"id": "t1"}]):
            r = c.patch(f"/api/brain/threads/{TID}", json={"title": "Renamed"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
    finally:
        _clear_auth(app)


def test_route_patch_not_owned_404_ok_false(client):
    """rename_thread False (not owned/absent) → 404 with {ok: false} body."""
    c, app = client
    _auth_as(app)
    try:
        with patch.object(gw, "_sb_patch", return_value=[]):
            r = c.patch(f"/api/brain/threads/{TID}", json={"title": "X"})
        assert r.status_code == 404
        assert r.json() == {"ok": False}
    finally:
        _clear_auth(app)


def test_route_patch_empty_title_422(client):
    """Whitespace-only title → 422 (validation) before the store is consulted."""
    c, app = client
    _auth_as(app)
    calls = []
    try:
        with patch.object(gw, "_sb_patch", side_effect=lambda p, x: calls.append(p)):
            r = c.patch(f"/api/brain/threads/{TID}", json={"title": "   "})
        assert r.status_code == 422
        assert calls == []  # never reached the store
    finally:
        _clear_auth(app)


def test_route_patch_missing_title_422(client):
    """Missing title field → 422."""
    c, app = client
    _auth_as(app)
    try:
        r = c.patch(f"/api/brain/threads/{TID}", json={})
        assert r.status_code == 422
    finally:
        _clear_auth(app)


def test_route_patch_title_normalized_before_store(client):
    """The route hands the store a trimmed, whitespace-collapsed, clamped title."""
    c, app = client
    _auth_as(app)
    seen = {}
    try:
        with patch.object(gw, "_sb_patch", side_effect=lambda p, x: seen.setdefault("t", x["title"]) or [{"id": "t1"}]):
            r = c.patch(f"/api/brain/threads/{TID}", json={"title": "  Hello   World  "})
        assert r.status_code == 200
        assert seen["t"] == "Hello World"
    finally:
        _clear_auth(app)


def test_route_delete_success_200(client):
    c, app = client
    _auth_as(app)
    try:
        with patch.object(gw, "_sb_get", return_value=[{"id": "t1"}]), \
             patch.object(gw, "_sb_delete", side_effect=lambda p: [{"id": "t1"}] if "brain_threads" in p else []):
            r = c.delete(f"/api/brain/threads/{TID}")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
    finally:
        _clear_auth(app)


def test_route_delete_not_owned_404_ok_false(client):
    """delete_thread False (ownership GET empty) → 404 {ok: false}, no delete issued."""
    c, app = client
    _auth_as(app)
    del_calls = []
    try:
        with patch.object(gw, "_sb_get", return_value=[]), \
             patch.object(gw, "_sb_delete", side_effect=lambda p: del_calls.append(p)):
            r = c.delete(f"/api/brain/threads/{TID}")
        assert r.status_code == 404
        assert r.json() == {"ok": False}
        assert del_calls == []
    finally:
        _clear_auth(app)


def test_route_patch_garbage_id_404(client):
    """A URL-metacharacter garbage id fails store validation → rename False → 404 (never a
    store call)."""
    c, app = client
    _auth_as(app)
    calls = []
    try:
        with patch.object(gw, "_sb_patch", side_effect=lambda p, x: calls.append(p)):
            r = c.patch("/api/brain/threads/not-a-uuid,user_id.neq.x", json={"title": "Hi"})
        assert r.status_code == 404
        assert calls == []
    finally:
        _clear_auth(app)
