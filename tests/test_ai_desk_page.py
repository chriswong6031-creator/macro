"""AI Desk page (templates/ai_desk.html.j2 + ai_desk.js + scripts/build_ai_desk_page).

The page is client-rendered (ai_desk.js fetches ai_desk.json), so here we assert the
static chrome renders cleanly (nav, bilingual labels, the desk-root mount, the script
includes) with no unrendered Jinja, that the renderer covers the key surfaces (track
record, theses, falsifier, panel), and that the builder ships the renderer asset."""
from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


def _render():
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False)
    return env.get_template("ai_desk.html.j2").render(as_of="2026-06-15 12:00 UTC")


def test_page_renders_without_unrendered_jinja():
    html = _render()
    assert "{{" not in html and "{%" not in html and "{#" not in html


def test_page_has_chrome_and_mount_and_assets():
    html = _render()
    assert "AI Desk" in html and 'class="site-nav"' in html
    assert 'id="desk-root"' in html and 'data-src="ai_desk.json"' in html
    assert '<script src="theme.js">' in html and '<script src="ai_desk.js">' in html
    # bilingual: the t() macro must emit the zh label alongside the en one
    assert "AI交易台" in html and 'class="l-zh"' in html
    # The header is now the shared one (_site_nav.html.j2), whose only external
    # entry is Terminal. Two per-page pills were removed here on 2026-08-01:
    #   · "Mastermind" — theme.js injects mm_brain.js sitewide, which mounts its
    #     own bottom-right launcher, so the nav pill was a duplicate entry point.
    #   · "🖥️ AI Desk" — a self-link marked .active on the page it points at.
    # NOTE: dropping the self-link orphans nothing. ai_desk.html is absent from
    # _navlinks.html.j2 and site-wide exactly ONE page links to it — itself. It
    # was already unreachable from the navigation; the pill only ever said "you
    # are here". Giving it a real home in the menu is a product decision, not a
    # chrome fix.
    assert 'href="https://app.mastermind-x.com"' in html
    assert 'href="https://bot.mastermind-x.com"' not in html


def test_renderer_covers_the_key_surfaces():
    js = (TEMPLATES / "ai_desk.js").read_text()
    for token in ("ai_desk.json", "track_record", "theses", "falsifier",
                  "panel", "dissent", "check_by"):
        assert token in js, token
    assert "esc(" in js                              # model content is HTML-escaped


def test_builder_ships_the_renderer_asset():
    from scripts import build_ai_desk_page as b
    assert "ai_desk.js" in b.ASSETS and "theme.js" in b.ASSETS and "theme.css" in b.ASSETS
