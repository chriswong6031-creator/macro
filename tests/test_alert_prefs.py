"""tests/test_alert_prefs.py — B-F08-1a alert delivery preferences.

Storage-shape + no-site/data-write + JS source contract for the preferences half of
MO-PAID-085 (email opt-in, category, timezone, quiet hours). Fully offline — same
stubbed seams as tests/test_account_prefs.py (urllib.request.urlopen, billing._pg).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import account_prefs, billing  # noqa: E402
from lib import user_prefs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
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
    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    def urlopen(self, req, timeout=None):
        payload = json.loads(req.data.decode()) if req.data else {}
        self.calls.append((req.get_method(), req.full_url, payload))
        return _Resp()


@pytest.fixture
def auth(monkeypatch) -> _Auth:
    a = _Auth()
    monkeypatch.setattr(urllib.request, "urlopen", a.urlopen)
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_ROLE_KEY", "service-role-test-key")
    monkeypatch.setattr(billing, "SUPABASE_URL", "https://proj.supabase.test")
    return a


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(billing, "_pg", lambda *a, **kw: None)


# --------------------------------------------------------------------------- #
# atomics — top-level keys, never a nested "prefs" blob
# --------------------------------------------------------------------------- #
def test_new_keys_are_top_level_not_nested(auth, store):
    account_prefs.save_prefs(
        account_prefs.PrefsRequest(tz="Asia/Hong_Kong", alert_email_optin=True), user=USER)
    _, _, payload = auth.calls[0]
    meta = payload["user_metadata"]
    assert meta["tz"] == "Asia/Hong_Kong"
    assert meta["alert_email_optin"] is True
    assert "prefs" not in meta
    assert json.dumps(payload).find('"prefs"') == -1


def test_merge_proof_quiet_hours_onto_existing_base(auth, store):
    """Writing quiet_hours onto a base already holding alert_categories + theme drops neither."""
    base_user = dict(USER, user_metadata=dict(
        USER["user_metadata"], alert_categories=["thesis_window"], theme="dark"))
    account_prefs.save_prefs(
        account_prefs.PrefsRequest(quiet_hours={"start": "22:00", "end": "07:00"}),
        user=base_user)
    _, _, payload = auth.calls[0]
    meta = payload["user_metadata"]
    assert meta["alert_categories"] == ["thesis_window"]
    assert meta["theme"] == "dark"
    assert meta["quiet_hours"] == {"start": "22:00", "end": "07:00"}


# --------------------------------------------------------------------------- #
# no site/ or data/ writes (slice1 ceiling)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mod_path", ["app/account_prefs.py", "lib/user_prefs.py"])
def test_no_filesystem_write_calls_in_source(mod_path):
    """No real filesystem write surface — the module talks to Supabase over HTTP only.
    ``open(`` legitimately appears as a substring of ``urlopen(`` (stdlib HTTP), so we
    check for an actual builtin ``open(`` call (not preceded by an identifier char) and for
    genuine local-filesystem write idioms, never docstring prose mentioning a path."""
    import re
    src = (ROOT / mod_path).read_text()
    assert not re.search(r"(?<![\w.])open\(", src), f"{mod_path} calls builtin open("
    assert "Path(" not in src, f"{mod_path} contains forbidden 'Path('"
    assert not re.search(r"\.write\(", src), f"{mod_path} contains forbidden '.write('"
    for banned in ("site/", "data/"):
        assert not re.search(re.escape(banned) + r"['\"]", src), (
            f"{mod_path} contains a real path literal forbidden {banned!r}")


@pytest.mark.skipif(not (ROOT / "site").is_dir() or not any((ROOT / "site").iterdir()),
                    reason="needs_full_checkout")
def test_no_site_or_data_mutation_on_post(auth, store):
    def _snapshot(d: Path):
        return {str(f): (f.stat().st_size, f.stat().st_mtime)
                for f in d.rglob("*") if f.is_file()}

    site_dir, data_dir = ROOT / "site", ROOT / "data"
    before_site = _snapshot(site_dir) if site_dir.is_dir() else {}
    before_data = _snapshot(data_dir) if data_dir.is_dir() else {}
    account_prefs.save_prefs(
        account_prefs.PrefsRequest(alert_email_optin=True, alert_categories=["thesis_window"],
                                    tz="UTC", quiet_hours={"start": "22:00", "end": "07:00"}),
        user=USER)
    after_site = _snapshot(site_dir) if site_dir.is_dir() else {}
    after_data = _snapshot(data_dir) if data_dir.is_dir() else {}
    assert before_site == after_site
    assert before_data == after_data


# --------------------------------------------------------------------------- #
# no LLM involvement
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mod_path", ["app/account_prefs.py", "lib/user_prefs.py"])
def test_no_llm_imports(mod_path):
    """No LLM-originated signals: neither module IMPORTS an LLM surface. A prose mention
    of another module's name in a docstring (e.g. this file's own comment explaining why
    it exists, which references brain_gateway's *unrelated* helper by name) is not an
    import and is not banned — only an actual import/call statement is."""
    import ast
    src = (ROOT / mod_path).read_text()
    tree = ast.parse(src)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    for banned in ("anthropic", "engine.neuralweb", "brain_gateway"):
        assert not any(banned in n for n in names), f"{mod_path} imports forbidden {banned!r}"


# --------------------------------------------------------------------------- #
# JS source contract (no browser harness in this repo)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def account_js() -> str:
    return (ROOT / "templates" / "account.js").read_text()


def test_alert_group_builder_exists_and_is_called(account_js):
    assert "function alertPrefsGroupHTML" in account_js
    assert "alertPrefsGroupHTML(ap, unset)" in account_js
    assert "function bodySignedIn" in account_js


def test_mount_standalone_and_macro_do_not_reference_undefined_el(account_js):
    """Real browser evidence capture (mockups/evidence/account_alert_prefs/) caught a
    runtime ReferenceError no source-only test here could see: mountStandalone() and
    mountMacro() each carried a stray `el.addEventListener('change', onChange, true);`
    line copy-pasted from mountEmbed(el) -- but neither function takes an `el`
    parameter. Every call to window.MMAccount.open() on a macro (embed-host) page or
    a standalone app page threw `el is not defined` inside mountMacro()/
    mountStandalone() before the panel ever rendered, so the entire alert-prefs
    surface this PR ships was unreachable at runtime in both its real deployment
    contexts. `node --check` and every existing JS-source-string test passed clean,
    because a reference to an undeclared identifier is a RUNTIME ReferenceError, not
    a parse-time error -- this is exactly the class of defect the frozen spec's
    required browser evidence matrix exists to catch that a no-browser-harness test
    suite cannot."""
    import re
    # word-boundary-anchored: a naive substring check for "el.addEventListener" also
    # matches "...pan[el.addEventListener]" inside `panel.addEventListener(...)`,
    # which is legitimate in every one of these functions -- only a BARE `el.`
    # reference (not preceded by an identifier character) is the defect.
    bare_el_re = re.compile(r"(?<![A-Za-z0-9_$.])el\.addEventListener")
    for fn_name in ("mountStandalone", "mountMacro"):
        start = account_js.index("function %s(" % fn_name)
        end = account_js.index("\n  }\n", start)
        body = account_js[start:end]
        assert not bare_el_re.search(body), (
            f"{fn_name} must not reference an undefined `el` -- it takes no `el` "
            f"parameter (only mountEmbed(el) legitimately does)"
        )
    # mountEmbed's own el.addEventListener calls are untouched and still legal.
    embed_start = account_js.index("function mountEmbed(el)")
    embed_end = account_js.index("\n  }\n", embed_start)
    embed_body = account_js[embed_start:embed_end]
    assert len(bare_el_re.findall(embed_body)) == 2


def test_coming_soon_string_removed_from_alert_group(account_js):
    # 'Coming soon' remains legal elsewhere (e.g. the plan card's Pro upsell), but the old
    # dead notifications group ('notifGroupHTML'/'notifRow') must be gone entirely.
    assert "notifGroupHTML" not in account_js
    assert "notifRow" not in account_js


_NEW_STR_KEYS = [
    "al_group", "al_master", "al_off", "al_unknown", "al_what", "al_cat_hold", "al_cat_thes",
    "al_none", "al_tz", "al_tz_unset", "al_qh", "al_qh_hint", "al_qh_s", "al_qh_e", "al_clear",
    "al_saved",
]


@pytest.mark.parametrize("key", _NEW_STR_KEYS)
def test_new_str_keys_have_non_empty_en_and_zh(account_js, key):
    import re
    m = re.search(re.escape(key) + r"\s*:\s*\[\s*(['\"])(.*?)\1\s*,\s*(['\"])(.*?)\3", account_js)
    assert m, f"STR key {key!r} not found"
    en, zh = m.group(2), m.group(4)
    assert en.strip() and zh.strip()


_MOVED_CSS_RULE_SIGNATURES = (
    ".mmacc-alerts{position:relative;padding-left:14px}",
    ".mmacc-alerts::before{",
    "button.mmacc-switch{",
    "button.mmacc-switch::after{",
    ".mmacc-switch-sm{",
    ".mmacc-alert-detail{",
    ':root[data-theme="light"] .mmacc-alerts{',
)


def test_alert_css_lives_in_theme_css_not_account_js(account_js):
    """B-F08-1a originally appended its ~25 alert-prefs CSS rules to the runtime
    `CSS` string in account.js -- a design-system bypass (governed CSS must own
    material styling, not a page composer's JS string). Meta-CEO B ruling moved
    them into templates/theme.css under a delimited block. This pins that they
    live there and ONLY there: account.js may still reference the class names as
    markup (e.g. `class="mmacc-alerts"`), but must carry no CSS rule BODY for
    them, and its createElement('style') count must stay at the pinned cap of 2
    (no third runtime style injection was added to compensate for the move)."""
    theme_css = (ROOT / "templates" / "theme.css").read_text()
    start_marker = "/* account sheet: alert delivery preferences (B-F08-1a) */"
    end_marker = "/* end account sheet: alert delivery preferences (B-F08-1a) */"
    assert start_marker in theme_css
    assert end_marker in theme_css
    moved_block = theme_css[theme_css.index(start_marker):theme_css.index(end_marker)]

    import re
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", moved_block), "no hex literal in the moved rules"

    for sig in _MOVED_CSS_RULE_SIGNATURES:
        assert sig in moved_block, f"{sig!r} missing from templates/theme.css"
        assert sig not in account_js, f"{sig!r} must not be styled from account.js anymore"

    assert account_js.count("createElement('style')") == 2


def test_every_switch_control_is_a_button(account_js):
    import re
    for m in re.finditer(r'role="switch"[^>]*', account_js):
        pass  # role appears inside a tag string; check the tag itself below
    assert 'class="mmacc-switch" role="switch"' not in account_js.replace(
        '<button type="button" class="mmacc-switch" role="switch"', "")
    assert '<span class="mmacc-switch" aria-disabled="true">' not in account_js


def test_no_title_attribute_emitted_by_alert_builder(account_js):
    start = account_js.index("function alertCatRow")
    end = account_js.index("function alertPrefsGroupHTML") + len("function alertPrefsGroupHTML")
    body_start = account_js.index("function alertPrefsGroupHTML")
    body_end = account_js.index("\n  function bodySignedIn")
    block = account_js[start:body_end]
    assert "title=" not in block


# --------------------------------------------------------------------------- #
# deployed artifact freshness
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not (ROOT / "site" / "account.js").exists()
                    or (ROOT / "site" / "account.js").stat().st_size == 0,
                    reason="needs_full_checkout")
def test_site_account_js_is_byte_identical_to_template():
    tpl = ROOT / "templates" / "account.js"
    site = ROOT / "site" / "account.js"
    assert tpl.read_bytes() == site.read_bytes()


# --------------------------------------------------------------------------- #
# template consumers tolerate the widened reader
# --------------------------------------------------------------------------- #
def test_read_user_prefs_returns_all_seven_keys():
    meta = {
        "lang": "en", "theme": "dark", "brain_depth": "concise",
        "alert_email_optin": True, "alert_categories": ["thesis_window"],
        "tz": "Asia/Hong_Kong", "quiet_hours": {"start": "22:00", "end": "07:00"},
    }
    out = user_prefs.read_user_prefs({"user_metadata": meta})
    assert set(out) == {
        "lang", "theme", "brain_depth", "alert_email_optin", "alert_categories",
        "tz", "quiet_hours",
    }


def test_pref_keys_starts_with_the_original_three():
    assert user_prefs.PREF_KEYS[:3] == ("lang", "theme", "brain_depth")


def test_quiet_hours_off_sentinel_reaches_the_put_as_none(auth, store):
    """A regression in validate_prefs/normalize_value that stopped converting the wire
    sentinel "off" would previously go undetected with a green suite -- every existing
    "off" test asserted only the route's response out["prefs"], never the actual PUT
    body sent to GoTrue. Assert the real network payload instead."""
    account_prefs.save_prefs(account_prefs.PrefsRequest(quiet_hours="off"), user=USER)
    _, _, payload = auth.calls[0]
    meta = payload["user_metadata"]
    assert meta["quiet_hours"] is None
    assert meta["quiet_hours"] != "off"


def test_alerts_on_with_no_tz_defaults_and_round_trips_on_get(auth, store):
    """B-F08-1a freeze §8 + Meta-CEO B ruling (macro#6907, round 2): turning alerts on
    with no tz supplied must not leave the account's alert delivery window undefined.
    The server applies default_tz_for_lang(lang) server-side (never a client-side
    guess) and the same value round-trips on the next GET -- named by the prior
    review round as a required test that was missing."""
    base_user = dict(USER, user_metadata=dict(USER["user_metadata"]))
    assert "tz" not in base_user["user_metadata"]  # fresh account, tz never touched

    out = account_prefs.save_prefs(
        account_prefs.PrefsRequest(alert_email_optin=True), user=base_user)
    assert out["prefs"]["tz"] == user_prefs.default_tz_for_lang("en") == "UTC"

    _, _, payload = auth.calls[0]
    meta = payload["user_metadata"]
    assert meta["tz"] == "UTC"
    assert meta["alert_email_optin"] is True

    # GET reads directly off the account record (no network, per read_prefs'
    # docstring) -- build the post-write record the way the real auth layer would
    # return it after the PUT above actually merged, then round-trip through it.
    after_user = dict(base_user, user_metadata=dict(base_user["user_metadata"], **meta))
    got = account_prefs.read_prefs(user=after_user)
    assert got["prefs"]["tz"] == "UTC"
    assert "tz" not in got["unset"]


def test_alerts_on_never_overwrites_an_existing_tz(auth, store):
    """The default only fills a genuinely unset tz -- it must never clobber a zone the
    account already has, including when the same call turns alerts on."""
    base_user = dict(USER, user_metadata=dict(USER["user_metadata"], tz="Asia/Hong_Kong"))
    account_prefs.save_prefs(
        account_prefs.PrefsRequest(alert_email_optin=True), user=base_user)
    _, _, payload = auth.calls[0]
    assert payload["user_metadata"]["tz"] == "Asia/Hong_Kong"


def test_get_prefs_unauthenticated_is_401(monkeypatch):
    from fastapi import HTTPException

    def _deny(authorization=None):
        raise HTTPException(401, "missing bearer token")

    monkeypatch.setattr(account_prefs, "_current_user", _deny)
    with pytest.raises(HTTPException) as ei:
        account_prefs.read_prefs(user=account_prefs._current_user(None))
    assert ei.value.status_code == 401
