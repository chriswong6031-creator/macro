"""Visitor-facing pages share the anonymous landing page's header and footer."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup


ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"


def _t(en: str, zh: str = "") -> Markup:
    return Markup(en)


def _render_partial(name: str, rel: str = "") -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=False)
    return env.get_template(name).render(rel=rel, t=_t)


def _block(html: str, tag: str, class_name: str) -> str:
    if class_name:
        pattern = (
            rf'<{tag}\b[^>]*class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>'
            rf".*?</{tag}>"
        )
    else:
        pattern = rf"<{tag}\b[^>]*>.*?</{tag}>"
    match = re.search(pattern, html, flags=re.DOTALL)
    assert match, f"missing {tag}.{class_name}"
    return match.group(0)


def _anchors(html: str) -> Counter[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for href, body in re.findall(
        r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.DOTALL
    ):
        text = re.sub(r"<[^>]+>", "", body)
        text = " ".join(text.split())
        if href.startswith("#"):
            href = "index.html" + href
        pairs.append((href, text))
    return Counter(pairs)


def test_shared_public_nav_matches_landing_core_information_architecture():
    landing = (TEMPLATES / "index.html").read_text(encoding="utf-8")
    landing_hrefs = {href for href, _label in _anchors(_block(landing, "nav", "nav"))}
    shared_hrefs = {
        href
        for href, _label in _anchors(
            _block(_render_partial("_public_nav.html.j2"), "nav", "public-nav")
        )
    }
    core = {
        "products/index.html",
        "research/index.html",
        "tools/index.html",
        "plans.html",
    }
    assert core <= landing_hrefs
    assert core <= shared_hrefs
    # The homepage expands those destinations into useful mega-menu links;
    # interior public pages keep a compact, server-rendered subset.
    assert shared_hrefs <= landing_hrefs
    assert not any("#" in href for href in shared_hrefs)


def test_shared_public_footer_matches_landing_information_architecture():
    landing = (TEMPLATES / "index.html").read_text(encoding="utf-8")
    expected = _anchors(_block(landing, "footer", ""))
    actual = _anchors(
        _block(_render_partial("_public_footer.html.j2"), "footer", "public-footer")
    )
    assert actual == expected


def test_visitor_templates_use_public_chrome_not_member_navigation():
    names = (
        "seo_base.html.j2",
        "plans.html.j2",
        "support.html.j2",
        "unsubscribe.html.j2",
    )
    for name in names:
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        assert '{% include "_public_nav.html.j2" %}' in text, name
        assert '{% include "_public_footer.html.j2" %}' in text, name
        assert "_site_nav.html.j2" not in text, name
        assert "_navlinks.html.j2" not in text, name


def test_all_committed_free_estate_pages_have_public_chrome():
    from scripts.build_free_content import _URL_MAP

    pages = sorted(path for path in _URL_MAP if path.endswith(".html"))
    assert pages
    for url_path in pages:
        output = SITE / url_path.lstrip("/")
        assert output.exists(), url_path
        text = output.read_text(encoding="utf-8")
        assert '<nav class="public-nav"' in text, url_path
        assert '<footer class="public-footer">' in text, url_path
        assert 'class="est-bar"' not in text, url_path
        assert 'class="est-footer"' not in text, url_path


def test_other_public_visitor_pages_have_public_chrome():
    for name in ("plans.html", "support.html", "unsubscribe.html"):
        text = (SITE / name).read_text(encoding="utf-8")
        assert '<nav class="public-nav"' in text, name
        assert '<footer class="public-footer">' in text, name
        assert '<nav class="site-nav"' not in text, name
