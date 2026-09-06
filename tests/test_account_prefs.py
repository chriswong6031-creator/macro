"""tests/test_account_prefs.py — app/account_prefs.py (SEE W3 / masterplan R4).

Fully offline: no Supabase, no network. Two seams are stubbed —
``urllib.request.urlopen`` (the auth admin API that stores ``user_metadata``) and
``billing._pg`` (the PostgREST upsert that mirrors ``lang`` into ``email_prefs``).

Coverage:
  - identity comes from the BEARER TOKEN only; a client-sent user_id is ignored.
  - lang/theme validation, including "nothing to save".
  - the metadata write MERGES rather than replacing (an unrelated stored key survives).
  - lang mirrors into email_prefs; theme alone does not touch it.
  - fail-soft: a partial failure still 200s with an honest per-sink flag; a total failure
    is an honest 502 rather than a lie.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import account_prefs, billing  # noqa: E402

USER = {"id": "9c1f-user", "email": "reader@example.com",
        "user_metadata": {"display_name": "Ada", "lang": "en"}}


class _Resp:
    def __init__(self, body=b"{}"):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class _Auth:
    """Records every admin-API call the module makes."""

    def __init__(self, fail=False):
        self.calls: list[tuple[str, str, dict]] = []
        self.fail = fail

    def urlopen(self, req, timeout=None):
        payload = json.loads(req.data.decode()) if req.data else {}
        self.calls.append((req.get_method(), req.full_url, payload))
        if self.fail:
            raise OSError("supabase unreachable")
        return _Resp()


class _Store:
    def __init__(self, fail=False):
        self.rows: list[dict] = []
        self.fail = fail

    def pg(self, method, path, body=None, prefer=None, timeout=6):
        if self.fail:
            raise RuntimeError("postgrest down")
        self.rows.append({"method": method, "path": path, "body": body, "prefer": prefer})
        return None


@pytest.fixture
def auth(monkeypatch) -> _Auth:
    a = _Auth()
    monkeypatch.setattr(urllib.request, "urlopen", a.urlopen)
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_ROLE_KEY", "service-role-test-key")
    monkeypatch.setattr(billing, "SUPABASE_URL", "https://proj.supabase.test")
    return a


@pytest.fixture
def store(monkeypatch) -> _Store:
    s = _Store()
    monkeypatch.setattr(billing, "_pg", s.pg)
    return s


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
def test_identity_comes_from_require_user(monkeypatch):
    """Same secretless verification every authed route uses — no local notion of 'who'."""
    seen = {}
    import app.main as main

    def _verify(authz):
        seen["authz"] = authz
        return USER

    monkeypatch.setattr(main, "require_user", _verify)
    assert account_prefs._current_user("Bearer tok-123") == USER
    assert seen["authz"] == "Bearer tok-123"


def test_unauthed_call_is_401(monkeypatch):
    import app.main as main

    def _reject(authz):
        raise HTTPException(401, "missing bearer token")

    monkeypatch.setattr(main, "require_user", _reject)
    with pytest.raises(HTTPException) as ei:
        account_prefs._current_user(None)
    assert ei.value.status_code == 401


def test_user_without_an_id_is_401(auth, store):
    with pytest.raises(HTTPException) as ei:
        account_prefs.save_prefs(account_prefs.PrefsRequest(lang="zh"), user={"email": "x@y.z"})
    assert ei.value.status_code == 401


def test_client_sent_user_id_is_ignored(auth, store):
    """Never trust the client: the write targets the TOKEN's user, whatever the body says."""
    body = account_prefs.PrefsRequest.model_validate(
        {"lang": "zh", "user_id": "attacker-uuid", "id": "attacker-uuid"})
    assert not hasattr(body, "user_id")
    account_prefs.save_prefs(body, user=USER)
    _, url, _ = auth.calls[0]
    assert url.endswith("/auth/v1/admin/users/9c1f-user")
    assert "attacker-uuid" not in url
    assert store.rows[0]["body"][0]["user_id"] == "9c1f-user"


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("payload, bad", [
    ({"lang": "fr"}, "lang"),
    ({"lang": "en-US"}, "lang"),
    ({"theme": "sepia"}, "theme"),
    ({"theme": ""}, "theme"),
    ({"brain_depth": "turbo"}, "brain_depth"),
    ({"brain_depth": "short"}, "brain_depth"),
    ({"brain_depth": ""}, "brain_depth"),
])
def test_unknown_values_are_400(auth, store, payload, bad):
    with pytest.raises(HTTPException) as ei:
        account_prefs.save_prefs(account_prefs.PrefsRequest(**payload), user=USER)
    assert ei.value.status_code == 400
    assert ei.value.detail["field"] == bad
    assert ei.value.detail["en"] and ei.value.detail["zh"]
    assert auth.calls == [] and store.rows == []


def test_empty_body_is_400(auth, store):
    with pytest.raises(HTTPException) as ei:
        account_prefs.save_prefs(account_prefs.PrefsRequest(), user=USER)
    assert ei.value.status_code == 400
    assert auth.calls == [] and store.rows == []


# --------------------------------------------------------------------------- #
# B-F08-1a: alert delivery preferences (email opt-in, category, tz, quiet hours)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value, expected", [
    (True, True), (False, False), ("true", True), ("off", False), ("1", True), ("0", False),
])
def test_alert_email_optin_accepts_bool_and_strings(auth, store, value, expected):
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(alert_email_optin=value), user=USER)
    # Turning alerts ON with no tz already known (USER carries none) also applies the
    # server-side default_tz_for_lang default (Meta-CEO B ruling, macro#6907 round 2;
    # see tests/test_alert_prefs.py::
    # test_alerts_on_with_no_tz_defaults_and_round_trips_on_get for the dedicated
    # coverage) -- turning them off never touches tz at all.
    want = {"alert_email_optin": expected}
    if expected:
        want["tz"] = "UTC"
    assert out["prefs"] == want


def test_alert_email_optin_bad_value_is_400(auth, store):
    with pytest.raises(HTTPException) as ei:
        account_prefs.save_prefs(account_prefs.PrefsRequest(alert_email_optin="maybe"), user=USER)
    assert ei.value.status_code == 400
    assert ei.value.detail["field"] == "alert_email_optin"
    assert auth.calls == [] and store.rows == []


def test_alert_categories_legal_subset_stored_sorted_deduped(auth, store):
    out = account_prefs.save_prefs(
        account_prefs.PrefsRequest(alert_categories=["thesis_window", "Holdings_Material_Change",
                                                       "thesis_window"]),
        user=USER)
    assert out["prefs"]["alert_categories"] == ["holdings_material_change", "thesis_window"]


def test_alert_categories_empty_list_is_legal(auth, store):
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(alert_categories=[]), user=USER)
    assert out["prefs"]["alert_categories"] == []


def test_alert_categories_unknown_member_rejects_whole_value(auth, store):
    with pytest.raises(HTTPException) as ei:
        account_prefs.save_prefs(
            account_prefs.PrefsRequest(alert_categories=["holdings_material_change", "wat"]),
            user=USER)
    assert ei.value.status_code == 400
    assert ei.value.detail["field"] == "alert_categories"
    assert auth.calls == [] and store.rows == []


def test_tz_stored_verbatim(auth, store):
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(tz="Asia/Hong_Kong"), user=USER)
    assert out["prefs"]["tz"] == "Asia/Hong_Kong"


@pytest.mark.parametrize("bad_tz", ["Mars/Olympus", "asia/hong_kong", ""])
def test_tz_bad_values_are_400(auth, store, bad_tz):
    with pytest.raises(HTTPException) as ei:
        account_prefs.save_prefs(account_prefs.PrefsRequest(tz=bad_tz), user=USER)
    assert ei.value.status_code == 400
    assert ei.value.detail["field"] == "tz"
    assert auth.calls == [] and store.rows == []


def test_quiet_hours_stored_as_pair(auth, store):
    out = account_prefs.save_prefs(
        account_prefs.PrefsRequest(quiet_hours={"start": "22:00", "end": "07:00"}), user=USER)
    assert out["prefs"]["quiet_hours"] == {"start": "22:00", "end": "07:00"}


def test_quiet_hours_off_sentinel_clears(auth, store):
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(quiet_hours="off"), user=USER)
    assert out["prefs"]["quiet_hours"] is None


def test_quiet_hours_equal_start_end_normalizes_to_none(auth, store):
    out = account_prefs.save_prefs(
        account_prefs.PrefsRequest(quiet_hours={"start": "09:00", "end": "09:00"}), user=USER)
    assert out["prefs"]["quiet_hours"] is None


@pytest.mark.parametrize("bad_qh", [
    {"start": "22:00"},
    {"start": "25:00", "end": "07:00"},
    {"start": "22:00", "end": "07:00", "x": 1},
])
def test_quiet_hours_bad_shapes_are_400(auth, store, bad_qh):
    with pytest.raises(HTTPException) as ei:
        account_prefs.save_prefs(account_prefs.PrefsRequest(quiet_hours=bad_qh), user=USER)
    assert ei.value.status_code == 400
    assert ei.value.detail["field"] == "quiet_hours"
    assert auth.calls == [] and store.rows == []


def test_alert_prefs_never_touch_email_prefs(auth, store):
    out = account_prefs.save_prefs(
        account_prefs.PrefsRequest(alert_email_optin=True, tz="UTC"), user=USER)
    assert out["email_prefs"] is False
    assert store.rows == []


def test_all_four_alert_fields_in_one_call(auth, store):
    out = account_prefs.save_prefs(
        account_prefs.PrefsRequest(alert_email_optin=True,
                                    alert_categories=["thesis_window"],
                                    tz="Asia/Hong_Kong",
                                    quiet_hours={"start": "22:00", "end": "07:00"}),
        user=USER)
    assert out["prefs"] == {
        "alert_email_optin": True, "alert_categories": ["thesis_window"],
        "tz": "Asia/Hong_Kong", "quiet_hours": {"start": "22:00", "end": "07:00"},
    }
    assert [c[0] for c in auth.calls] == ["PUT"]


def test_get_prefs_readback(auth, store):
    account_prefs.save_prefs(account_prefs.PrefsRequest(tz="Asia/Hong_Kong"), user=USER)
    user_with_tz = dict(USER, user_metadata=dict(USER["user_metadata"], tz="Asia/Hong_Kong"))
    out = account_prefs.read_prefs(user=user_with_tz)
    assert out["ok"] is True
    assert out["prefs"]["tz"] == "Asia/Hong_Kong"
    assert "alert_email_optin" in out["unset"]
    assert out["categories_available"] == ["holdings_material_change", "thesis_window"]


def test_get_prefs_route_is_registered():
    paths_methods = {(r.path, m) for r in account_prefs.router.routes for m in r.methods}
    assert ("/api/account/prefs", "GET") in paths_methods


@pytest.mark.parametrize("value, expected", [("ZH", "zh"), (" en ", "en")])
def test_values_are_normalised(auth, store, value, expected):
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(lang=value), user=USER)
    assert out["prefs"]["lang"] == expected


def test_lang_theme_brain_depth_bad_value_uses_default_error(auth, store):
    with pytest.raises(HTTPException) as ei:
        account_prefs.save_prefs(account_prefs.PrefsRequest(lang="fr"), user=USER)
    assert ei.value.detail["en"] == "We don't recognise that choice."


# --------------------------------------------------------------------------- #
# storage
# --------------------------------------------------------------------------- #
def test_metadata_write_merges_and_does_not_drop_other_keys(auth, store):
    """A partial user_metadata body has replaced the whole object on some GoTrue versions —
    the merge happens here, from the record the token verification already returned."""
    account_prefs.save_prefs(account_prefs.PrefsRequest(theme="dark"), user=USER)
    method, url, payload = auth.calls[0]
    assert method == "PUT"
    assert url == "https://proj.supabase.test/auth/v1/admin/users/9c1f-user"
    assert payload["user_metadata"] == {"display_name": "Ada", "lang": "en", "theme": "dark"}


def test_lang_mirrors_into_email_prefs(auth, store):
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(lang="zh"), user=USER)
    assert out == {"ok": True, "prefs": {"lang": "zh"}, "metadata": True, "email_prefs": True}
    row = store.rows[0]
    assert row["method"] == "POST"
    assert row["path"] == "email_prefs?on_conflict=user_id"
    assert row["prefer"] == "resolution=merge-duplicates,return=minimal"
    assert row["body"][0]["user_id"] == "9c1f-user"
    assert row["body"][0]["lang"] == "zh"
    assert row["body"][0]["updated_at"].startswith("20")


def test_theme_only_does_not_touch_email_prefs(auth, store):
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(theme="light"), user=USER)
    assert out["email_prefs"] is False
    assert store.rows == []


def test_both_keys_in_one_call(auth, store):
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(lang="en", theme="dark"), user=USER)
    assert out["prefs"] == {"lang": "en", "theme": "dark"}
    assert auth.calls[0][2]["user_metadata"]["theme"] == "dark"
    assert store.rows[0]["body"][0]["lang"] == "en"


# --------------------------------------------------------------------------- #
# brain_depth (Analyst OS W3) — the chat answer-length preference
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value, expected", [
    ("concise", "concise"), ("standard", "standard"), ("DEEP", "deep"), (" deep ", "deep"),
])
def test_brain_depth_is_accepted_and_normalised(auth, store, value, expected):
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(brain_depth=value), user=USER)
    assert out["prefs"] == {"brain_depth": expected}
    assert auth.calls[0][2]["user_metadata"] == {
        "display_name": "Ada", "lang": "en", "brain_depth": expected}


def test_brain_depth_alone_does_not_touch_email_prefs(auth, store):
    """The email mirror exists for LANGUAGE. A depth change must not write a row."""
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(brain_depth="deep"), user=USER)
    assert out["email_prefs"] is False
    assert store.rows == []


def test_all_three_keys_in_one_call(auth, store):
    out = account_prefs.save_prefs(
        account_prefs.PrefsRequest(lang="zh", theme="dark", brain_depth="concise"), user=USER)
    assert out["prefs"] == {"lang": "zh", "theme": "dark", "brain_depth": "concise"}
    assert auth.calls[0][2]["user_metadata"] == {
        "display_name": "Ada", "lang": "zh", "theme": "dark", "brain_depth": "concise"}
    assert store.rows[0]["body"][0]["lang"] == "zh"


def test_the_enum_table_is_the_libs(auth, store):
    """One table, shared with the chat tool — a value the route accepts is a value the
    gateway's set_chat_preference accepts, because there is only one list."""
    from lib import user_prefs

    assert account_prefs.LANGS is user_prefs.PREF_VALUES["lang"]
    assert account_prefs.THEMES is user_prefs.PREF_VALUES["theme"]
    assert account_prefs.DEPTHS is user_prefs.PREF_VALUES["brain_depth"]


def test_the_route_still_makes_exactly_one_network_call(auth, store):
    """The lib can read current metadata before merging; this path must NOT — the verified
    token's record is already in hand, so a GET here would be a wasted round trip on every
    debounced theme toggle."""
    account_prefs.save_prefs(account_prefs.PrefsRequest(brain_depth="concise"), user=USER)
    assert [c[0] for c in auth.calls] == ["PUT"]


# --------------------------------------------------------------------------- #
# fail-soft
# --------------------------------------------------------------------------- #
def test_partial_failure_is_reported_honestly(monkeypatch, store):
    """The mirror is not load-bearing — a metadata write that landed is still a success,
    and the response says which sink took it rather than claiming both did."""
    failing = _Auth(fail=True)
    monkeypatch.setattr(urllib.request, "urlopen", failing.urlopen)
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_ROLE_KEY", "service-role-test-key")
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(lang="zh"), user=USER)
    assert out == {"ok": True, "prefs": {"lang": "zh"}, "metadata": False, "email_prefs": True}


def test_total_failure_is_a_502_not_a_lie(monkeypatch):
    failing = _Auth(fail=True)
    monkeypatch.setattr(urllib.request, "urlopen", failing.urlopen)
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_ROLE_KEY", "service-role-test-key")
    monkeypatch.setattr(billing, "_pg", _Store(fail=True).pg)
    with pytest.raises(HTTPException) as ei:
        account_prefs.save_prefs(account_prefs.PrefsRequest(lang="zh"), user=USER)
    assert ei.value.status_code == 502


def test_unconfigured_service_role_skips_the_metadata_write(monkeypatch, store):
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_ROLE_KEY", "")
    called = []
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **kw: called.append(1) or _Resp())
    out = account_prefs.save_prefs(account_prefs.PrefsRequest(lang="en"), user=USER)
    assert called == [] and out["metadata"] is False and out["email_prefs"] is True


# --------------------------------------------------------------------------- #
# the route is actually mounted
# --------------------------------------------------------------------------- #
def test_route_is_registered_on_the_router():
    paths = {r.path for r in account_prefs.router.routes}
    assert "/api/account/prefs" in paths
    route = next(r for r in account_prefs.router.routes if r.path == "/api/account/prefs")
    assert "POST" in route.methods
