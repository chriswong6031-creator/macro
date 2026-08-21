"""tests/test_shared_pref_atomics.py — the cross-product shared-preference contract (E6).

`user_metadata.prefs` is a NESTED object, and supabase `auth.updateUser` REPLACES a nested
object wholesale. TWO browsers write it — this dashboard (templates/theme.js) and the
Mastermind Terminal (terminal/lib/accountPrefs.ts) — so each one's write silently discarded
whatever the other had changed since it last read:

    1. Terminal reads  {theme: dark, lang: en}
    2. here: the user picks Light  -> we write the WHOLE object
    3. Terminal, still holding its snapshot, changes language to Chinese
    4. Terminal sends {theme: dark, lang: zh}
    5. the Light choice from step 2 is gone.

Serializing either product's own writes cannot fix that — the race is BETWEEN the products —
and a fresh-read-before-write only shrinks the window, because read and write are not atomic.

The repair removes the shared container: each field is its own TOP-LEVEL key, and top-level
keys MERGE. This module pins the JS side of that as a source contract, the same way
tests/test_canada_build.py asserts on templates/theme.js text: there is no browser harness in
this repo, and a silent regression here is invisible until two live products disagree.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

THEME_JS = Path(__file__).resolve().parent.parent / "templates" / "theme.js"


@pytest.fixture(scope="module")
def src() -> str:
    return THEME_JS.read_text(encoding="utf-8")


def _save_pref_fn(src: str) -> str:
    """The body of `_savePrefToServer`, up to the next top-level comment block."""
    start = src.index("function _savePrefToServer(")
    end = src.index("/* Hook into theme/lang events", start)
    return src[start:end]


def test_the_writer_never_sends_the_nested_prefs_blob(src: str) -> None:
    """The whole point. A writer that sends `prefs` clobbers the other product's field."""
    body = _save_pref_fn(src)
    assert "data: { prefs" not in body
    assert "prefs: prefs" not in body
    assert re.search(r"\bpatch\.prefs\b", body) is None


def test_the_writer_sends_top_level_atomics(src: str) -> None:
    body = _save_pref_fn(src)
    assert "patch.theme =" in body
    assert "patch.theme_auto =" in body
    assert "patch.lang =" in body
    assert "updateUser({ data: data })" in body


def test_a_language_change_carries_only_the_language(src: str) -> None:
    """The restraint IS the fix: a lang write that also carried a stale theme would still
    lose the other product's newer theme, atomics or not."""
    body = _save_pref_fn(src)
    lang_branch = body[body.index("else if (which === 'lang')"):]
    assert "patch.lang" in lang_branch
    assert "patch.theme" not in lang_branch


def test_each_event_names_the_field_it_changed(src: str) -> None:
    assert "'themechange', function () { _savePrefToServer('theme'); }" in src
    assert "'langchange', function () { _savePrefToServer('lang'); }" in src


def test_the_reader_falls_back_per_field_not_per_blob(src: str) -> None:
    """A half-migrated account is the NORMAL state during the rollout: an account may have a
    v2 `lang` and only a legacy `prefs.theme`. A per-blob fallback reads one of them wrong."""
    fn = src[src.index("function _sharedPref("):src.index("function _isTheme(")]
    assert "meta[atomicKey]" in fn
    assert "legacy[legacyKey]" in fn
    # the atomic is preferred, and the legacy value is only consulted after it fails validation
    assert fn.index("meta[atomicKey]") < fn.index("legacy[legacyKey]")


def test_the_reader_resolves_all_three_shared_fields(src: str) -> None:
    apply_fn = src[src.index("function _applyServerPrefs("):src.index("/* Save ONLY the atomics")]
    assert "_sharedPref(meta, 'theme', 'theme', _isTheme)" in apply_fn
    assert "_sharedPref(meta, 'theme_auto', 'themeAuto', _isFlag)" in apply_fn
    assert "_sharedPref(meta, 'lang', 'lang', _isLang)" in apply_fn


def test_the_atomic_names_match_the_servers_own_vocabulary(src: str) -> None:
    """`theme` and `lang` are not new names — lib/user_prefs.py already calls them canonical
    and app/account_prefs.py already writes them. A parallel `ui_*` namespace would have made
    a THIRD representation of one preference."""
    from lib import user_prefs

    assert "lang" in user_prefs.PREF_VALUES
    assert "theme" in user_prefs.PREF_VALUES
    assert set(user_prefs.PREF_VALUES["theme"]) == {"light", "dark"}
    assert set(user_prefs.PREF_VALUES["lang"]) == {"en", "zh"}
    assert "ui_theme" not in src and "ui_lang" not in src


def test_theme_auto_is_browser_only_and_stays_out_of_the_route_vocabulary(src: str) -> None:
    """It is a presentation flag (the dashboard computes the theme from local time when it is
    set), not a server-stored preference — adding it to PREF_VALUES would widen the chat tool's
    write surface for nothing."""
    from lib import user_prefs

    assert "theme_auto" in src
    assert "theme_auto" not in user_prefs.PREF_VALUES
