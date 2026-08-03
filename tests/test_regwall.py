"""tests/test_regwall.py — the registration wall's fail-closed contract.

Offline: the Supabase verifier + cookie parser (app.main) are monkeypatched.
NOTE (repo memory fastapi-includedrouter-route-verify): endpoints are verified
via TestClient RESPONSES, never by scanning app.routes.

The one law under test: gated paths NEVER serve without a verified session —
missing cookie, bad token, verifier outage, and module exceptions all DENY
(302 to the landing with the sheet param), and nothing this endpoint returns
is cacheable.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import regwall
from app.main import app

client = TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def _wall_on(monkeypatch):
    monkeypatch.delenv("REGWALL_ENABLED", raising=False)


def _check(cookies=None, orig="/bonds.html"):
    return client.get("/api/regwall/check", cookies=cookies or {},
                      headers={"X-Original-Uri": orig})


def test_no_cookie_denies_with_ret():
    r = _check()
    assert r.status_code == 302
    assert r.headers["location"] == "/?signin=1&ret=/bonds.html"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-regwall"] == "deny"


def test_valid_session_allows(monkeypatch):
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda req: "tok_good")
    monkeypatch.setattr("app.main._mm_verify_uid_cached", lambda tok: "11111111-1111-1111-1111-111111111111")
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-regwall"] == "allow"
    assert r.headers["cache-control"] == "no-store"


def test_invalid_token_denies(monkeypatch):
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda req: "tok_bad")
    monkeypatch.setattr("app.main._mm_verify_uid_cached", lambda tok: None)
    assert _check().status_code == 302


def test_verifier_exception_fails_closed(monkeypatch):
    def boom(tok):
        raise RuntimeError("supabase down")
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda req: "tok")
    monkeypatch.setattr("app.main._mm_verify_uid_cached", boom)
    r = _check()
    assert r.status_code == 302, "an erroring verifier must DENY, never allow"


def test_ret_sanitization():
    # off-origin and garbage rets are dropped, never echoed
    r = _check(orig="//evil.example/steal")
    assert r.status_code == 302
    assert r.headers["location"] == "/?signin=1"
    r = _check(orig="https://evil.example/x")
    assert r.headers["location"] == "/?signin=1"


def test_public_path_allows_without_session():
    # the marketing funnel is public — allow without a session (never 302 to login)
    r = _check(orig="/index.html")
    assert r.status_code == 204
    assert r.headers["x-regwall"] == "public"


def test_research_vault_preview_allows_without_session():
    r = _check(orig="/research_vault.html")
    assert r.status_code == 204
    assert r.headers["x-regwall"] == "public"


def test_confluence_screener_lead_magnet_allows_without_session():
    r = _check(orig="/confluence_screener.html")
    assert r.status_code == 204
    assert r.headers["x-regwall"] == "public"


@pytest.mark.parametrize("path", ["/macro.html", "/start.html", "/us_stocks.html"])
def test_public_dashboard_previews_allow_without_session(path):
    r = _check(orig=path)
    assert r.status_code == 204
    assert r.headers["x-regwall"] == "public"


@pytest.mark.parametrize(
    "path", ["/special_situations.html", "/china_special_situations.html"])
def test_tier_preview_shells_allow_without_session(path):
    """W1a (SEO_SUPERCHARGE_MASTERPLAN): the two tier-preview SHELLS were promoted
    free_registered → public, so an anonymous visitor — and Googlebot, which never
    has a session — must get the preview + upgrade wall instead of a 302 to
    /?signin=1. This module is the ONLY guard on regwall.PUBLIC_PATHS: the boundary
    suite diffs Caddy against site_access.yml and never imports this mirror, so a
    promotion that lands in two of the three mirrors passes everything else.
    """
    r = _check(orig=path)
    assert r.status_code == 204, f"{path} must be public (no session needed)"
    assert r.headers["x-regwall"] == "public", path


@pytest.mark.parametrize(
    "path",
    [
        "/premiumdata/special_situations.json",
        "/premiumdata/china_special_situations.json",
        "/allocationdata/special_situations.json",
        "/chinaspecialdata/special.json",
    ],
)
def test_opening_the_shells_did_not_open_their_payloads(path):
    """The other half of W1a, and the half that would be expensive to get wrong.
    The split IS the gate: the shell holds the preview slice, every paid row ships
    in these payloads. They are asset requests, so an anonymous fetch must die at
    the registration wall's 401 long before app/paywall.py's enforced_early check
    ever runs — a 204 here would mean the promotion leaked the board.
    """
    r = client.get("/api/regwall/check",
                   headers={"X-Original-Uri": path, "X-Original-Kind": "asset"})
    assert r.status_code == 401, f"{path} must stay gated after the shell opened"
    assert r.json()["locked"] is True


@pytest.mark.parametrize(
    "path",
    [
        "/stocks/NVDA.html",
        "/products/market-terminal.html",
        "/tools/index.html",
        "/tools/calculators/roi.html",
        "/learn/technical/index.html",
        "/blog/win-rate-is-overrated.html",
    ],
)
def test_public_seo_trees_allow_without_session(path):
    # the free/SEO estate must stay crawlable — Googlebot carries no session, so
    # these MUST 204, never 302, or the wall silently kills organic reach.
    r = _check(orig=path)
    assert r.status_code == 204, f"{path} must be public (no session needed)"
    assert r.headers["x-regwall"] == "public", path


def test_gated_dashboard_still_denies_with_ret():
    # a non-public dashboard still requires an account and echoes ret for return
    r = _check(orig="/bonds.html")
    assert r.status_code == 302
    assert r.headers["location"] == "/?signin=1&ret=/bonds.html"


def test_deny_skips_public_ret():
    # _deny never bounces back to a public page (pointless); gated pages ARE echoed
    assert regwall._deny("/index.html").headers["Location"] == "/?signin=1"
    assert regwall._deny("/macro.html").headers["Location"] == "/?signin=1"
    assert regwall._deny("/stocks/NVDA.html").headers["Location"] == "/?signin=1"
    assert regwall._deny("/bonds.html").headers["Location"] == "/?signin=1&ret=/bonds.html"


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("REGWALL_ENABLED", "0")
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-regwall"] == "off"


def test_deny_helper_percent_encodes():
    assert regwall._deny("/a b.html").headers["Location"] == "/?signin=1&ret=/a%20b.html"


def test_asset_denial_is_json_not_redirect():
    r = client.get(
        "/api/regwall/check",
        headers={"X-Original-Uri": "/neuralwebdata/ruling_graph.json",
                 "X-Original-Kind": "asset"},
    )
    assert r.status_code == 401
    assert r.json() == {
        "locked": True,
        "reason": "authentication_required",
        "signin_url": "/?signin=1",
    }
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["vary"] == "Cookie"


def test_asset_valid_session_allows(monkeypatch):
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda req: "tok_good")
    monkeypatch.setattr("app.main._mm_verify_uid_cached", lambda tok: "11111111-1111-1111-1111-111111111111")
    r = client.get(
        "/api/regwall/check",
        headers={"X-Original-Uri": "/oracledata/tm_episodes.json",
                 "X-Original-Kind": "asset"},
    )
    assert r.status_code == 204
    assert r.headers["x-regwall"] == "allow"
