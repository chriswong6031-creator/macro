"""tests/test_theme_hash_deeplink.py
====================================
Guards the ``#theme-<id>`` deep-link contract, US receiving side + emitters.

The alerts board (engine/alert_triage.py SOURCES joins ``page`` + each event's
``anchor``) and engine/theme_alerts.py emit ``#theme-<id>`` deep links; alert
rows live ~90 days and bookmarks longer. The emitting engines are covered by
tests/test_sector_pulse_wiring.py and tests/test_theme_alerts.py; this file
covers the *receiving* side, which regressed silently twice:

* The 2026-07 revamp (#3282) removed the US page's ``#theme-<id>`` elements but
  left the boot handler calling ``openTheme()``, which returned early — every
  inbound link landed and silently did nothing, for months. #4254 fixed it with
  ``resolveThemeHash()``: validate the id, then ``location.replace()`` to
  ``basket/<id>.html``.
* The Sector Intelligence consolidation (#4237) turned baskets.html.j2 into a
  redirect stub whose hard-coded ``location.replace("…#actnow-section")`` ATE
  inbound hashes, and its merged-page handler hopped through an unguarded
  ``location.href`` — the same silent failure plus a Back-trap and a 404 path
  for retired ids. This suite was in no CI pack, so main stayed green.

The contract now has three US pieces, and all must hold:
  * the baskets.html stub FORWARDS ``#theme-<id>`` hashes to the merged page
    (non-theme traffic keeps the designed #actnow-section landing, which
    tests/test_sector_intelligence_page.py pins);
  * sector_central.html resolves the hash by navigating to ``basket/<id>.html``
    — it renders no ``#theme-<id>`` elements, so scrolling is not an option;
  * the alerts board emits theme links against the merged page directly, not
    the stub.
The china/hk/canada/intl pages still render ``.tcard`` elements with
``id="theme-<id>"`` and must keep routing through the shared ``openTheme()`` —
so nobody "cleans up" the shared function on the strength of the US pages no
longer calling it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "templates"

US_STUB = TEMPLATES / "baskets.html.j2"
US_MERGED = TEMPLATES / "sector_central.html.j2"
TRIAGE = REPO / "engine" / "alert_triage.py"
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
# US stub — legacy baskets.html#theme-<id> links must keep resolving
# ---------------------------------------------------------------------------

class TestUSStubForwardsThemeHash:

    def test_stub_forwards_the_theme_hash_to_the_merged_page(self):
        src = _src(US_STUB)
        assert "location.hash.startsWith('#theme-')" in src, (
            "the baskets.html stub no longer inspects the hash — inbound "
            "baskets.html#theme-<id> links (90d alert rows, bookmarks) get their "
            "hash eaten by the hard-coded #actnow-section redirect again"
        )
        assert "location.replace('sector_central.html'+location.hash)" in src, (
            "the stub must forward the #theme-<id> hash verbatim to the merged "
            "page, whose resolveThemeHash() routes it to basket/<id>.html"
        )

    def test_stub_redirects_only_via_replace(self):
        """href would trap Back: it returns to the stub, which redirects forward again."""
        src = _src(US_STUB)
        assert "location.href" not in src
        # the non-theme fallback stays on the designed landing (also pinned by
        # tests/test_sector_intelligence_page.py::test_redirect_stub)
        assert 'location.replace("sector_central.html#actnow-section")' in src


# ---------------------------------------------------------------------------
# Merged US page — the hash must resolve to the theme's own page
# ---------------------------------------------------------------------------

class TestUSPageResolvesToDetailPage:

    def test_boot_handler_routes_the_hash_through_the_resolver(self):
        """The merged page has no #theme-<id> elements, so openTheme()-style
        scroll handling is a no-op here; the handler must call the resolver."""
        src = _src(US_MERGED)
        handler = re.search(
            r"if\s*\(\s*location\.hash\.startsWith\('#theme-'\)\s*\)(.*)", src
        )
        assert handler, "merged page lost its #theme- hash handler entirely"
        body = handler.group(1)
        assert "openTheme" not in body, (
            "merged-page boot handler routes the hash through openTheme(); the "
            "consolidated page renders no #theme-<id> elements, so inbound "
            "#theme-<id> links would silently fail again"
        )
        assert "resolveThemeHash" in body

    def test_resolver_navigates_to_the_basket_detail_page(self):
        src = _src(US_MERGED)
        fn = re.search(r"function resolveThemeHash\(\)\{(.*?)\n\}", src, re.S)
        assert fn, "resolveThemeHash() missing from the merged US template"
        body = fn.group(1)
        assert "basket/" in body and ".html" in body, (
            "resolveThemeHash() must send the visitor to basket/<id>.html"
        )
        assert f"location.hash.slice({_HASH_PREFIX_LEN})" in body, (
            "resolver must strip exactly the '#theme-' prefix"
        )

    def test_resolver_uses_replace_not_href(self):
        """href would trap Back: it returns to #theme-<id>, which redirects forward again."""
        src = _src(US_MERGED)
        fn = re.search(r"function resolveThemeHash\(\)\{(.*?)\n\}", src, re.S)
        body = fn.group(1)
        assert "location.replace(" in body, (
            "use location.replace() so Back returns to the referring alert, "
            "not into a redirect loop"
        )
        assert "location.href" not in body

    def test_resolver_guards_on_a_known_theme(self):
        """An unknown id must stay put rather than redirect into a 404."""
        src = _src(US_MERGED)
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
# Emitting side — the alerts board links theme events to the merged page
# ---------------------------------------------------------------------------

class TestThemeAlertsEmitCanonicalPage:

    def test_themes_stream_targets_the_page_that_carries_the_resolver(self):
        """alert_triage joins SOURCES[...]["page"] + the event's #theme-<id> anchor.

        baskets.html is a redirect stub since #4237 — pointing fresh alert rows at
        it mints an extra hop through the stub forward forever. New emissions go
        straight to the page whose resolveThemeHash() owns the hash.
        """
        src = _src(TRIAGE)
        assert re.search(
            r'"themes":\s*\{[^}]*"page":\s*"sector_central\.html"', src
        ), (
            'SOURCES["themes"]["page"] must be sector_central.html — the merged '
            "page carrying resolveThemeHash() — not the baskets.html stub"
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
