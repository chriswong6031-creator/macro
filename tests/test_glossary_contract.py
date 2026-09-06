"""Rendered-page + wiring contract for the public glossary."""
from __future__ import annotations

import re

import yaml
from jinja2 import Environment, FileSystemLoader

from lib import config
from lib.glossary import BANNED_GLANCE_PATTERNS, BANNED_GLANCE_TOKENS, glossary_view_model
from lib.help_directory import HELP_LINKS

ROOT = config.ROOT


def _render() -> str:
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    vm = glossary_view_model(ROOT)
    return env.get_template("glossary.html.j2").render(generated_utc="2026-01-01 00:00", **vm)


def test_rendered_glossary_lists_every_term_in_both_languages():
    html = _render().replace("&amp;", "&")
    vm = glossary_view_model(ROOT)
    for domain in vm["domains"]:
        for term in domain["terms"]:
            assert term["name_en"] in html
            assert term["name_zh"] in html


def test_rendered_glossary_has_no_title_attributes_on_page_chrome():
    html = _render()
    start = html.index('<main class="gl-shell" id="glossary"')
    end = html.index("</main>", start)
    main = html[start:end]
    assert "title=" not in main


def test_rendered_glossary_uses_public_chrome_not_member_navigation():
    html = _render()
    assert '<nav class="public-nav"' in html
    assert '<footer class="public-footer">' in html
    assert "site-nav" not in html
    assert "_navlinks" not in html


def test_rendered_letter_rail_marks_empty_letters_disabled():
    html = _render()
    vm = glossary_view_model(ROOT)
    for letter in vm["letters"]:
        if letter["count"] == 0:
            frag_re = re.compile(
                r'<span class="gl-letter is-empty" data-letter="' + re.escape(letter["id"])
                + r'" aria-disabled="true">'
            )
            assert frag_re.search(html), letter["id"]


def test_rendered_glance_text_passes_the_banned_vocabulary_grep():
    site_path = config.site_dir() / "glossary.html"
    html = site_path.read_text(encoding="utf-8")
    for match in re.finditer(r'<p class="gl-(?:answer|why)">(.*?)</p>', html, re.S):
        text = re.sub(r"<[^>]+>", "", match.group(1))
        for pattern in BANNED_GLANCE_PATTERNS:
            assert not pattern.search(text), text
        for token in re.findall(r"[A-Za-z0-9_]+", text):
            assert token not in BANNED_GLANCE_TOKENS, token


def test_site_pair_matches_a_fresh_render_of_the_template(tmp_path):
    from scripts import build_public_pages
    build_public_pages.build(tmp_path)
    fresh = (tmp_path / "glossary.html").read_text(encoding="utf-8")
    site_path = config.site_dir() / "glossary.html"
    on_disk = site_path.read_text(encoding="utf-8")
    fresh_body = re.sub(r"<!--.*?-->", "", fresh, flags=re.S)
    on_disk_body = re.sub(r"<!--.*?-->", "", on_disk, flags=re.S)
    assert fresh_body == on_disk_body


def test_help_directory_lists_the_glossary():
    entry = next((e for e in HELP_LINKS if e.id == "glossary"), None)
    assert entry is not None
    assert entry.category == "research"
    assert entry.href == "glossary.html"


def test_public_nav_research_panel_links_to_glossary():
    nav = (ROOT / "templates" / "_public_nav.html.j2").read_text(encoding="utf-8")
    assert 'href="{{ rel }}glossary.html"' in nav


def test_public_render_fast_lane_covers_the_glossary():
    workflow = (ROOT / ".github" / "workflows" / "public-render.yml").read_text(encoding="utf-8")
    assert '"lib/glossary.py"' in workflow
    assert '"templates/glossary.html.j2"' in workflow


def test_glossary_template_declares_both_theme_treatments():
    tpl = (ROOT / "templates" / "glossary.html.j2").read_text(encoding="utf-8")
    assert "DARK TREATMENT" in tpl
    assert "LIGHT TREATMENT" in tpl
    for selector in (".gl-domain", ".gl-row:hover", ".gl-rail", ".gl-letter:hover"):
        assert f'html[data-theme="light"] {selector}' in tpl
