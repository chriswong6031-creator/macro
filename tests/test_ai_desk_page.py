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
    # cross-links to the sibling AI pages both exist (the "Mastermind" nav entry
    # points to the external bot; the AI Desk link stays local)
    assert 'href="https://bot.mastermind-x.com"' in html and 'href="ai_desk.html"' in html


def test_renderer_covers_the_key_surfaces():
    js = (TEMPLATES / "ai_desk.js").read_text()
    for token in ("ai_desk.json", "track_record", "theses", "falsifier",
                  "panel", "dissent", "check_by"):
        assert token in js, token
    assert "esc(" in js                              # model content is HTML-escaped


def test_builder_ships_the_renderer_asset():
    from scripts import build_ai_desk_page as b
    assert "ai_desk.js" in b.ASSETS and "theme.js" in b.ASSETS and "theme.css" in b.ASSETS
