"""Consolidated AI Daily Brief page (aibrief.html) render + nav-cleanup regression.

The old deterministic daily brief (scripts/daily_brief.py -> brief.html, plus the
china/hk variants) was retired and replaced by ONE static page that surfaces the
three EXISTING AI briefs written by engine/master_brain.py
(master_brief.json / china_brief.json / btc_brief.json) as toggle tabs, rendered
client-side by templates/aibrief.js. The "📰 Brief" nav-link was moved out of the
scrolling menu into a static "AI Daily Brief" button in the .nav-ctrls cluster.

These tests render the REAL template (same Jinja env as scripts/build_aibrief) and
guard, at the source level, that no template ever re-links the deleted brief pages.
"""
from __future__ import annotations

import jinja2

from engine import i18n
from lib import config


def _env() -> jinja2.Environment:
    """Mirror scripts/build_aibrief.main()'s template environment."""
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(config.ROOT / "templates"))
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env


def _render() -> str:
    return _env().get_template("aibrief.html.j2").render(as_of="2026-06-14 12:00 UTC")


def test_three_brief_panels_present():
    """One .ai-brief panel per lens, each wired to its master_brain JSON."""
    html = _render()
    assert 'data-brief-src="master_brief.json"' in html
    assert 'data-brief-src="china_brief.json"' in html
    assert 'data-brief-src="btc_brief.json"' in html
    assert html.count("ai-brief") >= 3
    assert html.count("data-brief-body") == 3


def test_toggle_tabs_present():
    """Three market toggle buttons, one per lens."""
    html = _render()
    assert 'data-lens="macro"' in html
    assert 'data-lens="china"' in html
    assert 'data-lens="btc"' in html
    assert "Macro" in html and "China" in html and "Bitcoin" in html
    # exactly one panel is active by default (class-driven visibility)
    assert html.count("brief-tab active") == 1


def test_required_assets_loaded():
    """The page is fully client-rendered — it needs theme.css/.js + aibrief.js."""
    html = _render()
    assert 'href="theme.css"' in html
    assert 'src="theme.js"' in html
    assert 'src="aibrief.js"' in html


def test_static_nav_button_present():
    """The renamed 'AI Daily Brief' entry lives in the nav-ctrls cluster."""
    html = _render()
    assert "AI Daily Brief" in html
    assert 'class="ai-brief-link' in html
    assert 'class="nav-ctrls"' in html


def test_page_does_not_link_old_brief_pages():
    """The new page must not reference the retired brief HTML files. NOTE: the exact
    href= form matters — 'aibrief.html' contains the substring 'brief.html'."""
    html = _render()
    assert 'href="brief.html"' not in html
    assert 'href="china_brief.html"' not in html
    assert 'href="hk_brief.html"' not in html
    assert 'href="https://bot.mastermind-x.com"' in html  # the nav AI entry points to the external Mastermind bot


def test_no_template_links_deleted_brief_pages():
    """Source-level guard across EVERY template: the deterministic brief pages are
    gone, so nothing may link brief.html / china_brief.html / hk_brief.html (in any
    relative form). Locks in the nav cleanup against future drift."""
    bad = ('href="brief.html"', 'href="../brief.html"',
           'href="china_brief.html"', 'href="../china_brief.html"',
           'href="hk_brief.html"', 'href="../hk_brief.html"')
    offenders = []
    for path in sorted((config.ROOT / "templates").glob("*.html.j2")):
        src = path.read_text()
        for needle in bad:
            if needle in src:
                offenders.append(f"{path.name}: {needle}")
    assert not offenders, "templates still link retired brief pages: " + "; ".join(offenders)
