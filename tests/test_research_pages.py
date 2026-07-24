"""Tests for the per-report SEO landing pages (RV programmatic SEO).

Guards the pieces that make the Google play work: stable/unique slugs, a paywalled
JSON-LD contract (isAccessibleForFree:false + hasPart), the teaser-not-full-summary
exposure, the ?doc= funnel CTA, and a sitemap merge that never eats other sections.
"""
from __future__ import annotations

import re

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


def _norm_render(item: dict) -> str:
    env = Environment(loader=FileSystemLoader("templates"),
                      autoescape=True, trim_blocks=True, lstrip_blocks=True)
    n = rp._norm(item)
    canonical = f"{rp.CANONICAL_BASE}/research/x.html"
    md = f"{n['inst']} research. {n['teaser']}"
    return env.get_template("research_report.html.j2").render(
        n=n, canonical=canonical, meta_desc=md,
        jsonld_str=rp._jsonld(n, canonical, md), related=[], site_base=rp.CANONICAL_BASE)


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
