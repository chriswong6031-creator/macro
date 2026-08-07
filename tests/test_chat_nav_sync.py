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

WHY THE STAMP TESTS ARE ABOUT --fix AND NOT ABOUT THE COMPARATOR (#4774): the
guard normalizes ``?v=`` stamps and ``defer`` away before comparing, correctly —
they are scripts/optimize_assets.py's to own. But ``--fix`` spliced in the RAW
canonical block, which wears neither, so the documented remedy for a nav drift
also stripped every stamp and every defer from both copies of the pair. Nothing
caught it: it rewrote the two copies identically, so check_template_site_sync saw
no divergence, and the selftest only ever proved the CHECK tolerates a stamp.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape

from scripts.sync_chat_nav import (
    check,
    decorations,
    extract_nav,
    lost_decorations,
    normalize,
    redecorate,
    render_canonical,
    selftest,
)

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


def test_every_decoration_on_the_shipped_header_survives_a_re_splice() -> None:
    """--fix must carry the optimizer's stamps and defer onto the new block.

    Asserted against the REAL committed header rather than a fixture, because the
    2026-08-06 measurement is what makes this concrete: re-splicing chat.html
    dropped 5 ``?v=`` stamps and 4 ``defer`` attributes, live.js and live_config.js
    among them — and app/deploy/Caddyfile's ``@public_versioned`` matcher requires
    BOTH the path and a ``?v=`` query, so a stripped stamp silently demotes the
    asset from ``immutable, max-age=1y`` to a 300s revalidate on every navigation.
    """
    current = extract_nav(PAGES[0].read_text(encoding="utf-8"), "templates/chat.html")
    stamps, deferred = decorations(current)
    assert stamps and deferred, (
        f"templates/chat.html's header carries {len(stamps)} stamp(s) and "
        f"{len(deferred)} defer(s) — with neither, this test asserts nothing. "
        "Either the page shipped un-optimized or decorations() stopped reading it."
    )

    spliced = redecorate(render_canonical(TEMPLATES), current)
    assert not lost_decorations(current, spliced), lost_decorations(current, spliced)

    after_stamps, after_defer = decorations(spliced)
    assert {u: h for u, h in stamps.items() if u in after_stamps} == after_stamps
    assert deferred <= after_defer


def test_the_re_splice_adds_only_stamps_and_defer() -> None:
    """Re-decorating may not change the markup the comparator actually compares.

    Otherwise --fix writes a page the very next check calls drifted — the "not a
    fixed point" failure the selftest's second assertion has always guarded, now
    reachable through the decoration pass rather than through the splice.
    """
    current = extract_nav(PAGES[0].read_text(encoding="utf-8"), "templates/chat.html")
    canonical = render_canonical(TEMPLATES)
    assert normalize(redecorate(canonical, current)) == normalize(canonical)


def test_lost_decorations_reports_a_stripped_stamp_and_a_stripped_defer() -> None:
    """Guard the guard: the fail-closed audit must SEE the pre-#4774 write.

    ``lost_decorations`` is the only thing standing between a future
    ``redecorate`` regression and a silent re-strip, so pin it on the exact shape
    it exists to refuse — the raw canonical block, spliced in undecorated.
    """
    current = ('<nav class="site-nav">'
               '<link rel="stylesheet" href="navigation-refresh.css?v=95f6bacd">'
               '<script src="live.js?v=e19f6af3" defer></script></nav>')
    raw = ('<nav class="site-nav">'
           '<link rel="stylesheet" href="navigation-refresh.css">'
           '<script src="live.js"></script></nav>')

    lost = lost_decorations(current, raw)
    assert any("navigation-refresh.css" in m and "95f6bacd" in m for m in lost), lost
    assert any("live.js" in m and "defer" in m for m in lost), lost

    # ...and an asset the partial REMOVED is not a loss — its ref left with it.
    assert lost_decorations(current, '<nav class="site-nav"></nav>') == []


def test_redecorate_keys_on_the_asset_not_the_line() -> None:
    """The carry must survive the very edits --fix exists to make.

    A menu link landing above the script block, or the partial reordering its own
    header, moves every decorated line. Keying on position would drop the stamps
    exactly when a real nav edit is being applied — the case that produced #4774.
    """
    current = ('<nav class="site-nav">'
               '<script src="live.js?v=e19f6af3" defer></script>'
               '<link rel="stylesheet" href="navigation-refresh.css?v=95f6bacd"></nav>')
    reordered = ('<nav class="site-nav"><a href="new_page.html">New</a>'
                 '<link rel="stylesheet" href="navigation-refresh.css">'
                 '<script src="live.js"></script></nav>')

    out = redecorate(reordered, current)
    assert 'href="navigation-refresh.css?v=95f6bacd"' in out
    assert 'src="live.js?v=e19f6af3"' in out and "defer" in out
    assert 'href="new_page.html"' in out, "the real nav edit must still land"
    assert not lost_decorations(current, out)


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
