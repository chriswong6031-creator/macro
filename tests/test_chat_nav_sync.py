"""chat.html's header is GENERATED from the canonical partial, and stays that way.

Companion to tests/test_product_chrome.py. That module guards the 113 product
templates that can ``{% include %}`` the shared header; this one guards the
114th. templates/chat.html is a plain-copy page — check_template_site_sync
requires it to byte-match site/chat.html, so Jinja cannot run there and #4228's
sweep had to leave it hand-copied.

Hand-copied is precisely what rotted. Measured on 2026-08-01, chat.html's menu
was missing 12 live pages and still advertised 17 that had been removed — 17
dead links in a shipped navigation — and it styled them with a bespoke
``chat_nav.css`` frozen against a mega-menu structure the partial stopped
emitting. scripts/sync_chat_nav.py replaced the hand-copying with a render, and
these tests are what keep a future edit to _navlinks.html.j2 from silently
re-opening the gap.

WHY THE HREF PARITY TEST IS SET-BASED AND BIDIRECTIONAL: the failure had both
shapes at once. A one-way check ("every link on the page is real") would have
passed the 12 missing pages, and the other one-way check would have passed the
17 dead ones. Only the symmetric difference sees both.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape

from scripts.sync_chat_nav import check, extract_nav, render_canonical, selftest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
PAGES = (ROOT / "templates" / "chat.html", ROOT / "site" / "chat.html")


def _t(en: str, zh: str = "") -> Markup:
    return Markup(
        f'<span class="l-en">{escape(en)}</span>'
        f'<span class="l-zh">{escape(zh or en)}</span>'
    )


def _menu_hrefs(html: str) -> set[str]:
    """Internal page links inside the <div class="nav-links"> menu."""
    m = re.search(r'<div class="nav-links">.*?\n  </div>', html, re.DOTALL)
    assert m, "no <div class=\"nav-links\"> menu found"
    return {
        h for h in re.findall(r'href="([^"]+)"', m.group(0))
        if not h.startswith(("http://", "https://", "javascript:", "#"))
    }


def test_chat_header_matches_the_canonical_partial() -> None:
    """The committed page agrees with a fresh render of _site_nav.html.j2."""
    assert check(ROOT), (
        "templates/chat.html's header has drifted from _site_nav.html.j2. It is "
        "generated — edit the partial, then run: "
        "python -m scripts.sync_chat_nav --fix"
    )


def test_the_gate_fires_on_drift() -> None:
    """Guard the guard.

    Without this the splice could stop matching — a renamed wrapper, a changed
    regex — and the test above would report green over a page nothing checks.
    The selftest hand-edits a link into a fixture copy and requires a red.
    """
    assert selftest() == 0


@pytest.mark.parametrize("page", PAGES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_menu_matches_navlinks_in_both_directions(page: Path) -> None:
    """No page the menu omits, and no link the site no longer has.

    Asserted on BOTH copies of the pair: the template is what regenerates, the
    site copy is what actually ships, and a lane that heals one without the
    other is the documented failure mode this pair keeps hitting.
    """
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    canonical = _menu_hrefs(env.get_template("_navlinks.html.j2").render(t=_t))
    shipped = _menu_hrefs(page.read_text(encoding="utf-8"))

    missing = sorted(canonical - shipped)
    dead = sorted(shipped - canonical)
    assert not missing, (
        f"{page.parent.name}/{page.name}'s menu omits live pages: {missing}. "
        "Run: python -m scripts.sync_chat_nav --fix"
    )
    assert not dead, (
        f"{page.parent.name}/{page.name}'s menu links pages the site no longer "
        f"has: {dead}. Run: python -m scripts.sync_chat_nav --fix"
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_nav_appearance_comes_from_the_shared_stylesheet(page: Path) -> None:
    """CLAUDE.md's Navigation source-of-truth law, pinned on the shipped bytes.

    navigation-refresh.css owns nav appearance for the product family. chat.html
    used to override it with chat_nav.css, which is why its menu could look
    right while being structurally a generation behind — that sheet is deleted
    and must not come back.
    """
    text = page.read_text(encoding="utf-8")
    assert "navigation-refresh.css" in text, (
        f"{page.name} no longer links navigation-refresh.css, the stylesheet "
        "that owns nav appearance for every product page"
    )
    assert "chat_nav.css" not in text, (
        f"{page.name} links chat_nav.css again. That sheet was a frozen fork of "
        "navigation-refresh.css's mega-menu rules, styling markup the shared "
        "partial no longer emits; page-local nav CSS is how this drifted."
    )


def test_the_header_is_the_whole_shared_chrome() -> None:
    """Taking the menu means taking the search box and controls with it.

    Mirrors test_product_chrome.test_every_product_page_takes_the_whole_header
    for the one page that reaches the partial by render rather than by include.
    """
    nav = extract_nav(PAGES[1].read_text(encoding="utf-8"), "site/chat.html")
    for needle, what in (
        ('class="nav-search"', "the search box"),
        ("product-icon-terminal", "the Terminal link"),
        ('class="theme-switch"', "the dark/light toggle"),
        ('class="lang-toggle"', "the EN/中文 toggle"),
        ('class="nav-brand"', "the brand logomark"),
    ):
        assert needle in nav, f"site/chat.html's header lost {what}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_the_data_base_shim_survives_the_splice(page: Path) -> None:
    """chat.html is exempt from the write_page guard, so check what it protects.

    scripts/sync_chat_nav.py is listed in tests/test_site_shim._ALLOW because
    write_page would inject the shim into a source file and break the pair's
    byte-match. That exemption is only safe while the shim is actually still
    there — without the R2 reroute the page's per-ticker fetches hit the
    protected HTML origin and 401.
    """
    text = page.read_text(encoding="utf-8")
    assert text.count("data-dbase") == 1, (
        f"{page.parent.name}/{page.name} should carry exactly one data-base shim "
        f"tag, found {text.count('data-dbase')}"
    )


def test_rendered_header_is_bilingual() -> None:
    """The generator must not ship the English-only t() stub.

    _site_nav.html.j2 reads ``t`` from the page context, so a generator that
    passed tests' ``Markup(en)`` helper would render a header with no Chinese at
    all — and every assertion above would still pass.
    """
    html = render_canonical(TEMPLATES)
    assert '<span class="l-zh">终端</span>' in html, (
        "the Terminal control rendered without its Chinese label — "
        "scripts.sync_chat_nav.render_canonical is passing an English-only t()"
    )
