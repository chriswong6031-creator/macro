"""Tests for the per-report SEO landing pages (RV programmatic SEO).

Guards the pieces that make the Google play work: stable/unique slugs, a paywalled
JSON-LD contract (isAccessibleForFree:false + hasPart), the teaser-not-full-summary
exposure, the ?doc= funnel CTA, and a sitemap merge that never eats other sections.
"""
from __future__ import annotations

import re

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
