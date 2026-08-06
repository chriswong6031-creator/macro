"""Supabase browser-facing origin (GFW proxy) — the session-key migration hazard.

*.supabase.co is Cloudflare-fronted and throttled in mainland China, so the browser
SDK can be pointed at our own origin (``watchlist.supabase.browser_url`` →
Caddy ``handle_path /sb/*``). The trap that makes this a migration rather than a
config edit:

    BOTH browser clients derive their session storage key from the URL they are
    handed — ``theme.js._storageKey()`` explicitly, and supabase-js's own default in
    ``account.js``. Point them at ``https://www.mastermind-x.com/sb`` without pinning
    the key and the browser starts writing ``sb-www-auth-token`` while
    ``app.main._sb_storage_key()`` (derived from the SERVER's SUPABASE_URL, which
    stays on supabase.co) keeps reading ``sb-fsldfzlxyavsuwqbceod-auth-token``.

    Every existing session is orphaned — every signed-in user silently logged out —
    and the server never sees a session again: the regwall, the paywall and the
    analytics visitor attribution all read that cookie.

So the contract these tests pin is: changing the browser-facing ORIGIN must never
change the session KEY. `ref` is what carries the project identity across the move.
"""
from __future__ import annotations

import json

import pytest

from lib import site_assets


def _cfg(monkeypatch, **supabase):
    base = {"url": "https://fsldfzlxyavsuwqbceod.supabase.co",
            "anon_key": "sb_publishable_test"}
    base.update(supabase)
    monkeypatch.setattr(site_assets.config, "load",
                        lambda: {"watchlist": {"supabase": base}})
    return json.loads(site_assets.supabase_cfg_json())


# --------------------------------------------------------------------------- #
# the hazard
# --------------------------------------------------------------------------- #
def test_browser_url_moves_the_origin_but_not_the_project_ref(monkeypatch):
    direct = _cfg(monkeypatch)
    proxied = _cfg(monkeypatch, browser_url="https://www.mastermind-x.com/sb")

    assert direct["url"] == "https://fsldfzlxyavsuwqbceod.supabase.co"
    assert proxied["url"] == "https://www.mastermind-x.com/sb", "browser calls OUR origin"
    # the one thing that must NOT move
    assert direct["ref"] == proxied["ref"] == "fsldfzlxyavsuwqbceod"


def test_session_cookie_key_is_identical_across_the_move(monkeypatch):
    """The actual regression: a different key logs every user out."""
    def key(cfg):
        return "sb-" + cfg["ref"] + "-auth-token"

    assert key(_cfg(monkeypatch)) == key(
        _cfg(monkeypatch, browser_url="https://www.mastermind-x.com/sb"))


def test_ref_matches_what_the_server_reads(monkeypatch):
    """app.main._sb_storage_key derives the ref from the SERVER url; they must agree,
    or the browser writes a cookie the server never looks for."""
    proxied = _cfg(monkeypatch, browser_url="https://www.mastermind-x.com/sb")
    server_ref = "https://fsldfzlxyavsuwqbceod.supabase.co".split("://", 1)[-1].split(".", 1)[0]
    assert proxied["ref"] == server_ref


def test_ref_is_never_derived_from_the_browser_host(monkeypatch):
    """A ref of 'www' is the exact shape of the bug — assert it can't be produced."""
    proxied = _cfg(monkeypatch, browser_url="https://www.mastermind-x.com/sb")
    assert proxied["ref"] != "www"
    assert proxied["ref"] not in proxied["url"], "ref must come from the project, not the proxy"


# --------------------------------------------------------------------------- #
# default is inert
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("blank", ["", "   ", None])
def test_unset_browser_url_keeps_todays_behaviour(monkeypatch, blank):
    cfg = _cfg(monkeypatch, browser_url=blank)
    assert cfg["url"] == "https://fsldfzlxyavsuwqbceod.supabase.co"


def test_trailing_slash_is_normalised(monkeypatch):
    """supabase-js concatenates ${url}/auth/v1 — a trailing slash yields a // path."""
    cfg = _cfg(monkeypatch, browser_url="https://www.mastermind-x.com/sb/")
    assert cfg["url"] == "https://www.mastermind-x.com/sb"


def test_unconfigured_supabase_still_emits_null(monkeypatch):
    monkeypatch.setattr(site_assets.config, "load", lambda: {"watchlist": {"supabase": {}}})
    assert site_assets.supabase_cfg_json() == "null"


def test_project_ref_helper_is_total():
    assert site_assets.project_ref("https://abc.supabase.co") == "abc"
    assert site_assets.project_ref("") == ""


# --------------------------------------------------------------------------- #
# the two browser clients must actually USE ref
# --------------------------------------------------------------------------- #
def test_theme_js_pins_the_storage_key_to_ref():
    src = (site_assets.Path(__file__).resolve().parent.parent
           / "templates" / "theme.js").read_text()
    assert "_sbCfg.ref" in src, "theme.js._storageKey must prefer the baked project ref"
    i = src.index("function _storageKey")
    body = src[i:i + 400]
    assert "ref" in body.split("hostname")[0], "ref must be checked BEFORE the url fallback"


def _account_js() -> str:
    return (site_assets.Path(__file__).resolve().parent.parent
            / "templates" / "account.js").read_text()


def test_account_js_pins_the_storage_key_to_ref():
    src = _account_js()
    assert "storageKey" in src, "account.js must not rely on supabase-js's url-derived default"
    assert "SUPA.ref" in src


def test_account_js_normalisation_carries_ref_through():
    """The pin above is DEAD unless normSupa preserves `ref`.

    This is the bug that shipped in the first cut of this PR: normSupa returned
    {url, anonKey} only, so SUPA.ref was always undefined, `storageKey` was never
    set, and supabase-js fell back to the url-derived default — the exact failure
    the pin exists to prevent. The source still CONTAINED "SUPA.ref", so a
    string-grep test passed while the code did nothing. Pin the return literal.
    """
    import re
    src = _account_js()
    m = re.search(r"function normSupa\(c\)\s*\{(.*?)\n  \}", src, re.S)
    assert m, "normSupa not found — did account.js change shape?"
    body = m.group(1)
    ret = body[body.index("return"):]
    assert "ref" in ret, (
        "normSupa drops `ref`, so SUPA.ref is undefined and the storageKey pin is dead")


# --------------------------------------------------------------------------- #
# the Caddy route the browser_url points at
# --------------------------------------------------------------------------- #
def test_caddy_exposes_the_sb_proxy_and_the_gate_ignores_it():
    caddy = (site_assets.Path(__file__).resolve().parent.parent
             / "app" / "deploy" / "Caddyfile").read_text()
    assert "handle_path /sb/*" in caddy, "browser_url has nothing to talk to without this"
    assert "fsldfzlxyavsuwqbceod.supabase.co" in caddy
    # Probed live before this existed: /sb/* fell through to the site gate's 401.
    # Every gate matcher must exempt it or the proxy is unreachable.
    matchers = [ln for ln in caddy.splitlines() if "not path /api/*" in ln]
    assert matchers, "gate matchers not found — did the Caddyfile shape change?"
    for ln in matchers:
        assert "/sb/*" in ln, f"gate would swallow the proxy: {ln.strip()[:80]}"


def test_proxied_auth_responses_are_not_cacheable():
    caddy = (site_assets.Path(__file__).resolve().parent.parent
             / "app" / "deploy" / "Caddyfile").read_text()
    block = caddy.split("handle_path /sb/*", 1)[1][:600]
    assert "no-store" in block, "an edge-cached auth response is a cross-user session leak"
