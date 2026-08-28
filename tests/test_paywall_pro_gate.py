"""Contract tests for the Pro-only host gate in front of bot.mastermind-x.com.

Two halves, and the second is the one that carries the feature:

* /api/paywall/check_pro (app/paywall.py) -- WHO the caller is, on every path, with
  no classification against config/site_access.yml (that file describes the MACRO
  site's URL space; the bot desk is a different application);
* the Caddy wiring (app/deploy/Caddyfile) that calls it, and the /health hole that
  keeps admin/uptime_board.py able to see an outage rather than a locked door.

"Anonymous is blocked" is the cheap half. The assertions that matter are ESSENTIAL
being blocked -- the tier below the floor, held by real paying customers -- and the
unknown-tier and broken-catalog paths denying rather than guessing.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import paywall
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
CADDY = (ROOT / "app" / "deploy" / "Caddyfile").read_text(encoding="utf-8")

client = TestClient(app, follow_redirects=False)
UID = "22222222-2222-2222-2222-222222222222"
EMAIL = "member@example.com"
OPERATOR = "ops@mastermind-x.com"


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("PAYWALL_ENABLED", raising=False)
    monkeypatch.delenv("PAYWALL_GRACE_SECONDS", raising=False)
    monkeypatch.delenv("PAYWALL_ENTITLEMENT_CACHE_SECONDS", raising=False)
    # Never inherit a real operator grant from the developer's shell: with this set,
    # every "free is locked" assertion below could pass for the wrong reason.
    monkeypatch.delenv("BRAIN_UNLIMITED_ALLOWLIST", raising=False)
    paywall._AUTH_CACHE.clear()
    paywall._ENT_CACHE.clear()
    paywall._CONFIG_CACHE = None
    paywall._PLANS_CACHE = None


def _check(path="/api/positions", headers=None, cookies=None):
    """A bot-host subrequest. Default path is an API lane -> the JSON deny branch."""
    hdrs = {"X-Original-Uri": path}
    hdrs.update(headers or {})
    return client.get("/api/paywall/check_pro", headers=hdrs, cookies=cookies or {})


def _signed_in(monkeypatch, email=EMAIL):
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda request: "tok")
    monkeypatch.setattr(paywall, "_fresh_identity", lambda token: (UID, email))


def _row(monkeypatch, tier, status="active", features=("site_full",), email=EMAIL):
    _signed_in(monkeypatch, email)
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: ({"tier": tier, "status": status, "features": list(features)}, True),
    )


# ---------------------------------------------------------------------------
# Who gets in
# ---------------------------------------------------------------------------
def test_anonymous_is_locked(monkeypatch):
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda request: None)
    r = _check()
    assert r.status_code == 403
    assert r.json() == {
        "locked": True,
        "tier": "anon",
        "required_tier": "pro",
        "upgrade_url": "/plans.html?upgrade=1&plan=pro",
    }


def test_signed_in_but_unverifiable_token_is_locked(monkeypatch):
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda request: "tok")
    monkeypatch.setattr(paywall, "_fresh_identity", lambda token: (None, ""))
    r = _check()
    assert r.status_code == 403
    assert r.json()["tier"] == "anon"


def test_free_is_locked(monkeypatch):
    _row(monkeypatch, "free", features=())
    r = _check()
    assert r.status_code == 403
    assert r.json()["tier"] == "free"


def test_essential_is_locked(monkeypatch):
    """THE feature. A paying Essential member holds site_full and is still not Pro.

    Without the tier comparison this row is `allowed=True` from _entitled() and the
    desk opens to the whole paid base -- a gate that only stops anonymous visitors.
    """
    _row(monkeypatch, "essential")
    r = _check()
    assert r.status_code == 403
    assert r.json()["tier"] == "essential"
    assert r.json()["required_tier"] == "pro"


def test_pre_rename_essential_row_is_locked_and_reported_as_essential(monkeypatch):
    """`insider` is the permanent legacy spelling of `essential` (lib/tiers.py).

    Both halves are load-bearing: it must not pass, and it must be REPORTED as the
    tier the customer actually holds. Un-normalized it would rank nowhere -- same
    403, but the body would name a tier the catalog no longer sells.
    """
    _row(monkeypatch, "insider")
    r = _check()
    assert r.status_code == 403
    assert r.json()["tier"] == "essential"


def test_pro_is_allowed(monkeypatch):
    _row(monkeypatch, "pro")
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-paywall"] == "allow-pro"
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["vary"] == "Cookie"
    assert not r.content


def test_trialing_pro_is_allowed(monkeypatch):
    _row(monkeypatch, "pro", status="trialing")
    assert _check().status_code == 204


def test_unlimited_operator_tier_is_allowed(monkeypatch):
    """`unlimited` is surfaced by /api/me off the brain-gateway allowlist and is NOT in
    tier_rank. Unknown-denies would lock the operator out of his own desk."""
    _row(monkeypatch, "unlimited")
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-paywall"] == "allow-unlimited"


@pytest.mark.parametrize("tier", ["platinum", "founding", "pro_plus", "PRO-MAX", ""])
def test_tier_outside_the_catalog_is_locked(monkeypatch, tier):
    """Unknown => deny. These rows carry site_full and an active status, so _entitled()
    says yes; the only thing refusing them is the rank lookup."""
    _row(monkeypatch, tier)
    assert _check().status_code == 403


@pytest.mark.parametrize("status", ["past_due", "canceled", "incomplete", "none", "paused"])
def test_pro_tier_without_an_active_subscription_is_locked(monkeypatch, status):
    _row(monkeypatch, "pro", status=status)
    r = _check()
    assert r.status_code == 403
    assert r.json()["tier"] == "pro"


def test_pro_row_missing_the_feature_is_locked(monkeypatch):
    _row(monkeypatch, "pro", features=())
    assert _check().status_code == 403


# ---------------------------------------------------------------------------
# The operator bypass -- BRAIN_UNLIMITED_ALLOWLIST, the same grant /api/me reads
#
# /api/me computes the real tier and then OVERWRITES it to `unlimited` off this
# allowlist, without ever touching user_entitlements. So the row of an operator whose
# account card says "Unlimited" may well say `free`, and a gate that reads only the row
# would lock him out of his own desk while the pill claims otherwise. These tests pin
# the two surfaces to one answer.
# ---------------------------------------------------------------------------
def test_allowlisted_operator_with_a_free_row_is_allowed(monkeypatch):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", OPERATOR)
    _row(monkeypatch, "free", status="none", features=(), email=OPERATOR)
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-paywall"] == "allow-unlimited"


def test_allowlisted_operator_with_no_entitlement_row_at_all_is_allowed(monkeypatch):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", OPERATOR)
    _signed_in(monkeypatch, OPERATOR)
    monkeypatch.setattr(paywall, "_store_entitlement", lambda uid: (None, True))
    assert _check().status_code == 204


def test_allowlisted_operator_never_reads_the_entitlement_store(monkeypatch):
    """The bypass runs BEFORE the entitlement read, so a store outage cannot lock the
    operator out either. Proven by making any read explode."""
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", OPERATOR)
    _signed_in(monkeypatch, OPERATOR)
    monkeypatch.setattr(
        paywall, "_store_entitlement", lambda uid: (_ for _ in ()).throw(AssertionError("read!"))
    )
    assert _check().status_code == 204


def test_non_allowlisted_email_with_a_free_row_is_locked(monkeypatch):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", OPERATOR)
    _row(monkeypatch, "free", status="none", features=(), email="someone.else@example.com")
    assert _check().status_code == 403


@pytest.mark.parametrize("value", ["", "   ", ","])
def test_empty_or_unset_allowlist_grants_nobody_anything(monkeypatch, value):
    """The allowlist is an env-only operator grant (never committed). With nothing in
    it the gate must behave exactly as if the bypass did not exist."""
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", value)
    _row(monkeypatch, "free", status="none", features=(), email=OPERATOR)
    assert _check().status_code == 403
    paywall._ENT_CACHE.clear()
    _row(monkeypatch, "pro", email=OPERATOR)
    assert _check().status_code == 204


def test_unset_allowlist_grants_nobody_anything(monkeypatch):
    _row(monkeypatch, "free", status="none", features=(), email=OPERATOR)
    assert _check().status_code == 403
    paywall._ENT_CACHE.clear()
    _row(monkeypatch, "pro", email=OPERATOR)
    assert _check().status_code == 204


@pytest.mark.parametrize(
    "stored,presented",
    [
        (OPERATOR, "  OPS@Mastermind-X.com "),
        ("  Ops@Mastermind-X.com , other@x.io", OPERATOR),
        ("a@x.io,ops@mastermind-x.com", "OPS@MASTERMIND-X.COM"),
    ],
)
def test_allowlist_matching_is_case_and_whitespace_insensitive(monkeypatch, stored, presented):
    """Delegated to brain_gateway._unlimited_allowed, which strips+lowers both sides.
    Pinned here because a second, stricter copy of the parsing in this module is
    exactly the drift this bypass is routed through the shared accessor to avoid."""
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", stored)
    _row(monkeypatch, "free", status="none", features=(), email=presented)
    assert _check().status_code == 204


def test_identity_without_an_email_gets_no_bypass_and_the_normal_tier_check(monkeypatch):
    """A Supabase response carrying no email cannot match any allowlist entry -- and
    must not short-circuit into one either (_unlimited_allowed returns False on '')."""
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", OPERATOR)
    _row(monkeypatch, "free", status="none", features=(), email="")
    assert _check().status_code == 403
    paywall._ENT_CACHE.clear()
    _row(monkeypatch, "pro", email="")
    assert _check().status_code == 204


class _Boom:
    def _unlimited_allowed(self, email):
        raise RuntimeError("brain gateway exploded")


class _Renamed:
    """The upstream helper renamed out from under us -> AttributeError."""


@pytest.mark.parametrize(
    "broken",
    [
        lambda: (_ for _ in ()).throw(RuntimeError("brain_gateway unavailable")),
        lambda: _Boom(),
        lambda: _Renamed(),
    ],
    ids=["import-raises", "call-raises", "helper-renamed"],
)
def test_a_broken_allowlist_lookup_falls_through_cleanly(monkeypatch, broken):
    """It must be neither the reason a Pro member is denied nor the reason a Free
    visitor is admitted -- the verdict falls back to the ordinary tier check."""
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", OPERATOR)
    monkeypatch.setattr("app.main._brain_module", broken)
    _row(monkeypatch, "pro", email=OPERATOR)
    assert _check().status_code == 204, "a broken allowlist denied a paying Pro member"
    paywall._ENT_CACHE.clear()
    _row(monkeypatch, "free", status="none", features=(), email=OPERATOR)
    assert _check().status_code == 403, "a broken allowlist admitted an unpaid visitor"


def test_the_bypass_uses_the_same_accessor_api_me_uses(monkeypatch):
    """Not a mock-shaped restatement of the code: this asserts the call actually lands
    on app.main._brain_module() -> brain_gateway._unlimited_allowed, which is what
    keeps the account pill and this door from drifting apart."""
    seen = []
    real = paywall._operator_unlimited

    def spy():
        from engine.neuralweb import brain_gateway

        seen.append(brain_gateway)
        return brain_gateway

    monkeypatch.setattr("app.main._brain_module", spy)
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", OPERATOR)
    assert real(OPERATOR) is True
    assert real("nobody@example.com") is False
    assert seen, "the bypass did not go through app.main._brain_module()"
    assert seen[0]._unlimited_allowed(OPERATOR) is True


# ---------------------------------------------------------------------------
# _fresh_identity -- one upstream call, both fields, one expiry
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_supabase(monkeypatch, payload, calls):
    def urlopen(req, timeout=None):
        calls.append(getattr(req, "full_url", None))
        return _FakeResp(payload)

    monkeypatch.setattr(paywall.urllib.request, "urlopen", urlopen)


def test_identity_reads_uid_and_email_from_a_single_supabase_call(monkeypatch):
    calls: list = []
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": 9_999_999_999}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    token = f"header.{payload}.signature"
    _fake_supabase(monkeypatch, {"id": UID, "email": "  Ops@Mastermind-X.com "}, calls)
    assert paywall._fresh_identity(token) == (UID, "ops@mastermind-x.com")
    assert len(calls) == 1
    # Cached together: neither accessor issues a second request, and they cannot
    # disagree about which verification the pair came from.
    assert paywall._fresh_uid(token) == UID
    assert paywall._fresh_identity(token) == (UID, "ops@mastermind-x.com")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"id": UID}, (UID, "")),
        ({"id": UID, "email": None}, (UID, "")),
        ({"id": UID, "email": 42}, (UID, "")),
        ({"id": "not-a-uuid", "email": "x@y.z"}, (None, "")),
        ({"email": "x@y.z"}, (None, "")),
        ({}, (None, "")),
    ],
)
def test_identity_degrades_to_empty_email_and_never_a_bogus_uid(monkeypatch, payload, expected):
    _fake_supabase(monkeypatch, payload, [])
    assert paywall._fresh_identity("tok-shape") == expected


def test_fresh_uid_contract_is_unchanged_by_the_refactor(monkeypatch):
    """The macro wall still calls _fresh_uid; its signature and answers must not move."""
    calls: list = []
    _fake_supabase(monkeypatch, {"id": UID, "email": EMAIL}, calls)
    assert paywall._fresh_uid("tok-1") == UID
    paywall._AUTH_CACHE.clear()
    _fake_supabase(monkeypatch, {"id": "garbage"}, calls)
    assert paywall._fresh_uid("tok-2") is None


# ---------------------------------------------------------------------------
# Fail closed
# ---------------------------------------------------------------------------
def test_auth_lookup_raising_denies(monkeypatch):
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda request: "tok")
    monkeypatch.setattr(
        paywall,
        "_fresh_identity",
        lambda token: (_ for _ in ()).throw(RuntimeError("supabase down")),
    )
    r = _check()
    assert r.status_code == 403
    assert r.json()["tier"] == "anon"


def test_entitlement_store_raising_denies(monkeypatch):
    _signed_in(monkeypatch)
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: (_ for _ in ()).throw(RuntimeError("postgrest down")),
    )
    assert _check().status_code == 403


def test_unreadable_catalog_denies_everyone_including_the_uncapped_tier(monkeypatch):
    """The rank order is read BEFORE the uncapped exception, deliberately: one rule."""
    monkeypatch.setattr(
        paywall, "_load_plans", lambda: (_ for _ in ()).throw(ValueError("no catalog"))
    )
    for tier in ("pro", "unlimited"):
        _row(monkeypatch, tier)
        paywall._ENT_CACHE.clear()
        assert _check().status_code == 403, tier


def test_catalog_that_no_longer_sells_pro_denies(monkeypatch, tmp_path):
    """`.index('pro')` raising is the intended behaviour, not an oversight: a catalog
    without the floor tier must not silently admit the next-best thing."""
    cat = tmp_path / "plans.yml"
    cat.write_text("tier_rank: [free, essential]\n", encoding="utf-8")
    monkeypatch.setattr(paywall, "PLANS_CONFIG", cat)
    _row(monkeypatch, "pro")
    assert _check().status_code == 403


@pytest.mark.parametrize("body", ["tier_rank: []\n", "tier_rank: pro\n", "[]\n", "\n"])
def test_shapeless_catalog_denies(monkeypatch, tmp_path, body):
    cat = tmp_path / "plans.yml"
    cat.write_text(body, encoding="utf-8")
    monkeypatch.setattr(paywall, "PLANS_CONFIG", cat)
    _row(monkeypatch, "pro")
    assert _check().status_code == 403


@pytest.mark.parametrize("path", ["//evil.test/x", "/a/../secret", "/bad%00", "/a\\b", ""])
def test_odd_original_uri_never_opens_the_door_and_never_crashes(monkeypatch, path):
    """The URI is read for ONE reason -- picking the deny body's shape. Identity is the
    authority, and Caddy forwards the ORIGINAL request to the origin, so this endpoint
    never authorizes a path and cannot be path-confused into doing so.

    Hence the contract is the pair below: a weird URI can neither admit a non-Pro
    caller nor produce a 5xx (a 5xx is not 2xx, so Caddy would deny -- but it would
    deny by crashing, with no interstitial and a stack trace in the log).
    """
    _row(monkeypatch, "essential")
    assert _check(path).status_code == 403
    paywall._ENT_CACHE.clear()
    _row(monkeypatch, "pro")
    assert _check(path).status_code in (204, 403)


# ---------------------------------------------------------------------------
# Shape of the answer
# ---------------------------------------------------------------------------
def test_browser_document_denial_is_html_and_uncacheable(monkeypatch):
    _row(monkeypatch, "essential")
    r = _check("/desk", headers={"Sec-Fetch-Dest": "document"})
    assert r.status_code == 403
    assert "text/html" in r.headers["content-type"]
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["vary"] == "Cookie"
    assert r.text.lstrip().lower().startswith("<!doctype html")


def test_bot_root_without_fetch_metadata_still_reads_as_a_document(monkeypatch):
    _row(monkeypatch, "free", features=())
    r = _check("/")
    assert r.status_code == 403
    assert "text/html" in r.headers["content-type"]


def test_non_document_denial_is_json_naming_the_required_tier(monkeypatch):
    _row(monkeypatch, "essential")
    r = _check("/api/positions")
    assert r.status_code == 403
    assert "application/json" in r.headers["content-type"]
    assert r.json()["required_tier"] == "pro"
    assert r.json()["upgrade_url"] == "/plans.html?upgrade=1&plan=pro"


def test_interstitial_file_is_what_a_denied_browser_receives(monkeypatch, tmp_path):
    """The page body is owned by app/paywall_pro_interstitial.html. Pinned through a
    temp file so this suite is green whether or not that file has landed yet."""
    page = tmp_path / "paywall_pro_interstitial.html"
    page.write_text("<!doctype html><title>x</title>PRO-INTERSTITIAL-SENTINEL", encoding="utf-8")
    monkeypatch.setattr(paywall, "PRO_INTERSTITIAL", page)
    _row(monkeypatch, "free", features=())
    r = _check("/", headers={"Sec-Fetch-Dest": "document"})
    assert r.status_code == 403
    assert "PRO-INTERSTITIAL-SENTINEL" in r.text


def test_missing_interstitial_still_denies_with_a_self_contained_page(monkeypatch, tmp_path):
    monkeypatch.setattr(paywall, "PRO_INTERSTITIAL", tmp_path / "does_not_exist.html")
    _row(monkeypatch, "free", features=())
    r = _check("/", headers={"Sec-Fetch-Dest": "document"})
    assert r.status_code == 403
    assert r.text.lstrip().lower().startswith("<!doctype html")
    # Absolute: this page renders on bot.mastermind-x.com, where /plans.html is not served.
    assert "https://mastermind-x.com/plans.html?upgrade=1&amp;plan=pro" in r.text
    assert "http://" not in r.text.replace("https://", "")


# ---------------------------------------------------------------------------
# What this endpoint deliberately does NOT do
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("switch", ["0", "1"])
def test_verdict_does_not_depend_on_the_macro_site_paywall_switch(monkeypatch, switch):
    """PAYWALL_ENABLED stages the MACRO wall. The bot desk is Pro-only either way --
    including while the switch is off, which is the state this ships into."""
    monkeypatch.setenv("PAYWALL_ENABLED", switch)
    _row(monkeypatch, "essential")
    assert _check().status_code == 403
    paywall._ENT_CACHE.clear()
    _row(monkeypatch, "pro")
    assert _check().status_code == 204


def test_no_path_classification_happens(monkeypatch):
    """The bot app owns its own URL space. A path the MACRO policy would 404 or wave
    through must get the same identity verdict as any other path on this host."""
    _row(monkeypatch, "pro")
    for path in (
        "/_mockup_research_vault.html",  # macro policy: deny -> 404 on the sibling
        "/plans.html",                   # macro policy: public -> 204 on the sibling
        "/desk",                         # exists only on the bot app
        "/api/positions",
    ):
        paywall._ENT_CACHE.clear()
        assert _check(path).status_code == 204, path
    monkeypatch.setattr(paywall, "_store_entitlement",
                        lambda uid: ({"tier": "free", "status": "none", "features": []}, True))
    for path in ("/_mockup_research_vault.html", "/plans.html", "/desk"):
        paywall._ENT_CACHE.clear()
        assert _check(path).status_code == 403, path


def test_sibling_macro_wall_is_unchanged_by_this_endpoint(monkeypatch):
    """Add, don't refactor: /api/paywall/check keeps classifying and keeps staging."""
    r = client.get(
        "/api/paywall/check",
        headers={"X-Original-Uri": "/neuralwebdata/ruling_graph.json", "X-Original-Kind": "asset"},
    )
    assert r.status_code == 204
    assert r.headers["x-paywall"] == "off"


# ---------------------------------------------------------------------------
# The wiring. A perfect endpoint nobody calls gates nothing.
# ---------------------------------------------------------------------------
def _bot_block() -> str:
    m = re.search(r"^bot\.mastermind-x\.com \{\n(.*?)^\}$", CADDY, flags=re.S | re.M)
    assert m, "the bot.mastermind-x.com site block is gone from app/deploy/Caddyfile"
    return m.group(1)


def test_caddy_routes_the_bot_host_through_the_pro_gate():
    body = _bot_block()
    assert "rewrite /api/paywall/check_pro" in body, (
        "bot.mastermind-x.com no longer issues the Pro auth subrequest -- the desk is "
        "open to anyone again"
    )
    assert "reverse_proxy 127.0.0.1:8000 {" in body, "the subrequest must go to macro-api"
    assert "header_up X-Original-Uri {http.request.uri}" in body
    assert re.search(r"@\w+ status 2xx\n\t+handle_response @\w+ \{\n\t+\}", body), (
        "the 2xx continue-to-origin matcher is missing; without it every request is "
        "answered by the auth response"
    )


def test_health_is_handled_ahead_of_the_gate_and_ungated():
    body = _bot_block()
    health = body.index("handle /health {")
    gate = body.index("/api/paywall/check_pro")
    assert health < gate, (
        "handle /health must precede the gated route -- admin/uptime_board.py probes it "
        "to tell 'the service is down' from 'you are not Pro'"
    )
    hblock = re.search(r"handle /health \{\n(.*?)\n\t\}", body, flags=re.S).group(1)
    assert "reverse_proxy 127.0.0.1:8001" in hblock
    assert "paywall" not in hblock, "/health must not be gated"


def test_gated_branch_is_never_shared_cache_material():
    """This host is orange-clouded; a Pro-only body in Cloudflare's cache is a leak."""
    body = _bot_block()
    gate = body.index("/api/paywall/check_pro")
    cache = body.index('header Cache-Control "private, no-store"')
    vary = body.index('header Vary "Cookie"')
    origin = body.index("reverse_proxy 127.0.0.1:8001", vary)
    assert gate < cache < vary < origin, (
        "the gated branch must set private/no-store + Vary: Cookie after the auth "
        "subrequest and before falling through to the bot origin"
    )


def test_bot_block_keeps_its_sni_and_robots_contract():
    """The block predates the gate and must not lose the reasons it existed."""
    body = _bot_block()
    assert "tls internal" in body, "removing this returns the origin handshake to HTTP 525"
    assert 'X-Robots-Tag "noindex, nofollow, noarchive"' in body
    assert "encode zstd gzip" in body


def test_uptime_probe_watches_the_open_health_path_with_a_real_assertion():
    """A None-expectation probe against a gated root collects a 403 and calls it up."""
    from admin.uptime_board import TARGETS

    bot = [t for t in TARGETS if t[1].startswith("https://bot.mastermind-x.com")]
    assert bot == [("Brain bot", "https://bot.mastermind-x.com/health", 200)], bot
