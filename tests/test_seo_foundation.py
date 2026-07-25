"""tests/test_seo_foundation.py — SEO foundation tests.

Covers:
  (a) SITE_BASE is www
  (b) discovery follows the unauthenticated site-access boundary
  (c) build_core_sitemap preserves public owned-family entries, drops gated
      pages, heals apex hosts, and is valid XML
  (d) round-trip compatibility both directions with build_ticker_pages.build_sitemap
  (e) homepage entry is the bare root URL
  (f) llms.txt and brand-facts.json exist in both templates/ and site/ and byte-match
  (g) brand-facts.json parses with effective_at
  (h) no "validated" in sitemap output (CI-enforced ban)

All fixture writes go to tmp_path only (MM_DATA_GUARD law).
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.seo import (  # noqa: E402
    SITE_BASE,
    build_core_sitemap,
    discover_core_pages,
    is_public_path,
    page_url,
    _should_exclude,
    _EXCLUDE_NAMES,
)
from scripts.build_ticker_pages import build_sitemap as ticker_build_sitemap  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_site(tmp_path: Path, pages: list[str] | None = None) -> Path:
    """Create a minimal site/ directory with given HTML filenames."""
    site = tmp_path / "site"
    site.mkdir()
    # Always create index.html
    (site / "index.html").write_text("<html><head><title>Home</title></head></html>")
    for page in (pages or []):
        (site / page).write_text(f"<html><head><title>{page}</title></head></html>")
    # Create stocks/ subdirectory
    stocks = site / "stocks"
    stocks.mkdir()
    (stocks / "AAPL.html").write_text("<html></html>")
    return site


def _minimal_sitemap(stocks_locs: list[str] | None = None) -> str:
    """Build a minimal sitemap XML string with optional /stocks/ entries."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        '  <url><loc>https://mastermind-x.com/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>',
        '  <url><loc>https://mastermind-x.com/macro.html</loc><changefreq>daily</changefreq><priority>0.9</priority></url>',
    ]
    for loc in (stocks_locs or []):
        lines.append(f'  <url><loc>{loc}</loc><lastmod>2026-07-20</lastmod><changefreq>daily</changefreq><priority>0.6</priority></url>')
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# (a) SITE_BASE is www
# ---------------------------------------------------------------------------

def test_site_base_is_www():
    assert SITE_BASE == "https://www.mastermind-x.com/"


def test_page_url_bare_root():
    assert page_url("") == "https://www.mastermind-x.com/"


def test_page_url_with_path():
    assert page_url("macro.html") == "https://www.mastermind-x.com/macro.html"


# ---------------------------------------------------------------------------
# (b) discover_core_pages follows the public serving boundary
# ---------------------------------------------------------------------------

def test_discover_excludes_mockup(tmp_path):
    site = _make_site(tmp_path, ["_mockup_foo.html", "plans.html"])
    pages = discover_core_pages(site)
    names = [n for n, _, _ in pages]
    assert "_mockup_foo" not in names
    assert "plans" in names


def test_discover_excludes_calibration(tmp_path):
    site = _make_site(tmp_path, ["calibration.html", "plans.html"])
    pages = discover_core_pages(site)
    names = [n for n, _, _ in pages]
    assert "calibration" not in names
    assert "plans" in names


def test_discover_excludes_chat(tmp_path):
    site = _make_site(tmp_path, ["chat.html", "plans.html"])
    pages = discover_core_pages(site)
    names = [n for n, _, _ in pages]
    assert "chat" not in names
    assert "plans" in names


def test_discover_excludes_all_in_exclude_names(tmp_path):
    """Every name in _EXCLUDE_NAMES must be excluded from discovery."""
    # Create a site with all excluded pages + one known public page
    site = _make_site(tmp_path, [f"{n}.html" for n in _EXCLUDE_NAMES] + ["plans.html"])
    pages = discover_core_pages(site)
    names = {n for n, _, _ in pages}
    for excluded in _EXCLUDE_NAMES:
        assert excluded not in names, f"Expected {excluded!r} to be excluded but it appeared"
    assert "plans" in names


def test_discover_excludes_registered_dashboard(tmp_path):
    """A real page is not sitemap-eligible merely because the file exists."""
    site = _make_site(tmp_path, ["plans.html", "macro.html", "bonds.html"])
    names = {name for name, _, _ in discover_core_pages(site)}
    assert "plans" in names
    assert "macro" not in names
    assert "bonds" not in names


def test_discover_excludes_stocks_subdir(tmp_path):
    """site/stocks/*.html must never appear in core discovery."""
    site = _make_site(tmp_path, ["macro.html"])
    pages = discover_core_pages(site)
    for name, url, filename in pages:
        assert "/stocks/" not in url, f"stocks/ URL leaked into core: {url}"


def test_discover_homepage_bare_root(tmp_path):
    """index.html maps to the bare root URL, not index.html."""
    site = _make_site(tmp_path)
    pages = discover_core_pages(site)
    urls = [url for _, url, _ in pages]
    assert "https://www.mastermind-x.com/" in urls
    # Must NOT include index.html path
    assert "https://www.mastermind-x.com/index.html" not in urls


def test_discover_homepage_is_first(tmp_path):
    """Homepage (empty name) must be first in the sorted list."""
    site = _make_site(tmp_path, ["plans.html", "macro.html"])
    pages = discover_core_pages(site)
    assert pages[0][0] == "", f"Expected homepage first, got {pages[0]}"


# ---------------------------------------------------------------------------
# (c) build_core_sitemap: valid XML, www URLs, preserves /stocks/, heals apex
# ---------------------------------------------------------------------------

def test_build_core_sitemap_valid_xml(tmp_path):
    site = _make_site(tmp_path, ["macro.html"])
    existing = _minimal_sitemap(["https://mastermind-x.com/stocks/AAPL.html"])
    result = build_core_sitemap(existing, site)
    # Must parse as valid XML
    ET.fromstring(result)


def test_build_core_sitemap_www_only(tmp_path):
    site = _make_site(tmp_path, ["macro.html"])
    existing = _minimal_sitemap(["https://mastermind-x.com/stocks/AAPL.html"])
    result = build_core_sitemap(existing, site)
    # Zero apex-host occurrences in any <loc>
    assert "https://mastermind-x.com/" not in result, (
        "Apex-host URL found in sitemap output — expected www only"
    )


def test_build_core_sitemap_preserves_stocks(tmp_path):
    site = _make_site(tmp_path, ["macro.html"])
    stocks_locs = [
        "https://mastermind-x.com/stocks/AAPL.html",
        "https://mastermind-x.com/stocks/MSFT.html",
    ]
    existing = _minimal_sitemap(stocks_locs)
    result = build_core_sitemap(existing, site)
    # Both stocks entries must appear (normalized to www)
    assert "https://www.mastermind-x.com/stocks/AAPL.html" in result
    assert "https://www.mastermind-x.com/stocks/MSFT.html" in result


def test_build_core_sitemap_heals_apex_in_stocks(tmp_path):
    """Preserved /stocks/ entries have their apex host normalized to www."""
    site = _make_site(tmp_path, ["macro.html"])
    existing = _minimal_sitemap(["https://mastermind-x.com/stocks/AAPL.html"])
    result = build_core_sitemap(existing, site)
    # Apex host must be gone from the stocks entry too
    assert "https://mastermind-x.com/stocks/AAPL.html" not in result
    assert "https://www.mastermind-x.com/stocks/AAPL.html" in result


def test_build_core_sitemap_preserves_public_research_entries(tmp_path):
    """The research builder owns publication dates for its runtime pages."""
    site = _make_site(tmp_path, ["plans.html"])
    existing = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url><loc>https://mastermind-x.com/research/sample.html</loc>'
        '<lastmod>2026-07-01</lastmod><changefreq>weekly</changefreq>'
        '<priority>0.5</priority></url>\n'
        '</urlset>\n'
    )
    result = build_core_sitemap(existing, site)
    assert "https://www.mastermind-x.com/research/sample.html" in result
    assert "<lastmod>2026-07-01</lastmod>" in result


def test_build_core_sitemap_homepage_entry(tmp_path):
    """Sitemap must contain the bare root URL for homepage."""
    site = _make_site(tmp_path, ["macro.html"])
    existing = _minimal_sitemap()
    result = build_core_sitemap(existing, site)
    assert "<loc>https://www.mastermind-x.com/</loc>" in result


def test_build_core_sitemap_drops_gated_root_pages(tmp_path):
    site = _make_site(tmp_path, ["plans.html", "macro.html", "bonds.html"])
    result = build_core_sitemap(_minimal_sitemap(), site)
    assert "https://www.mastermind-x.com/plans.html" in result
    assert "/macro.html" not in result
    assert "/bonds.html" not in result


def test_build_core_sitemap_does_not_invent_lastmod(tmp_path):
    """Build time is not evidence that a page's content changed."""
    site = _make_site(tmp_path, ["plans.html"])
    result = build_core_sitemap(_minimal_sitemap(), site)
    root = ET.fromstring(result)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    entries = {
        node.findtext("sm:loc", namespaces=ns): node
        for node in root.findall("sm:url", ns)
    }
    assert entries["https://www.mastermind-x.com/"].find("sm:lastmod", ns) is None
    assert entries["https://www.mastermind-x.com/plans.html"].find("sm:lastmod", ns) is None


def test_build_core_sitemap_no_validated(tmp_path):
    """CI-enforced ban: 'validated' must not appear in sitemap output."""
    site = _make_site(tmp_path, ["macro.html"])
    existing = _minimal_sitemap()
    result = build_core_sitemap(existing, site)
    assert "validated" not in result.lower()


# ---------------------------------------------------------------------------
# (d) Round-trip compatibility both directions
# ---------------------------------------------------------------------------

def _stocks_entries(locs: list[str]) -> list[dict]:
    """Build stocks entries list as expected by build_ticker_pages.build_sitemap."""
    return [
        {"loc": loc, "lastmod": "2026-07-20", "changefreq": "daily", "priority": 0.6}
        for loc in locs
    ]


def test_round_trip_core_then_ticker(tmp_path):
    """core sitemap → ticker sitemap → core sitemap: stocks and core entries survive."""
    site = _make_site(tmp_path, ["plans.html", "macro.html", "bonds.html"])

    # Step 1: build core sitemap from empty seed
    empty = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n</urlset>\n'
    after_core = build_core_sitemap(empty, site)

    # Step 2: ticker pass adds /stocks/ entries
    stock_locs = ["https://www.mastermind-x.com/stocks/AAPL.html",
                  "https://www.mastermind-x.com/stocks/MSFT.html"]
    after_ticker = ticker_build_sitemap(after_core, _stocks_entries(stock_locs))

    # Core entries must still be present
    assert "https://www.mastermind-x.com/" in after_ticker
    assert "https://www.mastermind-x.com/plans.html" in after_ticker
    assert "https://www.mastermind-x.com/macro.html" not in after_ticker
    assert "https://www.mastermind-x.com/bonds.html" not in after_ticker
    # Stocks entries must be present
    for loc in stock_locs:
        assert loc in after_ticker


def test_round_trip_ticker_then_core(tmp_path):
    """ticker sitemap → core sitemap: core entries replaced, stocks preserved."""
    site = _make_site(tmp_path, ["plans.html", "macro.html", "bonds.html"])

    # Step 1: start with a ticker-only sitemap (has stocks, stale core)
    stock_locs = ["https://mastermind-x.com/stocks/AAPL.html",
                  "https://mastermind-x.com/stocks/MSFT.html"]
    after_ticker = ticker_build_sitemap(
        _minimal_sitemap(),  # stale core (apex, only macro listed)
        _stocks_entries(stock_locs),
    )

    # Step 2: core pass regenerates core entries + normalizes stocks
    after_core = build_core_sitemap(after_ticker, site)

    # Public core entries must be present; gated root pages must be gone.
    assert "https://www.mastermind-x.com/" in after_core
    assert "https://www.mastermind-x.com/plans.html" in after_core
    assert "https://www.mastermind-x.com/macro.html" not in after_core
    assert "https://www.mastermind-x.com/bonds.html" not in after_core
    # Stocks entries preserved with www (healed)
    assert "https://www.mastermind-x.com/stocks/AAPL.html" in after_core
    assert "https://www.mastermind-x.com/stocks/MSFT.html" in after_core
    # No apex host anywhere
    assert "https://mastermind-x.com/" not in after_core


def test_round_trip_repeated_core_is_idempotent(tmp_path):
    """Running build_core_sitemap twice on the same output yields the same result."""
    site = _make_site(tmp_path, ["macro.html"])
    stock_locs = ["https://www.mastermind-x.com/stocks/AAPL.html"]
    existing = _minimal_sitemap(stock_locs)

    first = build_core_sitemap(existing, site)
    second = build_core_sitemap(first, site)
    assert first == second, "build_core_sitemap is not idempotent"


# ---------------------------------------------------------------------------
# (e) Homepage entry is bare root
# ---------------------------------------------------------------------------

def test_sitemap_homepage_not_index_html(tmp_path):
    """Sitemap must not contain /index.html — only the bare root /."""
    site = _make_site(tmp_path, ["macro.html"])
    existing = _minimal_sitemap()
    result = build_core_sitemap(existing, site)
    assert "/index.html" not in result


# ---------------------------------------------------------------------------
# (f) llms.txt and brand-facts.json exist in both templates/ and site/, byte-match
# ---------------------------------------------------------------------------

def test_llms_txt_exists_in_templates():
    p = _REPO / "templates" / "llms.txt"
    assert p.exists(), f"templates/llms.txt missing at {p}"


def test_llms_txt_exists_in_site():
    p = _REPO / "site" / "llms.txt"
    assert p.exists(), f"site/llms.txt missing at {p}"


def test_llms_txt_byte_matches():
    tpl = (_REPO / "templates" / "llms.txt").read_bytes()
    site = (_REPO / "site" / "llms.txt").read_bytes()
    assert tpl == site, "templates/llms.txt and site/llms.txt do not byte-match"


def test_brand_facts_json_exists_in_templates():
    p = _REPO / "templates" / "brand-facts.json"
    assert p.exists(), f"templates/brand-facts.json missing at {p}"


def test_brand_facts_json_exists_in_site():
    p = _REPO / "site" / "brand-facts.json"
    assert p.exists(), f"site/brand-facts.json missing at {p}"


def test_brand_facts_json_byte_matches():
    tpl = (_REPO / "templates" / "brand-facts.json").read_bytes()
    site = (_REPO / "site" / "brand-facts.json").read_bytes()
    assert tpl == site, "templates/brand-facts.json and site/brand-facts.json do not byte-match"


def test_llms_txt_contains_www():
    text = (_REPO / "templates" / "llms.txt").read_text()
    assert "https://www.mastermind-x.com/" in text
    assert "https://mastermind-x.com/" not in text


def test_llms_txt_advertises_only_public_urls():
    text = (_REPO / "templates" / "llms.txt").read_text()
    urls = re.findall(r"https://www\.mastermind-x\.com/[^\s)>\]]*", text)
    gated = [url for url in urls if not is_public_path(urlsplit(url).path)]
    assert gated == [], f"llms.txt advertises gated URLs: {gated}"


# ---------------------------------------------------------------------------
# (g) brand-facts.json parses with effective_at and no "validated"
# ---------------------------------------------------------------------------

def test_brand_facts_parses():
    p = _REPO / "templates" / "brand-facts.json"
    data = json.loads(p.read_text())
    assert "effective_at" in data, "brand-facts.json missing 'effective_at'"
    assert data["effective_at"], "effective_at is empty"


def test_brand_facts_has_public_surfaces():
    p = _REPO / "templates" / "brand-facts.json"
    data = json.loads(p.read_text())
    assert data.get("surface_scope") == "public_unauthenticated"
    surfaces = data.get("surfaces", [])
    assert len(surfaces) == 7, f"Expected 7 public surfaces, got {len(surfaces)}"


def test_brand_facts_no_validated():
    """CI-enforced ban: 'validated' must not appear in brand-facts.json."""
    text = (_REPO / "templates" / "brand-facts.json").read_text()
    assert "validated" not in text.lower(), "brand-facts.json contains banned word 'validated'"


def test_brand_facts_www_only():
    """brand-facts.json must use www URLs throughout."""
    text = (_REPO / "templates" / "brand-facts.json").read_text()
    assert "https://mastermind-x.com/" not in text, (
        "brand-facts.json contains apex host — all URLs must use www"
    )


def test_brand_facts_public_surfaces_are_public_and_www():
    """Every advertised surface must be reachable without registration."""
    p = _REPO / "templates" / "brand-facts.json"
    data = json.loads(p.read_text())
    for surface in data.get("surfaces", []):
        url = surface.get("url", "")
        assert url.startswith("https://www.mastermind-x.com/"), (
            f"Surface URL uses apex host: {url}"
        )
        assert is_public_path(urlsplit(url).path), f"Advertised gated surface: {url}"


# ---------------------------------------------------------------------------
# (h) Regenerated sitemap has zero apex host occurrences
# ---------------------------------------------------------------------------

def test_live_sitemap_www_only():
    """The committed site/sitemap.xml must contain zero apex-host URLs."""
    sm = _REPO / "site" / "sitemap.xml"
    if not sm.exists():
        pytest.skip("site/sitemap.xml not present")
    text = sm.read_text()
    apex_count = text.count("https://mastermind-x.com/")
    assert apex_count == 0, (
        f"Found {apex_count} apex-host occurrences in site/sitemap.xml"
    )


def test_live_sitemap_contains_only_public_urls():
    """The committed artifact must agree with the enforced access boundary."""
    root = ET.parse(_REPO / "site" / "sitemap.xml").getroot()
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    paths = [
        urlsplit(node.text or "").path
        for node in root.findall(".//sm:loc", ns)
    ]
    gated = [path for path in paths if not is_public_path(path)]
    assert gated == [], f"Gated URLs leaked into sitemap: {gated[:10]}"
