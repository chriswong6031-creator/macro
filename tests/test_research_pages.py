"""Tests for the per-report SEO landing pages (RV programmatic SEO).

Guards the pieces that make the Google play work: stable/unique slugs, a paywalled
JSON-LD contract (isAccessibleForFree:false + hasPart), the teaser-not-full-summary
exposure, the public first-pages excerpt (present when supplied, absent when not,
and always OUTSIDE the gated part), the ?doc= funnel CTA, and a sitemap merge that
never eats other sections.
"""
from __future__ import annotations

import json
import re
from html import unescape

import pytest
from jinja2 import Environment, FileSystemLoader

from scripts import build_research_pages as rp

_ITEM = {
    "id": "marketdesk-abc123-71f35b",
    "title": "JPM US Market Intel | Morning Briefing",
    "institution": "J.P. Morgan",
    "side": "sell",
    "desk": "Equity Research",
    "published_at": "2026-07-24T10:08:48Z",
    "summary_points": ["**Teaserbullet** with the thesis.", "Secretbullettwo copy.", "Secretbulletthree copy."],
    "tags": ["Rates", "Equities"],
    "tickers": ["JPM", "SPX"],
    "pages": 12,
}


def _norm_render(item: dict, excerpt_paras: list[str] | None = None) -> str:
    env = Environment(loader=FileSystemLoader("templates"),
                      autoescape=True, trim_blocks=True, lstrip_blocks=True)
    n = rp._norm(item)
    canonical = f"{rp.CANONICAL_BASE}/research/x.html"
    md = f"{n['inst']} research. {n['teaser']}"
    return env.get_template("research_report.html.j2").render(
        n=n, canonical=canonical, meta_desc=md,
        jsonld_str=rp._jsonld(n, canonical, md), related=[],
        excerpt_paras=excerpt_paras or [], site_base=rp.CANONICAL_BASE)


# --- slugs -----------------------------------------------------------------
def test_slug_is_kebab_with_id_suffix():
    s = rp._slug(_ITEM["title"], _ITEM["id"], set())
    assert re.fullmatch(r"[a-z0-9-]+", s)
    assert s.endswith("71f35b")               # stable id suffix
    assert "jpm-us-market-intel" in s


def test_slug_map_unique_and_deterministic():
    items = [dict(_ITEM, id=f"x{i}-aaa{i:03d}", title="Same Title") for i in range(5)]
    a = rp.slug_map(items)
    b = rp.slug_map(items)
    assert a == b                              # deterministic
    assert len(set(a.values())) == 5           # unique despite identical titles


# --- paywalled JSON-LD + teaser exposure -----------------------------------
def test_page_is_marked_paywalled_and_leaks_only_the_teaser():
    html = _norm_render(_ITEM)
    assert '"isAccessibleForFree": false' in html
    assert '"hasPart"' in html and '.rr-gate' in html      # gated part declared
    assert '"@type": "Article"' in html
    # the FIRST bullet (teaser) is public; later bullets are NOT in the page
    assert "Teaserbullet with the thesis" in html
    assert "Secretbullettwo" not in html
    assert "Secretbulletthree" not in html
    # markdown emphasis is stripped from the public snippet
    assert "**Teaserbullet" not in html


# --- public first-pages excerpt --------------------------------------------
# NOTE: the CSS class names (.rr-x, .rr-x-fade …) are in the <style> block on
# EVERY page, so a bare 'rr-x' substring proves nothing — assert on the markup.
_EXCERPT = ["Alphaquotable first paragraph of the pdf body text here.",
            "Bravosecond paragraph continues the argument."]


def test_excerpt_paragraphs_are_public_when_provided():
    html = _norm_render(_ITEM, excerpt_paras=_EXCERPT)
    # The exact-quote play: the report's own words are on the page, verbatim.
    assert "Alphaquotable" in html
    assert "Bravosecond" in html
    assert '<section class="rr-x"' in html
    # The excerpt is PUBLIC: it renders before (outside) the gated part, so the
    # JSON-LD hasPart/.rr-gate paywall declaration stays truthful.
    assert html.index('<section class="rr-x"') < html.index('<div class="rr-gate">')
    assert '"isAccessibleForFree": false' in html
    # noarchive keeps the cache from serving the excerpt around us.
    assert "noarchive" in html


def test_no_excerpt_renders_like_before():
    html = _norm_render(_ITEM, excerpt_paras=[])
    assert '<section class="rr-x"' not in html
    assert "Alphaquotable" not in html
    # the pre-excerpt page contract is untouched
    assert '"isAccessibleForFree": false' in html
    assert '<div class="rr-gate">' in html


def test_page_has_canonical_and_funnel_cta():
    html = _norm_render(_ITEM)
    assert '<link rel="canonical"' in html
    assert f'?doc={_ITEM["id"]}' in html                   # deep-link back to the viewer
    assert "J.P. Morgan" in html and "SELL" in html


# --- sitemap merge ---------------------------------------------------------
def test_sitemap_merge_preserves_other_sections():
    existing = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url><loc>https://www.mastermind-x.com/macro.html</loc></url>\n'
        '  <url><loc>https://www.mastermind-x.com/stocks/AAPL.html</loc></url>\n'
        '  <url><loc>https://www.mastermind-x.com/research/OLD.html</loc></url>\n'
        '</urlset>\n')
    out = rp.build_sitemap(existing, [{"loc": "https://www.mastermind-x.com/research/new.html"}])
    assert "/macro.html" in out                # untouched
    assert "/stocks/AAPL.html" in out          # ticker pages preserved
    assert "/research/OLD.html" not in out     # stale /research/ replaced
    assert "/research/new.html" in out         # fresh /research/ added
    assert out.count("</urlset>") == 1         # well-formed


# --- end-to-end build: a non-empty catalog MUST produce pages ---------------
def _redirect_out(monkeypatch, tmp_path):
    """Point the builder's outputs at tmp_path (never write the live site/ tree)."""
    monkeypatch.setattr(rp, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(rp, "SITEMAP", tmp_path / "sitemap.xml")


def test_build_writes_pages_hub_and_sitemap_for_nonempty_catalog(monkeypatch, tmp_path):
    _redirect_out(monkeypatch, tmp_path)
    other = dict(_ITEM, id="ubs-xyz789-99aa11", title="Second Report", institution="UBS")
    n = rp.build({"items": [_ITEM, other]})
    assert n == 2
    names = {p.name for p in (tmp_path / "research").glob("*.html")}
    assert "index.html" in names               # crawl hub emitted
    assert len(names) == 3                     # 2 report pages + hub
    xml = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    assert xml.count("<url>") == 3             # hub + 2 reports merged into sitemap


def test_build_on_committed_catalog_never_yields_zero_pages(monkeypatch, tmp_path):
    """#3392 regression: the production catalog must always yield landing pages.

    Guards the failure class that shipped dark: a non-empty committed catalog
    with zero site/research/*.html produced. Runs the REAL committed
    data/research_vault/catalog.json through the vault build's own projection,
    so any data-shape drift that breaks the builder fails HERE — not silently
    inside the nightly's fail-soft wrapper.
    """
    from scripts.build_research_vault import _public_catalog, load_catalog
    catalog = _public_catalog(load_catalog())
    if not catalog["items"]:
        pytest.skip("committed catalog is empty — empty state is the honest render")
    _redirect_out(monkeypatch, tmp_path)
    written = rp.build(catalog)
    assert written > 0                         # the alarm: non-empty catalog, zero pages
    renderable = [it for it in catalog["items"] if it.get("id")]
    assert written == len(renderable)          # one landing page per id-bearing report
    assert (tmp_path / "research" / "index.html").exists()


# --- titles are real titles, not filenames ---------------------------------

def _page_titles(path) -> tuple[str, str, str]:
    """(<title>, <h1>, JSON-LD headline) for one rendered report page.

    Markup surfaces are HTML-escaped by Jinja autoescape, JSON-LD is not — so
    unescape before comparing, or every apostrophe reads as a mismatch.
    """
    html = path.read_text(encoding="utf-8")
    head = unescape(re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip())
    h1 = unescape(re.search(r"<h1>(.*?)</h1>", html, re.S).group(1).strip())
    ld = json.loads(re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    return head, h1, ld["headline"]


def test_no_generated_page_titles_itself_after_its_own_filename(monkeypatch, tmp_path):
    """Regression: a report page must never title itself with a source filename.

    Shipped live as e.g. ``<title>2026 07 24 Pmi Fall Seven Times Get Up Eight en
    — TS Lombard …</title>`` — the upstream uploader hands us a de-slugified PDF
    filename as ``title``, and these pages exist only to match a search for the
    real report title.

    The assertion is the filename-ARTEFACT shape, not literal equality with the
    de-slugified filename: the slug is derived from the title, so
    ``deslug(filename) == title`` holds for every healthy page too and would make
    a literal test fire on all 86. ``repair_title`` returning "nothing to repair"
    is exactly the property we want — no date stamp, export language code,
    document number, dup-download marker, dangling paren, or all-lowercase stem.
    Runs the REAL committed catalog so a new bad source is caught on arrival.
    """
    from engine.research_vault.sidecar import repair_title
    from scripts.build_research_vault import _public_catalog, load_catalog
    catalog = _public_catalog(load_catalog())
    if not catalog["items"]:
        pytest.skip("committed catalog is empty — nothing to title")
    _redirect_out(monkeypatch, tmp_path)
    rp.build(catalog)

    offenders = []
    for page in sorted((tmp_path / "research").glob("*.html")):
        if page.name == "index.html":
            continue
        head, h1, headline = _page_titles(page)
        # (3) all three public surfaces carry the SAME real title.
        assert head.startswith(h1), f"{page.name}: <title> disagrees with <h1>"
        assert headline == h1[:110], f"{page.name}: JSON-LD headline disagrees with <h1>"
        if repair_title(h1)[1]:
            offenders.append((page.name, h1))
    assert not offenders, "pages titled after their source filename: " + repr(offenders[:5])


def test_display_title_falls_back_to_institution_and_summary_not_a_slug():
    """An item with no title at all gets a composed, readable title."""
    n = rp._norm(dict(_ITEM, title=""))
    assert n["title"] == "J.P. Morgan research: Teaserbullet with the thesis."
    # …and with no summary either, institution + date rather than a placeholder.
    n2 = rp._norm(dict(_ITEM, title="", summary_points=[]))
    assert n2["title"] == "J.P. Morgan research — Jul 24, 2026"
    assert "Untitled" not in n2["title"]


def test_filename_shaped_titles_are_repaired_on_the_rendered_page():
    """The live defect, end to end: filename in, real title out on all surfaces."""
    html = _norm_render(dict(_ITEM, title="2026 07 24 Pmi Fall Seven Times Get Up Eight en"))
    assert "<h1>PMI Fall Seven Times Get Up Eight</h1>" in html
    assert "2026 07 24" not in html
    assert '"headline": "PMI Fall Seven Times Get Up Eight"' in html


def test_repaired_title_does_not_move_the_indexed_url():
    """URL stability: the slug stays derived from the RAW catalog title."""
    item = dict(_ITEM, title="2026 07 24 Pmi Fall Seven Times Get Up Eight en")
    assert rp.slug_map([item])[item["id"]] == \
        rp._slug(item["title"], item["id"], set())          # unchanged by the repair
