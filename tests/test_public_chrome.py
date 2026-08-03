"""Visitor-facing pages share the anonymous landing page's header and footer."""
from __future__ import annotations

import re
from collections import Counter
from html import unescape
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
        # Compare what a READER sees, not the escaping. The landing is plain HTML
        # (so it carries a literal "&amp;"), while the shared partial goes through
        # Jinja with autoescape ON in the real builder — there, a source "&amp;"
        # becomes "&amp;amp;" and the footer link literally read "Plans &amp;
        # pricing" on every public page. _render_partial below renders with
        # autoescape OFF, so this test could never see that; normalising both
        # sides keeps it honest about the information architecture it exists to
        # guard, and stops it pinning one side's escaping.
        text = unescape(text)
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
        "tools/index.html",
        "plans.html",
    }
    assert core <= landing_hrefs
    assert core <= shared_hrefs
    # Every public tool/product page now carries the same conversion menu as the
    # homepage, including the three-summary Vault preview.
    assert "https://www.mastermind-x.com/research_vault.html" in landing_hrefs
    assert "https://www.mastermind-x.com/research_vault.html" in shared_hrefs
    # The shared research menu can carry a small number of deep public research
    # destinations that do not need a duplicate landing-page hero card.
    shared_only = {"stocks/earnings/index.html"}
    assert shared_hrefs <= landing_hrefs | shared_only
    assert shared_only <= shared_hrefs
    shared = _render_partial("_public_nav.html.j2")
    for panel in ("public-platform-panel", "public-research-panel", "public-resources-panel"):
        assert f'id="{panel}"' in shared
    assert 'id="public-nav-toggle"' in shared
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
    """Every committed §1 page carries visitor chrome — in one of TWO families.

    Generator-rendered estate pages get the SHARED public chrome
    (_public_nav.html.j2 / _public_footer.html.j2 via seo_base), including the
    products/index.html hub.

    The hand-authored flagships (lib.pages.HAND_AUTHORED_PAGES) are landing-
    native chapters of index.html, so they carry the LANDING chrome instead:
    `<nav class="nav">` and the landing's BARE `<footer>` — landing.css styles
    the element itself, not a class — byte-copied from the landing down to the
    Platform / Research / Resources / Legal columns. That is a chrome FAMILY
    split, not a missing-chrome gap: both families ship the full legal column
    set (privacy, terms, disclaimer), verified on the committed bytes.

    Neither family is skipped. A flagship that silently lost its nav, its
    footer, or its breadcrumb still fails here, and the families are asserted
    EXCLUSIVE so a page drifting onto the other's chrome is caught too. The
    est-bar / est-footer prohibition is the superseded chrome and binds both.
    """
    from scripts.build_free_content import _URL_MAP, _is_hand_authored

    pages = sorted(path for path in _URL_MAP if path.endswith(".html"))
    assert pages
    landing_family: list[str] = []
    estate_family: list[str] = []
    for url_path in pages:
        output = SITE / url_path.lstrip("/")
        assert output.exists(), url_path
        text = output.read_text(encoding="utf-8")
        if _is_hand_authored(url_path):
            landing_family.append(url_path)
            assert '<nav class="nav"' in text, url_path
            assert "<footer>" in text, url_path
            assert "est-crumb" in text, url_path
            assert '<nav class="public-nav"' not in text, url_path
        else:
            estate_family.append(url_path)
            assert '<nav class="public-nav"' in text, url_path
            assert '<footer class="public-footer">' in text, url_path
        assert 'class="est-bar"' not in text, url_path
        assert 'class="est-footer"' not in text, url_path

    # Anti-vacuity: if either branch stopped matching, the other would grade
    # every page against the wrong contract — or against none at all.
    assert landing_family, "no hand-authored page checked — the carve-out went vacuous"
    assert estate_family, "no estate page checked — the carve-out swallowed everything"


def test_other_public_visitor_pages_have_public_chrome():
    for name in ("plans.html", "support.html", "unsubscribe.html"):
        text = (SITE / name).read_text(encoding="utf-8")
        assert '<nav class="public-nav"' in text, name
        assert '<footer class="public-footer">' in text, name
        assert '<nav class="site-nav"' not in text, name


def test_shared_public_header_geometry_matches_landing_header():
    landing_css = (TEMPLATES / "landing.css").read_text(encoding="utf-8")
    public_css = (TEMPLATES / "_public_chrome_css.html.j2").read_text(encoding="utf-8")
    assert "--maxw:1280px; --gutter:clamp(20px,4.5vw,60px)" in landing_css
    assert (
        ".nav-in{position:relative;max-width:var(--maxw);margin:0 auto;"
        "padding:0 var(--gutter);height:64px;display:flex;align-items:center;gap:24px}"
    ) in landing_css
    for marker in (
        "max-width:1280px",
        "padding:0 clamp(20px,4.5vw,60px)",
        "height:64px",
        "gap:24px",
        "min-height:40px",
        "padding:8px 12px",
        "border-radius:10px",
        "top:calc(100% + 12px)",
        "width:min(650px,calc(100vw - 40px))",
    ):
        assert marker in public_css
    assert (
        'font-family:Inter,-apple-system,BlinkMacSystemFont,"SF Pro Text",'
        '"SF Pro Display",system-ui'
    ) in public_css
    assert (
        "font-family:'Inter',-apple-system,BlinkMacSystemFont,'SF Pro Text',"
        "'SF Pro Display',system-ui"
    ) in landing_css


def test_agent_contract_names_only_the_two_canonical_navigation_families():
    for name in ("AGENTS.md", "CLAUDE.md"):
        source = (ROOT / name).read_text(encoding="utf-8")
        assert "Navigation source-of-truth" in source
        assert "templates/_site_nav.html.j2" in source
        assert "templates/_public_nav.html.j2" in source
        assert re.search(
            r"(Never create or locally resize a third page\s+header|"
            r"Do not hand-copy or restyle a third header)",
            source,
        )
