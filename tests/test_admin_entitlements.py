"""tests/test_admin_entitlements.py — admin/entitlements.py (MNZ W2 operator console).

Fully offline. The two data planes are stubbed at their seams:
  * READ roster  → monkeypatch ``admin.users._query`` (the Management-API PAT SELECT) +
    force ``users.status()`` configured, so ``list_users`` exercises the real join/filter
    plumbing without any network.
  * WRITE actions → monkeypatch the billing spine on the ``app.billing`` module object:
    ``_pg`` (the service-role PostgREST call — serves ``_row_for`` reads AND captures the
    ``_upsert_entitlement`` bodies), ``_stripe`` (a fake Stripe with Subscription
    list/modify/cancel), ``_invalidate`` (no-op), and ``SUPABASE_SERVICE_ROLE_KEY`` truthy.

Coverage maps to the mission's test asks:
  - list join surfaces name + email + tier (+ filter/search plumbing).
  - each action produces the exact entitlement row / Stripe call.
  - comp-over-active-Stripe is BLOCKED without force, and without cancel_stripe under force.
  - force + cancel_stripe cancels the sub then writes the comp.
  - extend/reset trial on a REAL trialing sub calls Subscription.modify (not a comp).
  - lifetime pass row shape: current_period_end NULL, status active, source comp.
  - live server: 401 for an unauthenticated caller, 403 for a write missing the CSRF header.
"""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin import auth, entitlements, users  # noqa: E402


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _FakeSub:
    def __init__(self, sid, status):
        self.id, self.status = sid, status


class _SubAPI:
    """Records modify/cancel calls; lists a scripted set of subscriptions."""
    def __init__(self, subs):
        self._subs = subs
        self.modified: list[dict] = []
        self.canceled: list[str] = []

    def list(self, **kw):
        return type("R", (), {"data": list(self._subs)})()

    def modify(self, sid, **kw):
        self.modified.append({"id": sid, **kw})
        return _FakeSub(sid, "trialing")

    def cancel(self, sid, **kw):
        self.canceled.append(sid)
        # after cancel, drop it from the live set (mirrors real Stripe)
        self._subs = [s for s in self._subs if s.id != sid]
        return _FakeSub(sid, "canceled")


class _FakeStripe:
    def __init__(self, subs=None):
        self.Subscription = _SubAPI(subs or [])


@pytest.fixture
def wired(monkeypatch):
    """Wire the billing spine to in-memory fakes and return handles for assertions.

    ``pg_rows`` is the current user_entitlements row(s) that ``_row_for`` / GET reads see;
    ``upserts`` captures every POST body ``_upsert_entitlement`` sends. ``computed`` is what
    ``_compute_entitlement`` returns after a Stripe trial-modify (the webhook-parity recompute).
    """
    from app import billing

    state = {
        "pg_rows": [],                                   # served for GET user_entitlements?...
        "upserts": [],                                   # captured POST bodies
        "computed": {"tier": "essential", "features": ["site_full", "terminal_live_options"],
                     "status": "trialing", "current_period_end": "2026-08-01T00:00:00+00:00"},
        "invalidated": [],
    }
    fake = _FakeStripe()

    def _pg(method, path, body=None, prefer=None, timeout=6):
        if method == "GET" and path.startswith("user_entitlements"):
            return list(state["pg_rows"])
        if method == "POST" and path.startswith("user_entitlements"):
            # billing._upsert_entitlement / _persist_customer send [row]
            state["upserts"].extend(body or [])
            return None
        return None

    monkeypatch.setattr(billing, "SUPABASE_SERVICE_ROLE_KEY", "svc-role-test")
    monkeypatch.setattr(billing, "_pg", _pg)
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_compute_entitlement", lambda cid: dict(state["computed"]))
    monkeypatch.setattr(billing, "_invalidate", lambda uid: state["invalidated"].append(uid))
    return state, fake


def _set_row(state, **kw):
    row = {"stripe_customer_id": None, "tier": "free", "status": "none",
           "source": "stripe", "current_period_end": None}
    row.update(kw)
    state["pg_rows"] = [row]


UID = "11111111-1111-1111-1111-111111111111"


# ===========================================================================
# READ — list join (name + email + tier), filters, search
# ===========================================================================
def _rows_query(sqls):
    """The paged SELECT that joins the tables and returns user columns (not the count/summary)."""
    return next(s for s in sqls if "coalesce(e.tier,'free') as tier" in s)


def test_list_users_joins_name_email_tier(monkeypatch):
    sqls: list[str] = []

    def _query(sql):
        sqls.append(sql)
        if "count(*)" in sql and "group by" not in sql:
            return [{"n": 1}]
        if "group by" in sql:
            return [{"tier": "pro", "status": "active", "n": 1}]
        return [{
            "user_id": UID, "email": "ada@example.com", "name": "Ada Lovelace",
            "provider": "google", "tier": "pro", "status": "active", "source": "stripe",
            "stripe_customer_id": "cus_1", "current_period_end": "2026-09-01",
            "updated_at": "2026-07-23 10:00", "created": "2026-01-01",
        }]

    monkeypatch.setattr(users, "status", lambda: {"configured": True, "project_ref": "x", "reason": None, "setup_steps": []})
    monkeypatch.setattr(users, "_query", _query)

    out = entitlements.list_users()
    assert out["ok"] is True
    u = out["users"][0]
    assert u["name"] == "Ada Lovelace" and u["email"] == "ada@example.com" and u["tier"] == "pro"
    assert out["total"] == 1 and out["pages"] == 1
    # the join + name coalesce is in the ROWS SQL (auth.users ⋈ user_entitlements, raw_user_meta_data)
    rows_sql = _rows_query(sqls)
    assert "from auth.users u" in rows_sql and "left join public.user_entitlements e on e.user_id = u.id" in rows_sql
    assert "raw_user_meta_data" in rows_sql
    # the tier×status summary is present for the filter chips
    assert out["summary"] == [{"tier": "pro", "status": "active", "n": 1}]


def test_list_users_filters_and_search_are_sanitized(monkeypatch):
    sqls: list[str] = []

    def _query(sql):
        sqls.append(sql)
        if "count(*)" in sql and "group by" not in sql:
            return [{"n": 0}]
        return []

    monkeypatch.setattr(users, "status", lambda: {"configured": True})
    monkeypatch.setattr(users, "_query", _query)

    entitlements.list_users(tier="pro", status="trialing", search="o'brien", page=2, page_size=25)
    rows_sql = _rows_query(sqls)
    assert "coalesce(e.tier,'free') in ('pro')" in rows_sql and "coalesce(e.status,'none') = 'trialing'" in rows_sql
    # single quote doubled (no injection), wrapped in ILIKE against email + name
    assert "o''brien" in rows_sql and "ilike" in rows_sql
    # OFFSET reflects page 2 × page_size 25
    assert "offset 25" in rows_sql and "limit 25" in rows_sql
    # an out-of-allowlist tier/status token is simply ignored (never interpolated raw)
    sqls.clear()
    entitlements.list_users(tier="'; drop table", status="haxx")
    assert "drop table" not in _rows_query(sqls)


def test_list_users_not_configured(monkeypatch):
    monkeypatch.setattr(users, "status", lambda: {"configured": False, "reason": "no PAT", "setup_steps": ["step"]})
    out = entitlements.list_users()
    assert out["ok"] is False and out["reason"] == "no PAT"


# ===========================================================================
# WRITE — change_tier (comp upgrade/downgrade)
# ===========================================================================
def test_change_tier_upgrade_writes_comp_active_no_stripe(wired):
    state, _ = wired
    _set_row(state, stripe_customer_id=None, tier="free", status="none")
    payload, code = entitlements.act({"user_id": UID, "action": "change_tier",
                                      "params": {"tier": "pro"}}, operator="operator")
    assert code == 200 and payload["ok"] is True
    row = state["upserts"][-1]
    assert row["tier"] == "pro" and row["status"] == "active" and row["source"] == "comp"
    assert row["current_period_end"] is None
    # features come from _tier_features(pro)
    assert "chat_opus" in row["features"] and "site_full" in row["features"]
    assert UID in state["invalidated"]


def test_change_tier_to_free_empties_features(wired):
    state, _ = wired
    _set_row(state, stripe_customer_id=None, tier="pro", status="active")
    payload, code = entitlements.act({"user_id": UID, "action": "change_tier",
                                      "params": {"tier": "free"}}, operator="operator")
    assert code == 200
    row = state["upserts"][-1]
    assert row["tier"] == "free" and row["status"] == "none" and row["features"] == []
    assert row["current_period_end"] is None and row["source"] == "comp"


def test_change_tier_bad_tier_rejected(wired):
    _state, _ = wired
    payload, code = entitlements.act({"user_id": UID, "action": "change_tier",
                                      "params": {"tier": "platinum"}}, operator="operator")
    assert code == 400 and "tier must be one of" in payload["error"]


# ===========================================================================
# WRITE — comp-vs-live-Stripe honesty gate (the crux)
# ===========================================================================
def test_comp_over_active_stripe_blocked_without_force(wired):
    state, fake = wired
    _set_row(state, stripe_customer_id="cus_live", tier="pro", status="active")
    fake.Subscription._subs = [_FakeSub("sub_live", "active")]
    payload, code = entitlements.act({"user_id": UID, "action": "change_tier",
                                      "params": {"tier": "essential"}}, operator="operator")
    assert code == 409 and payload["ok"] is False and payload["code"] == "stripe_active"
    assert "sub_live" in payload["live_subscriptions"]
    # NOTHING was written and the sub was NOT cancelled
    assert state["upserts"] == [] and fake.Subscription.canceled == []


def test_force_without_cancel_still_blocked(wired):
    state, fake = wired
    _set_row(state, stripe_customer_id="cus_live", tier="pro", status="active")
    fake.Subscription._subs = [_FakeSub("sub_live", "active")]
    payload, code = entitlements.act({"user_id": UID, "action": "change_tier",
                                      "params": {"tier": "essential", "force": True}}, operator="operator")
    assert code == 409 and payload["code"] == "force_needs_cancel"
    assert state["upserts"] == [] and fake.Subscription.canceled == []


def test_force_comp_cancels_stripe_then_writes(wired):
    state, fake = wired
    _set_row(state, stripe_customer_id="cus_live", tier="pro", status="active")
    fake.Subscription._subs = [_FakeSub("sub_live", "active")]
    payload, code = entitlements.act(
        {"user_id": UID, "action": "change_tier",
         "params": {"tier": "essential", "force": True, "cancel_stripe": True}}, operator="operator")
    assert code == 200 and payload["ok"] is True
    # the live sub was cancelled FIRST, then the comp written (durable vs. reconciler)
    assert fake.Subscription.canceled == ["sub_live"]
    row = state["upserts"][-1]
    assert row["tier"] == "essential" and row["source"] == "comp" and row["status"] == "active"


def test_comp_on_non_stripe_user_needs_no_force(wired):
    """A user whose row has a customer id but NO live sub can be comped freely."""
    state, fake = wired
    _set_row(state, stripe_customer_id="cus_old", tier="free", status="canceled")
    fake.Subscription._subs = [_FakeSub("sub_old", "canceled")]   # not active/trialing
    payload, code = entitlements.act({"user_id": UID, "action": "change_tier",
                                      "params": {"tier": "pro"}}, operator="operator")
    assert code == 200 and state["upserts"][-1]["tier"] == "pro"
    assert fake.Subscription.canceled == []


# ===========================================================================
# WRITE — free passes (monthly / annual / lifetime)
# ===========================================================================
def test_grant_monthly_pass_sets_30d_window(wired):
    state, _ = wired
    _set_row(state, stripe_customer_id=None)
    payload, code = entitlements.act({"user_id": UID, "action": "grant_pass",
                                      "params": {"kind": "monthly", "tier": "essential"}}, operator="operator")
    assert code == 200
    row = state["upserts"][-1]
    assert row["tier"] == "essential" and row["status"] == "active" and row["source"] == "comp"
    assert row["current_period_end"] is not None   # a real end date ~+30d
    assert row["current_period_end"][:4] in ("2026", "2027")


def test_grant_annual_pass_sets_far_window(wired):
    state, _ = wired
    _set_row(state, stripe_customer_id=None)
    entitlements.act({"user_id": UID, "action": "grant_pass",
                      "params": {"kind": "annual", "tier": "pro"}}, operator="operator")
    row = state["upserts"][-1]
    assert row["current_period_end"] is not None and row["tier"] == "pro"


def test_grant_lifetime_pass_row_shape(wired):
    """Lifetime ⟺ comp + status active + current_period_end NULL (the mission's exact shape)."""
    state, _ = wired
    _set_row(state, stripe_customer_id=None)
    payload, code = entitlements.act({"user_id": UID, "action": "grant_pass",
                                      "params": {"kind": "lifetime", "tier": "pro"}}, operator="operator")
    assert code == 200
    row = state["upserts"][-1]
    assert row["source"] == "comp" and row["status"] == "active"
    assert row["current_period_end"] is None            # lifetime = NULL end
    assert row["tier"] == "pro" and "chat_opus" in row["features"]


def test_grant_pass_bad_kind_and_tier(wired):
    _state, _ = wired
    _p, code = entitlements.act({"user_id": UID, "action": "grant_pass",
                                 "params": {"kind": "decade", "tier": "pro"}}, operator="operator")
    assert code == 400
    _p, code = entitlements.act({"user_id": UID, "action": "grant_pass",
                                 "params": {"kind": "monthly", "tier": "free"}}, operator="operator")
    assert code == 400   # a pass to free is meaningless


# ===========================================================================
# WRITE — remove_comp → free
# ===========================================================================
def test_remove_comp_reverts_to_free(wired):
    state, _ = wired
    _set_row(state, stripe_customer_id=None, tier="pro", status="active", source="comp")
    payload, code = entitlements.act({"user_id": UID, "action": "remove_comp"}, operator="operator")
    assert code == 200
    row = state["upserts"][-1]
    assert row["tier"] == "free" and row["status"] == "none" and row["features"] == []
    assert row["current_period_end"] is None and row["source"] == "comp"


def test_remove_comp_over_live_stripe_blocked(wired):
    """Even a downgrade-to-free comp is transient over a live sub → same gate."""
    state, fake = wired
    _set_row(state, stripe_customer_id="cus_live", tier="pro", status="active")
    fake.Subscription._subs = [_FakeSub("sub_live", "active")]
    _p, code = entitlements.act({"user_id": UID, "action": "remove_comp"}, operator="operator")
    assert code == 409 and state["upserts"] == []


# ===========================================================================
# WRITE — extend / reset trial (the ONE direct-Stripe path)
# ===========================================================================
def test_extend_trial_on_real_stripe_sub_modifies_not_comps(wired):
    state, fake = wired
    _set_row(state, stripe_customer_id="cus_live", tier="essential", status="trialing")
    fake.Subscription._subs = [_FakeSub("sub_trial", "trialing")]
    payload, code = entitlements.act({"user_id": UID, "action": "extend_trial",
                                      "params": {"days": 14}}, operator="operator")
    assert code == 200 and payload["mechanic"] == "stripe"
    # Subscription.modify called with a trial_end epoch + proration_behavior none
    assert len(fake.Subscription.modified) == 1
    mod = fake.Subscription.modified[0]
    assert mod["id"] == "sub_trial" and mod["proration_behavior"] == "none"
    assert isinstance(mod["trial_end"], int)
    # then recompute→upsert→invalidate (webhook-parity), source is the recomputed (stripe) row
    assert state["upserts"], "expected a recompute upsert after modify"
    assert UID in state["invalidated"]


def test_extend_trial_without_stripe_sub_writes_trialing_comp(wired):
    state, fake = wired
    _set_row(state, stripe_customer_id=None, tier="essential", status="none")
    fake.Subscription._subs = []
    payload, code = entitlements.act({"user_id": UID, "action": "extend_trial",
                                      "params": {"days": 10}}, operator="operator")
    assert code == 200 and payload["mechanic"] == "comp"
    row = state["upserts"][-1]
    assert row["status"] == "trialing" and row["source"] == "comp"
    assert row["current_period_end"] is not None   # the trial window
    assert fake.Subscription.modified == []         # never touched a (nonexistent) sub


def test_reset_trial_uses_7d_and_modifies_real_sub(wired):
    state, fake = wired
    _set_row(state, stripe_customer_id="cus_live", tier="pro", status="trialing")
    fake.Subscription._subs = [_FakeSub("sub_trial", "trialing")]
    payload, code = entitlements.act({"user_id": UID, "action": "reset_trial"}, operator="operator")
    assert code == 200 and payload["mechanic"] == "stripe"
    assert fake.Subscription.modified[0]["id"] == "sub_trial"


def test_extend_trial_bad_days_rejected(wired):
    _state, _ = wired
    _p, code = entitlements.act({"user_id": UID, "action": "extend_trial",
                                 "params": {"days": 0}}, operator="operator")
    assert code == 400


# ===========================================================================
# Dispatch guards
# ===========================================================================
def test_unknown_action_and_missing_user(wired):
    _state, _ = wired
    _p, code = entitlements.act({"user_id": UID, "action": "nope"}, operator="operator")
    assert code == 400
    _p, code = entitlements.act({"action": "change_tier", "params": {"tier": "pro"}}, operator="operator")
    assert code == 400


def test_no_service_role_key_503(monkeypatch):
    from app import billing
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_ROLE_KEY", "")
    p, code = entitlements.act({"user_id": UID, "action": "remove_comp"}, operator="operator")
    assert code == 503 and p["code"] == "no_writer"


# ===========================================================================
# Live server auth — 401 (no session) / 403 (write missing CSRF)
# ===========================================================================
def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), __import__("admin.server", fromlist=["Handler"]).Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _req(port, path, method="GET", body=None, cookies=None, headers=None):
    h = dict(headers or {})
    if body is not None:
        h["Content-Type"] = "application/json"
    if cookies:
        h["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h, method=method)
    return urllib.request.urlopen(req, timeout=10)


def test_entitlements_routes_require_auth_and_csrf(monkeypatch):
    import os
    old = {k: os.environ.get(k) for k in ("ADMIN_DEPLOYED", "ADMIN_PASSWORD", "ADMIN_SESSION_SECRET")}
    os.environ.update({"ADMIN_DEPLOYED": "1", "ADMIN_PASSWORD": "s3cret", "ADMIN_SESSION_SECRET": "it-secret"})
    auth._attempts.clear()
    httpd, port = _server()
    try:
        # GET list without a session → 401
        try:
            _req(port, "/api/entitlements")
            raise AssertionError("expected 401 for unauthenticated GET")
        except urllib.error.HTTPError as e:
            assert e.code == 401

        # POST action without a session → 401
        try:
            _req(port, "/api/entitlements/action", "POST", {"user_id": UID, "action": "remove_comp"})
            raise AssertionError("expected 401 for unauthenticated POST")
        except urllib.error.HTTPError as e:
            assert e.code == 401

        # log in, get cookies
        r = _req(port, "/api/login", "POST", {"password": "s3cret"})
        jar = {}
        for c in (r.headers.get_all("Set-Cookie") or []):
            k, _, rest = c.partition("=")
            jar[k] = rest.split(";")[0]

        # authed POST WITHOUT the CSRF header → 403 (even with a valid session)
        try:
            _req(port, "/api/entitlements/action", "POST",
                 {"user_id": UID, "action": "remove_comp"},
                 cookies={auth.SESSION_COOKIE: jar[auth.SESSION_COOKIE],
                          auth.CSRF_COOKIE: jar[auth.CSRF_COOKIE]})
            raise AssertionError("expected 403 (missing CSRF header)")
        except urllib.error.HTTPError as e:
            assert e.code == 403 and "CSRF" in json.loads(e.read())["error"]
    finally:
        httpd.shutdown(); httpd.server_close()
        auth._attempts.clear()
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_roster_base_is_all_users(monkeypatch):
    """The lockdown makes registration the floor: users with NO entitlement row must
    surface as implicit free — the roster's base table is auth.users."""
    captured = []
    monkeypatch.setattr(entitlements.users, "status", lambda: {"configured": True})
    monkeypatch.setattr(entitlements.users, "_query", lambda sql: captured.append(sql) or [])
    entitlements.list_users()
    rows_sql = next(s for s in captured if "coalesce(e.tier,'free') as tier" in s)
    assert "from auth.users u" in rows_sql
    assert "left join public.user_entitlements e" in rows_sql


# ===========================================================================
# The 'insider' alias (rename migration, Phase 2 — the direction REVERSED)
#
# The console is a WRITE plane, so tolerance here is normalise-then-validate, never a
# widened tuple: whatever survives the check is the literal string _write_comp puts into
# user_entitlements.tier, and an operator action must never write the RETIRED value back
# onto a row the catalog has already moved.
# ===========================================================================
def test_change_tier_accepts_the_alias_and_writes_the_wire_value(wired):
    state, _ = wired
    _set_row(state, stripe_customer_id=None, tier="free", status="none")
    payload, code = entitlements.act({"user_id": UID, "action": "change_tier",
                                      "params": {"tier": "insider"}}, operator="operator")
    assert code == 200 and payload["ok"] is True
    row = state["upserts"][-1]
    assert row["tier"] == "essential", "an alias must never reach the entitlement row"
    assert row["status"] == "active" and row["source"] == "comp"
    # features resolve off the CANONICAL tier, so the alias buys the same access
    assert "site_full" in row["features"] and "terminal_live_options" in row["features"]
    assert "chat_opus" not in row["features"]


def test_change_tier_alias_row_is_identical_to_the_canonical_one(wired):
    """Every field but the wall-clock stamp, so the parity claim is total rather than a
    handful of hand-picked keys."""
    def _write(tier):
        _set_row(state, stripe_customer_id=None, tier="free", status="none")
        entitlements.act({"user_id": UID, "action": "change_tier",
                          "params": {"tier": tier}}, operator="operator")
        return {k: v for k, v in state["upserts"][-1].items() if k != "updated_at"}

    state, _ = wired
    assert _write("insider") == _write("essential")


def test_grant_pass_accepts_the_alias_and_writes_the_wire_value(wired):
    state, _ = wired
    _set_row(state, stripe_customer_id=None)
    _payload, code = entitlements.act({"user_id": UID, "action": "grant_pass",
                                       "params": {"kind": "monthly", "tier": "INSIDER "}},
                                      operator="operator")
    assert code == 200
    assert state["upserts"][-1]["tier"] == "essential"


def test_a_still_unknown_tier_is_still_rejected(wired):
    """Widening the alias must not widen the enum."""
    _state, _ = wired
    _p, code = entitlements.act({"user_id": UID, "action": "change_tier",
                                 "params": {"tier": "platinum"}}, operator="operator")
    assert code == 400
    _p, code = entitlements.act({"user_id": UID, "action": "grant_pass",
                                 "params": {"kind": "monthly", "tier": "essentialish"}},
                                operator="operator")
    assert code == 400


def test_roster_filter_maps_the_alias_onto_the_stored_value(monkeypatch):
    """?tier=insider must resolve to the canonical filter — and ?tier=essential must ALSO
    match the pre-rename rows, which are never back-filled. Tokens stay allow-listed, so
    the SQL interpolation surface is unchanged."""
    sqls: list[str] = []

    def _query(sql):
        sqls.append(sql)
        if "count(*)" in sql and "group by" not in sql:
            return [{"n": 0}]
        return []

    monkeypatch.setattr(users, "status", lambda: {"configured": True})
    monkeypatch.setattr(users, "_query", _query)

    entitlements.list_users(tier="insider")
    rows_sql = _rows_query(sqls)
    assert "coalesce(e.tier,'free') in ('essential','insider')" in rows_sql, (
        "the roster must match BOTH spellings or a pre-rename paying member vanishes "
        "from the operator's view")

    sqls.clear()
    entitlements.list_users(tier="essential")
    assert "coalesce(e.tier,'free') in ('essential','insider')" in _rows_query(sqls)

    sqls.clear()
    entitlements.list_users(tier="pro")
    assert "coalesce(e.tier,'free') in ('pro')" in _rows_query(sqls), (
        "an un-renamed tier must not pick up a stray alias")


def test_the_grant_tuples_stay_canonical():
    """Named, so a future 'just add essential to the tuple' edit trips this instead of
    quietly re-arming the write path it was meant to protect."""
    assert entitlements._GRANT_TIERS == ("essential", "pro")
    assert entitlements._ALL_TIERS == ("free", "essential", "pro")
