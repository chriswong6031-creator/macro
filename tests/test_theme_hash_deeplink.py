"""tests/test_theme_hash_deeplink.py
====================================
Guards the ``baskets.html#theme-<id>`` deep-link contract.

alerts.html rows, the dashboard sector-heat/cool chips and
``engine/theme_alerts.py`` anchors all emit ``baskets.html#theme-<id>``.
The emitting side is covered by tests/test_sector_pulse_wiring.py and
tests/test_theme_alerts.py; this file covers the *receiving* side, which
had no guard and regressed silently.

The 2026-07 revamp (#3282) replaced the US page's per-theme desk cards --
the only source of ``#theme-<id>`` elements -- with the verdict hero / act
board / rotation map, but left the boot handler calling ``openTheme()``.
``openTheme()`` returns early when ``#theme-<id>`` is absent, so every
inbound link landed on the page and silently did nothing, for months.

Two halves, and both must hold:
  * the US page resolves the hash by navigating to ``basket/<id>.html``
    (its rotation-board rows are filtered and capped at 10, so anchoring a
    row would resolve for only a subset of themes);
  * the china/hk/canada/intl pages, which DO render ``.tcard`` elements
    with ``id="theme-<id>"``, still route through the shared
    ``openTheme()`` -- so nobody "cleans up" the shared function on the
    strength of the US page no longer calling it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "templates"

US_TEMPLATE = TEMPLATES / "baskets.html.j2"
DESK_JS = TEMPLATES / "baskets_desk.js"
REGIONAL_TEMPLATES = [
    TEMPLATES / "baskets_china.html.j2",
    TEMPLATES / "baskets_hk.html.j2",
    TEMPLATES / "baskets_canada.html.j2",
    TEMPLATES / "baskets_intl.html.j2",
]

# '#theme-' is 7 characters; the handler slices the hash at that offset.
_HASH_PREFIX_LEN = len("#theme-")


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# US page — the hash must resolve to the theme's own page
# ---------------------------------------------------------------------------

class TestUSPageResolvesToDetailPage:

    def test_boot_handler_does_not_call_open_theme(self):
        """The US page has no #theme-<id> elements, so openTheme() is a no-op here."""
        src = _src(US_TEMPLATE)
        handler = re.search(
            r"if\s*\(\s*location\.hash\.startsWith\('#theme-'\)\s*\)(.*)", src
        )
        assert handler, "US page lost its #theme- hash handler entirely"
        body = handler.group(1)
        assert "openTheme" not in body, (
            "US boot handler calls openTheme(), which finds nothing on this page "
            "since #3282 removed the theme desk cards -- inbound #theme-<id> links "
            "would silently fail again"
        )
        assert "resolveThemeHash" in body

    def test_resolver_navigates_to_the_basket_detail_page(self):
        src = _src(US_TEMPLATE)
        fn = re.search(r"function resolveThemeHash\(\)\{(.*?)\n\}", src, re.S)
        assert fn, "resolveThemeHash() missing from the US template"
        body = fn.group(1)
        assert "basket/" in body and ".html" in body, (
            "resolveThemeHash() must send the visitor to basket/<id>.html"
        )
        assert f"location.hash.slice({_HASH_PREFIX_LEN})" in body, (
            "resolver must strip exactly the '#theme-' prefix"
        )

    def test_resolver_uses_replace_not_href(self):
        """href would trap Back: it returns to #theme-<id>, which redirects forward again."""
        src = _src(US_TEMPLATE)
        fn = re.search(r"function resolveThemeHash\(\)\{(.*?)\n\}", src, re.S)
        body = fn.group(1)
        assert "location.replace(" in body, (
            "use location.replace() so Back returns to the referring alert, "
            "not into a redirect loop"
        )

    def test_resolver_guards_on_a_known_theme(self):
        """An unknown id must stay put rather than redirect into a 404."""
        src = _src(US_TEMPLATE)
        fn = re.search(r"function resolveThemeHash\(\)\{(.*?)\n\}", src, re.S)
        body = fn.group(1)
        assert "themeById(" in body, (
            "resolveThemeHash() must validate the id against THEME.themes before "
            "navigating, or a stale link becomes a 404"
        )
        # the guard has to precede the navigation, not follow it
        assert body.index("themeById(") < body.index("location.replace("), (
            "the themeById() guard must run before the redirect"
        )


# ---------------------------------------------------------------------------
# Regional pages — openTheme() stays load-bearing
# ---------------------------------------------------------------------------

class TestRegionalPagesKeepOpenTheme:

    def test_shared_desk_js_still_defines_open_theme(self):
        src = _src(DESK_JS)
        assert "function openTheme(" in src, (
            "openTheme() is still the hash handler for the four regional pages; "
            "do not remove it because the US page stopped calling it"
        )

    def test_shared_desk_js_still_renders_theme_ids(self):
        """openTheme() is only meaningful while the desk renders id=theme-<id>."""
        src = _src(DESK_JS)
        assert 'id="theme-${t.id}"' in src, (
            "the shared desk renderer no longer emits id=\"theme-<id>\" -- "
            "openTheme() would be a no-op on the regional pages too"
        )

    @pytest.mark.parametrize(
        "template", REGIONAL_TEMPLATES, ids=lambda p: p.stem
    )
    def test_regional_boot_handler_still_calls_open_theme(self, template: Path):
        src = _src(template)
        handler = re.search(
            r"if\s*\(\s*location\.hash\.startsWith\('#theme-'\)\s*\)(.*)", src
        )
        assert handler, f"{template.name} lost its #theme- hash handler"
        assert "openTheme" in handler.group(1), (
            f"{template.name} renders .tcard id=\"theme-<id>\" elements and must "
            "keep routing the hash through openTheme()"
        )
