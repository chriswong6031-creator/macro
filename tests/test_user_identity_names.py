"""Name-first identity coverage for admin rosters, analytics, and account profiles."""
from __future__ import annotations

from pathlib import Path

from admin import users
from app import billing, main


def test_display_name_sql_covers_supabase_metadata_shapes():
    sql = users.display_name_sql("person")
    assert "person.raw_user_meta_data" in sql
    for key in ("display_name", "name", "full_name", "first_name", "last_name",
                "given_name", "family_name"):
        assert f"->>'{key}'" in sql
    assert sql.startswith("coalesce(")


def test_recent_users_selects_name(monkeypatch):
    seen: list[str] = []

    monkeypatch.setattr(users, "status", lambda: {"configured": True})
    monkeypatch.setattr(
        users,
        "_query",
        lambda sql: seen.append(sql) or [{
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "provider": "google",
        }],
    )

    out = users.recent(limit=20)
    assert out["users"][0]["name"] == "Ada Lovelace"
    assert "as name" in seen[0]
    assert "raw_user_meta_data" in seen[0]


def test_subscribers_selects_name(monkeypatch):
    seen: list[str] = []

    def query(sql):
        seen.append(sql)
        if "from public.user_entitlements e" in sql:
            return [{"name": "Grace Hopper", "email": "grace@example.com"}]
        return []

    monkeypatch.setattr(users, "status", lambda: {"configured": True})
    monkeypatch.setattr(users, "_query", query)

    out = users.subscribers()
    assert out["subscribers"][0]["name"] == "Grace Hopper"
    assert "as name" in seen[1]


def test_profile_name_prefers_explicit_display_name():
    user = {
        "email": "ada@example.com",
        "user_metadata": {
            "display_name": "  Ada Lovelace  ",
            "name": "Provider Name",
            "full_name": "Other Name",
        },
    }
    assert main._user_display_name(user) == "Ada Lovelace"


def test_profile_name_supports_split_provider_names():
    user = {
        "user_metadata": {
            "given_name": "Grace",
            "family_name": "Hopper",
        },
    }
    assert main._user_display_name(user) == "Grace Hopper"
    assert main._user_display_name({"user_metadata": {}, "email": "fallback@example.com"}) is None


def test_account_profile_includes_name(monkeypatch):
    monkeypatch.setattr(
        billing,
        "read_entitlement",
        lambda _uid: {
            "tier": "free",
            "features": [],
            "status": "none",
            "current_period_end": None,
        },
    )
    out = main.account(user={
        "id": "user-1",
        "email": "ada@example.com",
        "user_metadata": {"full_name": "Ada Lovelace"},
    })
    assert out["name"] == "Ada Lovelace"
    assert out["email"] == "ada@example.com"


def test_me_profile_includes_name(monkeypatch):
    monkeypatch.setattr(
        billing,
        "read_entitlement",
        lambda _uid: {
            "tier": "free",
            "features": [],
            "status": "none",
            "current_period_end": None,
        },
    )

    class Gateway:
        @staticmethod
        def get_user_quotas(*_args, **_kwargs):
            return {"tier": "free", "quotas": {}}

    monkeypatch.setattr(main, "_brain_module", lambda: Gateway)
    out = main.me(user={
        "id": "user-1",
        "email": "grace@example.com",
        "user_metadata": {"given_name": "Grace", "family_name": "Hopper"},
    })
    assert out["name"] == "Grace Hopper"
    assert out["email"] == "grace@example.com"


def test_frontends_render_name_before_email():
    repo = Path(__file__).resolve().parent.parent
    admin_js = (repo / "admin" / "static" / "app.js").read_text()
    account_js = (repo / "templates" / "account.js").read_text()

    assert "anRegisteredIdentity(s.name, s.email" in admin_js
    assert "anRegisteredIdentity(v.name, v.email" in admin_js
    assert "u.name || u.email || \"—\"" in admin_js
    assert "a.name || a.email || T('account')" in account_js
